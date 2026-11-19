"""Utility-Based Agent.

Decision mechanism: maximise EXPECTED UTILITY over candidate troubleshooting
actions under uncertainty about the root cause.

1. Belief: evidence features add log-odds weights to each hypothesis
   (failure category); a softmax turns scores into probabilities P(h | evidence).
2. Each candidate action a has:
     value(a, h)  - how much it advances diagnosis/resolution if h is true (0..1)
     cost(a)      - engineer minutes
     risk(a)      - chance of causing harm / disruption (0..1)
3. EU(a) = BENEFIT * sum_h P(h) * value(a, h) - COST_W * cost(a) - RISK_W * risk(a)

The action with the highest EU is recommended; the full table is shown in the UI
so the trade-off is visible. Unlike the goal-based agent, this agent can prefer a
cheap, broadly useful action when the evidence is ambiguous.
"""

import math

from core.knowledge import (
    DEPENDENCY_FAILURE,
    DEPLOYMENT_FAILURE,
    FLAKY_INFRA,
    TEST_FAILURE,
)
from agents.base import Decision, checklist_for, evidence_for, sense

HYPOTHESES = [TEST_FAILURE, DEPENDENCY_FAILURE, DEPLOYMENT_FAILURE, FLAKY_INFRA]

BENEFIT = 100.0
COST_W = 0.8    # utility lost per engineer-minute
RISK_W = 60.0   # utility lost per unit of risk
TEMPERATURE = 2.5  # softens the softmax so beliefs are not over-confident

# feature -> {hypothesis: log-odds weight}
EVIDENCE_WEIGHTS = {
    "tests_failed": {TEST_FAILURE: 1.5, FLAKY_INFRA: 1.0},
    "assertion_error": {TEST_FAILURE: 2.0},
    "deterministic_retry": {TEST_FAILURE: 1.5, FLAKY_INFRA: -1.5},
    "change_touches_failing_module": {TEST_FAILURE: 2.0, FLAKY_INFRA: -1.0},
    "timeout_error": {FLAKY_INFRA: 2.0, TEST_FAILURE: 0.3},
    "infra_warning": {FLAKY_INFRA: 1.5},
    "only_docs_changed": {FLAKY_INFRA: 2.0, TEST_FAILURE: -2.0, DEPENDENCY_FAILURE: -1.0},
    "log_truncated": {FLAKY_INFRA: 0.3},
    "dependency_resolution_error": {DEPENDENCY_FAILURE: 4.0},
    "deps_changed": {DEPENDENCY_FAILURE: 1.5},
    "build_failed": {DEPENDENCY_FAILURE: 1.5},
    "health_failed": {DEPLOYMENT_FAILURE: 3.0},
    "error_rate_spike": {DEPLOYMENT_FAILURE: 1.5},
    "config_changed": {DEPLOYMENT_FAILURE: 1.5},
}

# name, cost (min), risk (0..1), value per hypothesis
CANDIDATE_ACTIONS = [
    ("Reproduce failing tests locally against the latest diff", 15, 0.0,
     {TEST_FAILURE: 0.9, FLAKY_INFRA: 0.3}),
    ("Recommend reverting the latest commit (owner decides)", 10, 0.25,
     {TEST_FAILURE: 0.7, DEPENDENCY_FAILURE: 0.6, DEPLOYMENT_FAILURE: 0.4}),
    ("Verify requested package versions on the index and runner Python compatibility", 5, 0.0,
     {DEPENDENCY_FAILURE: 0.95}),
    ("Inspect failing health checks + startup logs and diff runtime config vs previous release", 10, 0.0,
     {DEPLOYMENT_FAILURE: 0.9}),
    ("Recommend immediate production rollback to the release owner", 5, 0.35,
     {DEPLOYMENT_FAILURE: 0.8}),
    ("Re-run failed job on a different runner and check runner/test-DB health", 10, 0.02,
     {FLAKY_INFRA: 0.9, TEST_FAILURE: 0.2}),
    ("Collect full untruncated logs and escalate to the pipeline owner", 20, 0.0,
     {TEST_FAILURE: 0.3, DEPENDENCY_FAILURE: 0.3, DEPLOYMENT_FAILURE: 0.3, FLAKY_INFRA: 0.3}),
]


def features(p: dict) -> dict:
    s = p["signals"]
    return {
        "tests_failed": p["tests_failed"],
        "assertion_error": s["assertion_error"],
        "deterministic_retry": bool(p["failed_on_retry"]),
        "change_touches_failing_module": p["change_touches_failing_module"],
        "timeout_error": s["timeout_error"],
        "infra_warning": s["infra_warning"],
        "only_docs_changed": p["only_docs_changed"],
        "log_truncated": s["log_truncated"],
        "dependency_resolution_error": s["dependency_resolution_error"] or bool(p["dependency_errors"]),
        "deps_changed": p["deps_changed"],
        "build_failed": p["failed_stage"] == "build",
        "health_failed": p["health_failed"],
        "error_rate_spike": p["error_rate_spike"],
        "config_changed": bool(p["config_changes"]) or s["missing_config"],
    }


def beliefs(feats: dict) -> dict:
    scores = {h: 0.0 for h in HYPOTHESES}
    for f, present in feats.items():
        if present:
            for h, w in EVIDENCE_WEIGHTS[f].items():
                scores[h] += w
    z = sum(math.exp(v / TEMPERATURE) for v in scores.values())
    return {h: math.exp(v / TEMPERATURE) / z for h, v in scores.items()}


class UtilityBasedAgent:
    name = "Utility-Based"
    mechanism = "Maximise expected utility = benefit x P(cause) x value - cost - risk"

    def decide(self, scenario: dict) -> Decision:
        p = sense(scenario)
        feats = features(p)
        probs = beliefs(feats)

        table = []
        for name, cost, risk, value in CANDIDATE_ACTIONS:
            exp_value = sum(probs[h] * value.get(h, 0.0) for h in HYPOTHESES)
            eu = BENEFIT * exp_value - COST_W * cost - RISK_W * risk
            table.append({"action": name, "expected_value": round(exp_value, 3), "cost_min": cost,
                          "risk": risk, "expected_utility": round(eu, 1)})
        table.sort(key=lambda r: r["expected_utility"], reverse=True)
        best = table[0]

        category = max(probs, key=probs.get)
        top_p = probs[category]
        trace = [f"Active evidence features: {[f for f, v in feats.items() if v]}"]
        trace.append("Belief P(cause|evidence): " + ", ".join(f"{h}={v:.2f}" for h, v in
                                                             sorted(probs.items(), key=lambda x: -x[1])))
        for r in table[:3]:
            trace.append(f"EU({r['action'][:60]}...) = {r['expected_utility']}")
        trace.append(f"Chosen action maximises EU ({best['expected_utility']}); "
                     f"most probable cause {category} (p={top_p:.2f})")
        if top_p < 0.6:
            trace.append("Belief is uncertain (<0.6) - a broadly informative action is preferred.")

        causes = {
            TEST_FAILURE: "Most probable: a code regression in the recently changed module.",
            DEPENDENCY_FAILURE: "Most probable: an unavailable / Python-incompatible dependency pin.",
            DEPLOYMENT_FAILURE: "Most probable: the release is misconfigured for the target environment.",
            FLAKY_INFRA: "Most probable: a non-deterministic infrastructure problem (runner / test DB), not the code change.",
        }
        return Decision(
            agent=self.name, mechanism=self.mechanism, failure_category=category,
            evidence=evidence_for(category, p), likely_cause=f"{causes[category]} (p={top_p:.2f})",
            next_step=best["action"], verification_checklist=checklist_for(category),
            reasoning=trace, confidence=round(top_p, 2),
            details={"beliefs": {h: round(v, 3) for h, v in probs.items()}, "utility_table": table},
        )