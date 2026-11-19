"""Model-Based Reflex Agent.

Decision mechanism: condition -> action rules evaluated on an INTERNAL STATE
(world model) rather than the raw percept. The state is updated from:
  * the pipeline's run history (how the world evolved), and
  * the current percept (what we see now),
using a simple transition model of a CI pipeline:
  build -> unit_test -> package -> deploy_canary -> health_check
(the first failing stage is the locus of the problem; a test that fails and
passes on the SAME commit is non-deterministic).

State persists inside the agent object between calls (per pipeline timeline), so in the
UI the agent accumulates knowledge as more runs are investigated.
"""

from collections import defaultdict

from core.knowledge import (
    DEPENDENCY_FAILURE,
    DEPLOYMENT_FAILURE,
    FLAKY_INFRA,
    TEST_FAILURE,
    UNKNOWN,
)
from agents.base import Decision, checklist_for, evidence_for, sense


class ModelBasedReflexAgent:
    name = "Model-Based Reflex"
    mechanism = "Rules over an internal pipeline state updated from history + current percept"

    def __init__(self):
        self.state = {}  # pipeline name -> world model

    # ----------------------------------------------------------- state update
    def _blank_state(self) -> dict:
        return {
            "runs_seen": set(),
            "last_green_commit": None,
            "last_healthy_version": None,
            "test_outcomes": defaultdict(list),   # test -> [(commit, 'pass'|'fail')]
            "commit_outcomes": defaultdict(list),  # commit -> ['success'|'failed']
        }

    def update_state(self, scenario: dict, p: dict) -> dict:
        # each scenario is an independent pipeline timeline, so state is keyed by both
        world = f"{scenario['pipeline_status']['pipeline']}#{scenario['id']}"
        st = self.state.setdefault(world, self._blank_state())
        current_failing = set(p["failing_tests"])

        # replay history oldest -> newest
        for run in reversed(scenario["run_history"]):
            if run["run_id"] in st["runs_seen"]:
                continue
            st["runs_seen"].add(run["run_id"])
            st["commit_outcomes"][run["commit"]].append(run["overall"])
            if run["overall"] == "success" and run["run_id"] > st.get("last_green_run", -1):
                st["last_green_run"] = run["run_id"]
                st["last_green_commit"] = run["commit"]
                if run.get("health") == "healthy":
                    st["last_healthy_version"] = run.get("deployed_version")
            failed = set(run.get("failed_tests", []))
            # record pass/fail for tests that matter now
            for t in current_failing | failed:
                ok = run["overall"] == "success" or t not in failed
                st["test_outcomes"][t].append((run["commit"], "pass" if ok else "fail"))

        # incorporate current percept
        run_id = scenario["pipeline_status"]["run_id"]
        if run_id not in st["runs_seen"]:
            st["runs_seen"].add(run_id)
            st["commit_outcomes"][p["commit"]].append(p["overall"])
            for t in current_failing:
                st["test_outcomes"][t].append((p["commit"], "fail"))
        return st

    # ----------------------------------------------------------- derived facts
    @staticmethod
    def _flaky_tests(st: dict, tests: list) -> dict:
        """A test is flaky if it both passed and failed on the same commit, or
        alternated pass/fail across recent runs."""
        out = {}
        for t in tests:
            hist = st["test_outcomes"].get(t, [])
            by_commit = defaultdict(set)
            for commit, res in hist:
                by_commit[commit].add(res)
            same_commit = [c for c, r in by_commit.items() if r == {"pass", "fail"}]
            fails = sum(1 for _, r in hist if r == "fail")
            if same_commit or (fails >= 2 and len(hist) - fails >= 1):
                out[t] = {"fails": fails, "observations": len(hist), "mixed_on_commits": same_commit}
        return out

    # ----------------------------------------------------------- decide
    def decide(self, scenario: dict) -> Decision:
        p = sense(scenario)
        st = self.update_state(scenario, p)
        flaky = self._flaky_tests(st, p["failing_tests"])
        parent_green = st["last_green_commit"] == p["parent_commit"]

        trace = [
            f"State: last green commit = {st['last_green_commit']}, "
            f"parent commit = {p['parent_commit']} (parent green: {parent_green})",
            f"State: last healthy deployed version = {st['last_healthy_version']}",
            f"State: runs observed for this pipeline = {len(st['runs_seen'])}",
        ]
        if flaky:
            for t, info in flaky.items():
                trace.append(
                    f"State: {t.split('::')[-1]} failed {info['fails']}/{info['observations']} "
                    f"observed runs; mixed pass/fail on commits {info['mixed_on_commits']}"
                )

        details = {
            "last_green_commit": st["last_green_commit"],
            "last_healthy_version": st["last_healthy_version"],
            "flaky_tests": flaky,
        }

        if p["failed_stage"] == "build" and (p["signals"]["dependency_resolution_error"] or p["dependency_errors"]):
            cat = DEPENDENCY_FAILURE
            trace.append("Rule: first failing stage is build AND model shows dependency errors -> dependency failure")
            cause = ("The latest commit changed dependency pins to versions that cannot be installed "
                     "on the runner (unavailable or Python-incompatible)." if p["deps_changed"]
                     else "Dependency resolution failed although the manifest did not change (index/cache issue).")
            step = "Compare the manifest diff against the last green commit and check each failing pin on the package index."
            conf = 0.9
        elif p["tests_failed"] and flaky and not p["change_touches_failing_module"]:
            cat = FLAKY_INFRA
            trace.append("Rule: failing test is flaky in the state model AND change does not touch it -> flaky/infra")
            cause = "Non-deterministic test failure (test-database connectivity / runner health), not caused by the latest commit."
            step = "Re-run the failed job on a different runner and check the health of the test database and runner disk."
            conf = 0.8
        elif p["tests_failed"]:
            cat = TEST_FAILURE
            if parent_green:
                trace.append("Rule: tests failed AND parent commit was green in the state model -> regression introduced by latest commit")
            else:
                trace.append("Rule: tests failed, no flaky history -> treat as code regression")
            cause = (f"Commit {p['commit']} changed {', '.join(p['code_files_changed']) or 'code'} "
                     "and broke tests that passed on the previous green commit.")
            step = f"Diff {p['commit']} against last green commit {st['last_green_commit']} for the module under test and reproduce the failing tests locally."
            conf = 0.85 if parent_green else 0.65
        elif p["health_failed"] or p["failed_stage"] == "health_check":
            cat = DEPLOYMENT_FAILURE
            trace.append("Rule: all pre-deploy stages green, health check failed, previous version was healthy -> release/config problem")
            cause = ("The new release fails in the target environment while the previous version "
                     f"({st['last_healthy_version']}) was healthy - likely an environment/config mismatch.")
            step = "Compare runtime configuration between the healthy and failing versions; keep rollout paused and inform the release owner."
            conf = 0.85
        else:
            cat = UNKNOWN
            trace.append("No rule matched the current state")
            cause, step, conf = "Insufficient information.", "Collect full logs and escalate.", 0.2

        return Decision(
            agent=self.name, mechanism=self.mechanism, failure_category=cat,
            evidence=evidence_for(cat, p) if cat != UNKNOWN else [],
            likely_cause=cause, next_step=step,
            verification_checklist=checklist_for(cat), reasoning=trace,
            confidence=conf, details=details,
        )