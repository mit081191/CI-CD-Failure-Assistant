"""Learning Agent.

Decision mechanism: decisions are driven by EXPERIENCE DATA that is updated from
feedback on past investigations (data/experience.json).

Components (Russell & Norvig learning-agent architecture):
  * Performance element - picks a category and an action using the experience:
      - failure signature = failed stage + dominant log signal
      - category = most frequent confirmed category for that signature
        (Laplace-smoothed probability)
      - action   = action with the highest Laplace-smoothed success rate
        (s + 1) / (s + f + 2) for that category
  * Critic - `record_outcome()` receives the engineer's feedback (actual
    category, whether the recommended step helped) and compares it with the
    prediction.
  * Learning element - updates signature and success/failure counts and logs the
    episode, so the next decision for a similar failure changes.
  * Problem generator - for an unseen signature the agent falls back to a
    stage-based prior and marks the decision as exploratory.
"""

import copy
import json
import os
from datetime import datetime

from core.knowledge import (
    DEPENDENCY_FAILURE,
    DEPLOYMENT_FAILURE,
    FLAKY_INFRA,
    TEST_FAILURE,
    UNKNOWN,
)
from agents.base import Decision, checklist_for, evidence_for, sense

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_PATH = os.path.join(HERE, "data", "experience_seed.json")
DEFAULT_PATH = os.path.join(HERE, "data", "experience.json")

SIGNAL_PRIORITY = [
    "dependency_resolution_error",
    "missing_config",
    "readiness_probe_failed",
    "timeout_error",
    "assertion_error",
]

STAGE_PRIOR = {
    "build": DEPENDENCY_FAILURE,
    "unit_test": TEST_FAILURE,
    "health_check": DEPLOYMENT_FAILURE,
    "deploy_canary": DEPLOYMENT_FAILURE,
}

# candidate actions per category (the agent learns which one works best)
ACTION_MENU = {
    TEST_FAILURE: [
        "Reproduce the failing tests locally on the suspect commit",
        "Re-run the pipeline without changes",
        "Ask the commit author to review the failing assertion against the diff",
    ],
    DEPENDENCY_FAILURE: [
        "Check the package index for the pinned versions and runner Python compatibility",
        "Clear the CI dependency cache and re-run",
        "Pin back to the last versions used by the green build",
    ],
    DEPLOYMENT_FAILURE: [
        "Diff runtime configuration/env vars between healthy and failing release",
        "Restart the failing pods",
        "Recommend rollback to the release owner",
    ],
    FLAKY_INFRA: [
        "Re-run the job on a different runner and check runner/test-DB health",
        "Increase the test timeout",
        "Quarantine the test immediately",
    ],
    UNKNOWN: ["Collect full logs and escalate to the pipeline owner"],
}


def laplace(s: int, f: int) -> float:
    return (s + 1) / (s + f + 2)


class LearningAgent:
    name = "Learning"
    mechanism = "Experience-driven: signature->category counts and action success/failure rates, updated by feedback"

    def __init__(self, experience_path: str = DEFAULT_PATH):
        self.path = experience_path
        if not os.path.exists(self.path):
            self.reset()
        self.experience = self._load()

    # ---------------------------------------------------------- persistence
    def _load(self) -> dict:
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def save(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self.experience, fh, indent=2)

    def reset(self):
        with open(SEED_PATH, encoding="utf-8") as fh:
            seed = json.load(fh)
        self.experience = copy.deepcopy(seed)
        self.save()

    # ---------------------------------------------------------- helpers
    @staticmethod
    def signature(p: dict) -> str:
        signal = next((s for s in SIGNAL_PRIORITY if p["signals"].get(s)), "none")
        return f"{p['failed_stage']}|{signal}"

    def category_distribution(self, sig: str) -> dict:
        counts = self.experience["signature_outcomes"].get(sig, {})
        cats = [TEST_FAILURE, DEPENDENCY_FAILURE, DEPLOYMENT_FAILURE, FLAKY_INFRA]
        total = sum(counts.get(c, 0) for c in cats)
        return {c: (counts.get(c, 0) + 1) / (total + len(cats)) for c in cats}, counts

    def action_stats(self, category: str) -> list:
        stats = self.experience["action_outcomes"].setdefault(category, {})
        rows = []
        for a in ACTION_MENU[category]:
            s = stats.get(a, {}).get("success", 0)
            f = stats.get(a, {}).get("failure", 0)
            rows.append({"action": a, "success": s, "failure": f, "success_rate": round(laplace(s, f), 3)})
        rows.sort(key=lambda r: r["success_rate"], reverse=True)
        return rows

    # ---------------------------------------------------------- performance element
    def decide(self, scenario: dict) -> Decision:
        p = sense(scenario)
        sig = self.signature(p)
        dist, raw = self.category_distribution(sig)
        trace = [f"Failure signature: '{sig}'"]

        if raw:
            category = max(dist, key=dist.get)
            conf = dist[category]
            trace.append(f"Experience for this signature (confirmed categories): {raw}")
            trace.append("Laplace-smoothed P(category|signature): " +
                         ", ".join(f"{c}={v:.2f}" for c, v in sorted(dist.items(), key=lambda x: -x[1])))
            exploratory = False
        else:
            category = STAGE_PRIOR.get(p["failed_stage"], UNKNOWN)
            conf = 0.3
            trace.append("Signature never seen before -> exploratory decision using stage prior")
            exploratory = True

        rows = self.action_stats(category)
        best = rows[0]
        trace.append(f"Action success rates for {category} ((s+1)/(s+f+2)):")
        for r in rows:
            trace.append(f"  {r['action']}: {r['success']} success / {r['failure']} failure -> {r['success_rate']}")
        trace.append(f"Chosen: '{best['action']}' because it has the highest learned success rate.")
        trace.append("Feedback recorded in the UI updates these counts and can change future decisions.")

        cause = {
            TEST_FAILURE: "Past failures with this signature were mostly code regressions.",
            DEPENDENCY_FAILURE: "Past failures with this signature were dependency/version problems.",
            DEPLOYMENT_FAILURE: "Past failures with this signature were release configuration problems.",
            FLAKY_INFRA: "Past failures with this signature were mostly flaky tests / CI infrastructure.",
            UNKNOWN: "No experience available.",
        }[category]

        return Decision(
            agent=self.name, mechanism=self.mechanism, failure_category=category,
            evidence=evidence_for(category, p), likely_cause=cause, next_step=best["action"],
            verification_checklist=checklist_for(category), reasoning=trace,
            confidence=round(conf, 2),
            details={"signature": sig, "signature_counts": raw, "action_stats": rows,
                     "exploratory": exploratory, "episodes_so_far": len(self.experience["episodes"])},
        )

    # ---------------------------------------------------------- critic + learning element
    def record_outcome(self, scenario: dict, predicted_category: str, actual_category: str,
                       action: str, success: bool) -> dict:
        p = sense(scenario)
        sig = self.signature(p)
        sig_counts = self.experience["signature_outcomes"].setdefault(sig, {})
        sig_counts[actual_category] = sig_counts.get(actual_category, 0) + 1

        # the action came from the predicted category's menu, so its success/failure
        # is credited there (a wrong diagnosis usually means the action failed)
        act = self.experience["action_outcomes"].setdefault(predicted_category, {}).setdefault(
            action, {"success": 0, "failure": 0})
        act["success" if success else "failure"] += 1

        episode = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "scenario": scenario["id"],
            "signature": sig,
            "predicted": predicted_category,
            "actual": actual_category,
            "prediction_correct": predicted_category == actual_category,
            "action": action,
            "action_success": success,
        }
        self.experience["episodes"].append(episode)
        self.save()
        return episode
