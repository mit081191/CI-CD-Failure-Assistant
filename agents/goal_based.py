"""Goal-Based Agent.

Decision mechanism: explicit GOAL + SEARCH over an action model.

Goal state: {"root_cause_confirmed", "fix_path_identified"} - i.e. the cause of
the failure is confirmed and a safe fix path exists (advisory only, no automatic
changes).

Each troubleshooting action has preconditions (facts that must hold) and
effects (facts it adds), STRIPS-style. The agent converts percepts into an
initial set of facts and runs uniform-cost search to find the cheapest action
sequence that reaches the goal. The recommended next step is the first action
of that plan; the failure category follows from the hypothesis the plan
confirms. If no plan reaches the goal, the agent asks for more information.
"""

import heapq
from dataclasses import dataclass

from core.knowledge import (
    DEPENDENCY_FAILURE,
    DEPLOYMENT_FAILURE,
    FLAKY_INFRA,
    TEST_FAILURE,
    UNKNOWN,
)
from agents.base import Decision, checklist_for, evidence_for, sense

GOAL = frozenset({"root_cause_confirmed", "fix_path_identified"})


@dataclass(frozen=True)
class Action:
    name: str
    pre: frozenset
    add: frozenset
    cost: int  # estimated engineer minutes
    hypothesis: str = None  # category this action confirms (if any)


ACTIONS = [
    # --- code regression path
    Action("Map failing tests to the files changed in the latest commit",
           frozenset({"tests_failed", "change_touches_failing_module"}), frozenset({"suspect_change_identified"}), 5),
    Action("Reproduce the failing tests locally on the suspect commit and its parent",
           frozenset({"suspect_change_identified", "deterministic_failure"}), frozenset({"root_cause_confirmed"}), 15, TEST_FAILURE),
    Action("Hand the failing assertion + diff to the commit author for a fix in a new commit",
           frozenset({"root_cause_confirmed", "suspect_change_identified"}), frozenset({"fix_path_identified"}), 5),
    # --- dependency path
    Action("Check the package index for the requested versions and runner Python compatibility",
           frozenset({"dependency_resolution_error"}), frozenset({"version_problem_confirmed"}), 5),
    Action("Identify the commit that changed the dependency pins",
           frozenset({"version_problem_confirmed", "deps_changed"}), frozenset({"root_cause_confirmed"}), 3, DEPENDENCY_FAILURE),
    Action("Propose pinning to the newest available compatible versions (owner applies)",
           frozenset({"root_cause_confirmed", "version_problem_confirmed"}), frozenset({"fix_path_identified"}), 5),
    # --- deployment path
    Action("Inspect failing health-check endpoints and application startup logs",
           frozenset({"health_check_failed"}), frozenset({"failing_component_identified"}), 5),
    Action("Compare runtime configuration / env vars between the healthy and new release",
           frozenset({"failing_component_identified", "config_changed"}), frozenset({"root_cause_confirmed"}), 10, DEPLOYMENT_FAILURE),
    Action("Ask the release owner to keep rollout paused or roll back, and correct the config",
           frozenset({"root_cause_confirmed", "failing_component_identified"}), frozenset({"fix_path_identified"}), 5),
    # --- flaky / infra path
    Action("Re-run the failed job on a different runner (no code change)",
           frozenset({"tests_failed", "timeout_error"}), frozenset({"determinism_assessed"}), 10),
    Action("Check runner disk and test-database connectivity",
           frozenset({"determinism_assessed", "infra_warning"}), frozenset({"root_cause_confirmed"}), 10, FLAKY_INFRA),
    Action("Open an infra ticket and track the flaky test (quarantine only with owner approval)",
           frozenset({"root_cause_confirmed", "determinism_assessed"}), frozenset({"fix_path_identified"}), 5),
]


def facts_from_percepts(p: dict) -> frozenset:
    f = set()
    if p["tests_failed"]:
        f.add("tests_failed")
    if p["change_touches_failing_module"]:
        f.add("change_touches_failing_module")
    if p["failed_on_retry"] or (p["signals"]["assertion_error"] and not p["signals"]["timeout_error"]):
        f.add("deterministic_failure")
    if p["signals"]["dependency_resolution_error"] or p["dependency_errors"]:
        f.add("dependency_resolution_error")
    if p["deps_changed"]:
        f.add("deps_changed")
    if p["health_failed"]:
        f.add("health_check_failed")
    if p["config_changes"] or p["signals"]["missing_config"]:
        f.add("config_changed")
    if p["signals"]["timeout_error"]:
        f.add("timeout_error")
    if p["signals"]["infra_warning"]:
        f.add("infra_warning")
    return frozenset(f)


def plan(initial: frozenset, max_depth: int = 6):
    """Uniform-cost search; returns (plan, total_cost, nodes_expanded)."""
    counter = 0
    frontier = [(0, counter, initial, [])]
    seen = {}
    expanded = 0
    while frontier:
        cost, _, state, path = heapq.heappop(frontier)
        if GOAL <= state:
            return path, cost, expanded
        if seen.get(state, 1e9) <= cost or len(path) >= max_depth:
            continue
        seen[state] = cost
        expanded += 1
        for a in ACTIONS:
            if a.pre <= state and not a.add <= state:
                counter += 1
                heapq.heappush(frontier, (cost + a.cost, counter, state | a.add, path + [a]))
    return None, None, expanded


class GoalBasedAgent:
    name = "Goal-Based"
    mechanism = "Uniform-cost search for an action plan that reaches the goal (cause confirmed + fix path)"

    def decide(self, scenario: dict) -> Decision:
        p = sense(scenario)
        facts = facts_from_percepts(p)
        trace = [f"Initial facts: {sorted(facts)}", f"Goal: {sorted(GOAL)}"]
        steps, cost, expanded = plan(facts)
        trace.append(f"Search expanded {expanded} states")

        if not steps:
            trace.append("No action sequence reaches the goal from the known facts -> gather information first")
            return Decision(
                agent=self.name, mechanism=self.mechanism, failure_category=UNKNOWN,
                evidence=[f"Pipeline failed at stage '{p['failed_stage']}'"],
                likely_cause="Known facts do not satisfy the preconditions of any diagnosis path.",
                next_step="Collect complete logs and test reports for the failed stage, then re-plan.",
                verification_checklist=checklist_for(UNKNOWN), reasoning=trace, confidence=0.2,
                details={"plan": [], "facts": sorted(facts)},
            )

        category = next(a.hypothesis for a in steps if a.hypothesis)
        for i, a in enumerate(steps, 1):
            trace.append(f"Plan step {i}: {a.name} (cost {a.cost} min) -> adds {sorted(a.add)}")
        trace.append(f"Plan reaches goal with total estimated cost {cost} min; category confirmed by plan: {category}")

        causes = {
            TEST_FAILURE: "The latest code change in the module under test introduced a deterministic regression.",
            DEPENDENCY_FAILURE: "Dependency pins changed in the latest commit request versions that cannot be installed on the runner.",
            DEPLOYMENT_FAILURE: "The release depends on configuration that is missing or renamed in the target environment.",
            FLAKY_INFRA: "Timeout in an integration test on an unhealthy runner - an infrastructure problem, not the code change.",
        }
        return Decision(
            agent=self.name, mechanism=self.mechanism, failure_category=category,
            evidence=evidence_for(category, p), likely_cause=causes[category],
            next_step=steps[0].name, verification_checklist=checklist_for(category),
            reasoning=trace, confidence=0.8,
            details={"plan": [a.name for a in steps], "plan_cost_min": cost, "facts": sorted(facts)},
        )