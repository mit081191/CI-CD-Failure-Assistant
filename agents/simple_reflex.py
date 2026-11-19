"""Simple Reflex Agent.

Decision mechanism: condition -> action rules evaluated on the CURRENT percept
only. The first rule whose condition matches fires. No memory, no history, no
look-ahead.

Expected weakness: in the edge case (D) the percept "unit_test stage failed"
matches the test-failure rule, so it blames the code even though only README.md
changed and the failure is a timeout. This is the classic limitation of reflex
agents in partially observable environments.
"""

from core.knowledge import (
    DEPENDENCY_FAILURE,
    DEPLOYMENT_FAILURE,
    TEST_FAILURE,
    UNKNOWN,
)
from agents.base import Decision, checklist_for, evidence_for, sense

# (rule name, condition(percepts) -> bool, category, cause, action)
RULES = [
    (
        "R1: dependency error text in log",
        lambda p: p["signals"]["dependency_resolution_error"],
        DEPENDENCY_FAILURE,
        "A required package version cannot be resolved from the package index.",
        "Check the package index for the requested versions and correct the pin in the manifest.",
    ),
    (
        "R2: test stage failed",
        lambda p: p["failed_stage"] == "unit_test" or p["tests_failed"],
        TEST_FAILURE,
        "Recent code change broke one or more tests.",
        "Open the failing test output and compare it with the latest code change.",
    ),
    (
        "R3: health check failed",
        lambda p: p["health_failed"] or p["failed_stage"] == "health_check",
        DEPLOYMENT_FAILURE,
        "The new release is unhealthy in the target environment.",
        "Inspect the failing health-check endpoints and application startup logs.",
    ),
]


class SimpleReflexAgent:
    name = "Simple Reflex"
    mechanism = "Ordered condition-action rules on the current percept (no memory)"

    def decide(self, scenario: dict) -> Decision:
        p = sense(scenario)
        trace = []
        for rule_name, cond, category, cause, action in RULES:
            matched = cond(p)
            trace.append(f"{rule_name} -> {'MATCH' if matched else 'no match'}")
            if matched:
                trace.append("First matching rule fires; remaining rules are not evaluated.")
                return Decision(
                    agent=self.name,
                    mechanism=self.mechanism,
                    failure_category=category,
                    evidence=evidence_for(category, p),
                    likely_cause=cause,
                    next_step=action,
                    verification_checklist=checklist_for(category),
                    reasoning=trace,
                    confidence=0.6,  # fixed: reflex rules have no notion of certainty
                    details={"fired_rule": rule_name},
                )
        trace.append("No rule matched - default action.")
        return Decision(
            agent=self.name,
            mechanism=self.mechanism,
            failure_category=UNKNOWN,
            evidence=[f"Pipeline failed at stage '{p['failed_stage']}'"],
            likely_cause="No rule covers this situation.",
            next_step="Collect full logs for the failed stage and escalate to the pipeline owner.",
            verification_checklist=checklist_for(UNKNOWN),
            reasoning=trace,
            confidence=0.2,
            details={"fired_rule": None},
        )