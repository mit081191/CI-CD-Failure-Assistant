"""Shared domain knowledge: failure categories and post-fix verification checklists.

Every agent uses the same category labels so that their decisions can be compared
directly in the UI and in the test report.
"""

TEST_FAILURE = "TEST_FAILURE"
DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
DEPLOYMENT_FAILURE = "DEPLOYMENT_HEALTH_FAILURE"
FLAKY_INFRA = "FLAKY_TEST_OR_CI_INFRA"
UNKNOWN = "UNKNOWN"

CATEGORIES = [TEST_FAILURE, DEPENDENCY_FAILURE, DEPLOYMENT_FAILURE, FLAKY_INFRA, UNKNOWN]

CATEGORY_LABELS = {
    TEST_FAILURE: "Unit/integration test failure (code regression)",
    DEPENDENCY_FAILURE: "Build failure (dependency / version unavailable or incompatible)",
    DEPLOYMENT_FAILURE: "Deployment health-check failure after release",
    FLAKY_INFRA: "Flaky test or CI infrastructure problem (non-deterministic)",
    UNKNOWN: "Unknown - more information needed",
}

VERIFICATION_CHECKLISTS = {
    TEST_FAILURE: [
        "Failing tests pass locally on the fixed commit",
        "Full unit-test suite passes in CI (no new failures)",
        "A regression test covers the corrected behaviour",
        "Code review approved for the fix commit",
    ],
    DEPENDENCY_FAILURE: [
        "Pinned version exists on the package index for the runner's Python version",
        "Lock file regenerated and committed; clean install succeeds from an empty cache",
        "Build stage and full test suite pass with the new pin",
        "Changelog of the dependency checked for breaking changes",
    ],
    DEPLOYMENT_FAILURE: [
        "Readiness and liveness health checks return 200 on all canary pods",
        "Error rate and p95 latency back within baseline for 15+ minutes",
        "Required configuration / environment variables present in the target environment",
        "Rollout resumed (or rolled back) by the release owner and smoke tests pass",
    ],
    FLAKY_INFRA: [
        "Failing job re-run on a healthy runner passes",
        "Test passes repeatedly (e.g. 5 consecutive runs) to confirm stability",
        "Runner / test-service health (disk, DB connectivity) back to normal",
        "Flaky test tracked in an issue; quarantined only with owner approval",
    ],
    UNKNOWN: [
        "Collect complete logs for the failed stage",
        "Confirm which stage failed first and whether it reproduces",
        "Escalate to the pipeline owner with the collected evidence",
    ],
}

SAFETY_NOTE = (
    "Advisory only: the assistant recommends troubleshooting steps; it never changes "
    "code, edits configuration, re-runs deployments or rolls back automatically."
)