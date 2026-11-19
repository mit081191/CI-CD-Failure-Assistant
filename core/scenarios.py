"""Shared scenario data.

All six agents receive exactly the same scenario dictionary (deep-copied) so that
their decisions can be compared fairly. Each scenario represents one failed
pipeline run with: pipeline status, build logs, test results, dependency info,
recent code changes, deployment/health data and recent run history.

Scenarios
---------
A  Normal case     - unit tests fail after a code change.
B  Failure case    - build fails: pinned dependency version unavailable/incompatible.
C  Critical case   - tests pass, but deployment health checks fail after release.
D  Edge/ambiguous  - integration test times out on a docs-only commit; logs are
                     truncated and the same test has failed intermittently before.
"""

import copy

from core.knowledge import (
    DEPENDENCY_FAILURE,
    DEPLOYMENT_FAILURE,
    FLAKY_INFRA,
    TEST_FAILURE,
)

SCENARIOS = {
    # ------------------------------------------------------------------ A
    "A": {
        "id": "A",
        "name": "A - Unit tests fail after a code change",
        "type": "normal",
        "description": (
            "A developer changed the discount logic in the pricing module. Build "
            "succeeds but two unit tests in tests/test_pricing.py fail."
        ),
        "expected_category": TEST_FAILURE,
        "pipeline_status": {
            "pipeline": "shop-api / main",
            "run_id": 4812,
            "branch": "main",
            "commit": "a91f3c2",
            "parent_commit": "7d02be1",
            "trigger": "push",
            "overall": "failed",
            "failed_stage": "unit_test",
            "stages": [
                {"name": "checkout", "status": "success", "duration_s": 4},
                {"name": "build", "status": "success", "duration_s": 62},
                {"name": "unit_test", "status": "failed", "duration_s": 48},
                {"name": "package", "status": "skipped", "duration_s": 0},
                {"name": "deploy_canary", "status": "skipped", "duration_s": 0},
                {"name": "health_check", "status": "skipped", "duration_s": 0},
            ],
        },
        "build_logs": "\n".join([
            "[12:01:02] Checking out commit a91f3c2 (main)",
            "[12:01:06] Installing dependencies from requirements.lock",
            "[12:02:05] Successfully installed 48 packages",
            "[12:02:08] Build OK: wheel shop_api-2.7.1-py3-none-any.whl created",
            "[12:02:10] Running: pytest tests/ -q --maxfail=20",
            "[12:02:55] FAILED tests/test_pricing.py::test_apply_discount - AssertionError: assert 81.0 == 90.0",
            "[12:02:56] FAILED tests/test_pricing.py::test_bulk_order_discount - AssertionError: assert 729.0 == 810.0",
            "[12:02:58] ========== 2 failed, 186 passed in 45.31s ==========",
            "[12:02:58] Retrying failed tests once (--last-failed)",
            "[12:03:01] FAILED tests/test_pricing.py::test_apply_discount - AssertionError: assert 81.0 == 90.0",
            "[12:03:01] FAILED tests/test_pricing.py::test_bulk_order_discount - AssertionError: assert 729.0 == 810.0",
            "[12:03:02] ERROR: Stage unit_test failed with exit code 1",
        ]),
        "test_results": {
            "executed": True,
            "total": 188,
            "passed": 186,
            "failed": 2,
            "skipped": 0,
            "failed_on_retry": 2,
            "failures": [
                {
                    "test": "tests/test_pricing.py::test_apply_discount",
                    "error_type": "AssertionError",
                    "message": "assert 81.0 == 90.0",
                    "module_under_test": "shop_api/pricing.py",
                },
                {
                    "test": "tests/test_pricing.py::test_bulk_order_discount",
                    "error_type": "AssertionError",
                    "message": "assert 729.0 == 810.0",
                    "module_under_test": "shop_api/pricing.py",
                },
            ],
        },
        "dependencies": {
            "manifest": "requirements.lock",
            "changed_in_latest_commit": False,
            "runner_python": "3.11",
            "resolution_errors": [],
            "packages": [
                {"name": "fastapi", "requested": "0.115.4", "status": "ok"},
                {"name": "pydantic", "requested": "2.9.2", "status": "ok"},
            ],
        },
        "recent_changes": {
            "summary": "1 commit since last green run: discount calculation refactor in pricing module.",
            "commits": [
                {
                    "sha": "a91f3c2",
                    "author": "dev.ravi",
                    "message": "Refactor discount calculation to support stacked promotions",
                    "files": ["shop_api/pricing.py"],
                    "lines_added": 24,
                    "lines_removed": 11,
                    "diff_hint": "price = price * (1 - discount) applied inside loop over promotions",
                }
            ],
        },
        "deployment": {
            "executed": False,
            "environment": "production",
            "previous_version": "2.7.0",
            "new_version": None,
            "health_checks": [],
            "error_rate_pct": None,
            "baseline_error_rate_pct": 0.4,
            "config_changes": [],
        },
        "run_history": [
            {"run_id": 4811, "commit": "7d02be1", "overall": "success", "failed_stage": None, "failed_tests": []},
            {"run_id": 4810, "commit": "5be9a07", "overall": "success", "failed_stage": None, "failed_tests": []},
            {"run_id": 4809, "commit": "11c4d8e", "overall": "success", "failed_stage": None, "failed_tests": []},
        ],
    },
    # ------------------------------------------------------------------ B
    "B": {
        "id": "B",
        "name": "B - Build fails: dependency version unavailable/incompatible",
        "type": "failure",
        "description": (
            "A commit bumped orjson to 3.12.9, which does not exist on the package "
            "index, and pinned numpy 2.3.1, which needs Python >= 3.11 while the CI "
            "runner uses Python 3.10. The build stage fails during dependency install."
        ),
        "expected_category": DEPENDENCY_FAILURE,
        "pipeline_status": {
            "pipeline": "shop-api / main",
            "run_id": 4820,
            "branch": "main",
            "commit": "c3e77a0",
            "parent_commit": "a1b9e44",
            "trigger": "push",
            "overall": "failed",
            "failed_stage": "build",
            "stages": [
                {"name": "checkout", "status": "success", "duration_s": 4},
                {"name": "build", "status": "failed", "duration_s": 37},
                {"name": "unit_test", "status": "skipped", "duration_s": 0},
                {"name": "package", "status": "skipped", "duration_s": 0},
                {"name": "deploy_canary", "status": "skipped", "duration_s": 0},
                {"name": "health_check", "status": "skipped", "duration_s": 0},
            ],
        },
        "build_logs": "\n".join([
            "[09:14:01] Checking out commit c3e77a0 (main)",
            "[09:14:05] Python 3.10.14 detected on runner ci-runner-03",
            "[09:14:05] Installing dependencies from requirements.txt",
            "[09:14:31] ERROR: Ignored the following versions that require a different python version: 2.3.0 Requires-Python >=3.11; 2.3.1 Requires-Python >=3.11",
            "[09:14:31] ERROR: Could not find a version that satisfies the requirement numpy==2.3.1 (from versions: 1.26.4, 2.0.2, 2.1.3, 2.2.6)",
            "[09:14:32] ERROR: Could not find a version that satisfies the requirement orjson==3.12.9 (from versions: 3.10.7, 3.10.12, 3.10.15)",
            "[09:14:32] ERROR: No matching distribution found for orjson==3.12.9",
            "[09:14:38] ERROR: Stage build failed with exit code 1",
        ]),
        "test_results": {
            "executed": False,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "failed_on_retry": 0,
            "failures": [],
        },
        "dependencies": {
            "manifest": "requirements.txt",
            "changed_in_latest_commit": True,
            "runner_python": "3.10",
            "resolution_errors": [
                "orjson==3.12.9: no matching distribution (latest available 3.10.15)",
                "numpy==2.3.1: requires Python >=3.11, runner has 3.10",
            ],
            "packages": [
                {"name": "orjson", "requested": "3.12.9", "previous": "3.10.7", "status": "unavailable",
                 "available_versions": ["3.10.7", "3.10.12", "3.10.15"]},
                {"name": "numpy", "requested": "2.3.1", "previous": "2.1.3", "status": "incompatible",
                 "available_versions": ["1.26.4", "2.0.2", "2.1.3", "2.2.6"], "requires_python": ">=3.11"},
                {"name": "fastapi", "requested": "0.115.4", "status": "ok"},
            ],
        },
        "recent_changes": {
            "summary": "1 commit since last green run: dependency bumps in requirements.txt.",
            "commits": [
                {
                    "sha": "c3e77a0",
                    "author": "dev.meera",
                    "message": "chore: bump orjson and numpy to latest",
                    "files": ["requirements.txt"],
                    "lines_added": 2,
                    "lines_removed": 2,
                    "diff_hint": "orjson==3.10.7 -> 3.12.9 ; numpy==2.1.3 -> 2.3.1",
                }
            ],
        },
        "deployment": {
            "executed": False,
            "environment": "production",
            "previous_version": "2.7.1",
            "new_version": None,
            "health_checks": [],
            "error_rate_pct": None,
            "baseline_error_rate_pct": 0.4,
            "config_changes": [],
        },
        "run_history": [
            {"run_id": 4819, "commit": "a1b9e44", "overall": "success", "failed_stage": None, "failed_tests": []},
            {"run_id": 4818, "commit": "f02c6d1", "overall": "success", "failed_stage": None, "failed_tests": []},
        ],
    },
    # ------------------------------------------------------------------ C
    "C": {
        "id": "C",
        "name": "C - Tests pass, deployment health checks fail after release",
        "type": "critical",
        "description": (
            "Release 2.8.0 passed build and all tests and was rolled out to a 10% "
            "canary. Readiness checks fail with HTTP 503 and the error rate spikes. "
            "The release renamed an environment variable that the production "
            "manifest still sets under the old name."
        ),
        "expected_category": DEPLOYMENT_FAILURE,
        "pipeline_status": {
            "pipeline": "shop-api / main",
            "run_id": 4831,
            "branch": "main",
            "commit": "e5d2f19",
            "parent_commit": "c9a0b37",
            "trigger": "tag v2.8.0",
            "overall": "failed",
            "failed_stage": "health_check",
            "stages": [
                {"name": "checkout", "status": "success", "duration_s": 4},
                {"name": "build", "status": "success", "duration_s": 64},
                {"name": "unit_test", "status": "success", "duration_s": 51},
                {"name": "package", "status": "success", "duration_s": 22},
                {"name": "deploy_canary", "status": "success", "duration_s": 95},
                {"name": "health_check", "status": "failed", "duration_s": 300},
            ],
        },
        "build_logs": "\n".join([
            "[15:30:02] Checking out tag v2.8.0 (e5d2f19)",
            "[15:31:06] Build OK: image registry.local/shop-api:2.8.0 pushed",
            "[15:32:00] ========== 194 passed in 49.80s ==========",
            "[15:33:40] Deploying shop-api:2.8.0 to production canary (10% traffic)",
            "[15:33:41] Rollout started: 2/20 pods updated",
            "[15:34:10] pod shop-api-7f9c-x2k: Readiness probe failed: HTTP probe failed with statuscode: 503",
            "[15:34:12] pod shop-api-7f9c-x2k: app log: KeyError: 'PAYMENT_GATEWAY_URL' in shop_api/settings.py line 42",
            "[15:34:15] pod shop-api-7f9c-q8m: Readiness probe failed: HTTP probe failed with statuscode: 503",
            "[15:38:40] Canary analysis: error_rate=34.2% (baseline 0.4%), p95_latency=2900ms (baseline 180ms)",
            "[15:38:41] ERROR: Health gate failed - rollout paused at 10%. Manual decision required.",
        ]),
        "test_results": {
            "executed": True,
            "total": 194,
            "passed": 194,
            "failed": 0,
            "skipped": 0,
            "failed_on_retry": 0,
            "failures": [],
        },
        "dependencies": {
            "manifest": "requirements.lock",
            "changed_in_latest_commit": False,
            "runner_python": "3.11",
            "resolution_errors": [],
            "packages": [
                {"name": "fastapi", "requested": "0.115.4", "status": "ok"},
                {"name": "pydantic-settings", "requested": "2.6.1", "status": "ok"},
            ],
        },
        "recent_changes": {
            "summary": "3 commits in release 2.8.0, including a settings refactor that renamed PAYMENT_API_URL to PAYMENT_GATEWAY_URL.",
            "commits": [
                {
                    "sha": "e5d2f19",
                    "author": "dev.arjun",
                    "message": "Release 2.8.0",
                    "files": ["CHANGELOG.md", "pyproject.toml"],
                    "lines_added": 9,
                    "lines_removed": 1,
                },
                {
                    "sha": "d71b2aa",
                    "author": "dev.arjun",
                    "message": "Refactor settings: rename PAYMENT_API_URL to PAYMENT_GATEWAY_URL",
                    "files": ["shop_api/settings.py", "tests/conftest.py"],
                    "lines_added": 14,
                    "lines_removed": 9,
                    "diff_hint": "os.environ['PAYMENT_GATEWAY_URL'] (no default); tests set the variable in conftest.py",
                },
                {
                    "sha": "b44e0c3",
                    "author": "dev.sneha",
                    "message": "Add order export endpoint",
                    "files": ["shop_api/routes/orders.py", "tests/test_orders.py"],
                    "lines_added": 88,
                    "lines_removed": 3,
                },
            ],
        },
        "deployment": {
            "executed": True,
            "environment": "production",
            "previous_version": "2.7.1",
            "new_version": "2.8.0",
            "rollout": "canary 10% - paused",
            "health_checks": [
                {"name": "liveness /healthz", "status": "passing", "detail": "200 OK"},
                {"name": "readiness /ready", "status": "failing", "detail": "503 on 2/2 canary pods"},
                {"name": "smoke test POST /checkout", "status": "failing", "detail": "500 Internal Server Error"},
            ],
            "error_rate_pct": 34.2,
            "baseline_error_rate_pct": 0.4,
            "p95_latency_ms": 2900,
            "baseline_p95_latency_ms": 180,
            "config_changes": [
                "Application now reads PAYMENT_GATEWAY_URL; production manifest still defines PAYMENT_API_URL",
            ],
        },
        "run_history": [
            {"run_id": 4830, "commit": "c9a0b37", "overall": "success", "failed_stage": None, "failed_tests": [],
             "deployed_version": "2.7.1", "health": "healthy"},
            {"run_id": 4829, "commit": "b44e0c3", "overall": "success", "failed_stage": None, "failed_tests": []},
        ],
    },
    # ------------------------------------------------------------------ D
    "D": {
        "id": "D",
        "name": "D - Edge case: intermittent timeout on a docs-only commit",
        "type": "edge",
        "description": (
            "An integration test times out connecting to the test database on a "
            "commit that changed only README.md. Logs are truncated, the runner "
            "reports low disk space, and the same test has failed intermittently in "
            "recent runs (including once on the same commit). The surface signal "
            "'tests failed' is misleading."
        ),
        "expected_category": FLAKY_INFRA,
        "pipeline_status": {
            "pipeline": "shop-api / main",
            "run_id": 4842,
            "branch": "main",
            "commit": "f81aa05",
            "parent_commit": "e5d2f19",
            "trigger": "push",
            "overall": "failed",
            "failed_stage": "unit_test",
            "stages": [
                {"name": "checkout", "status": "success", "duration_s": 5},
                {"name": "build", "status": "success", "duration_s": 66},
                {"name": "unit_test", "status": "failed", "duration_s": 212},
                {"name": "package", "status": "skipped", "duration_s": 0},
                {"name": "deploy_canary", "status": "skipped", "duration_s": 0},
                {"name": "health_check", "status": "skipped", "duration_s": 0},
            ],
        },
        "build_logs": "\n".join([
            "[18:20:01] Checking out commit f81aa05 (main) on runner ci-runner-07",
            "[18:20:02] WARNING: runner ci-runner-07 disk usage at 96%",
            "[18:21:07] Build OK",
            "[18:21:09] Running: pytest tests/ -q",
            "[18:24:38] FAILED tests/integration/test_order_sync.py::test_sync_orders_to_warehouse - TimeoutError: connection to postgres-test:5432 timed out after 30s",
            "[18:24:40] ========== 1 failed, 193 passed in 209.12s ==========",
            "[18:24:41] ... log output truncated (exceeded 4 MB limit) ...",
            "[18:24:41] ERROR: Stage unit_test failed with exit code 1",
        ]),
        "test_results": {
            "executed": True,
            "total": 194,
            "passed": 193,
            "failed": 1,
            "skipped": 0,
            "failed_on_retry": None,  # retry did not run - unknown
            "failures": [
                {
                    "test": "tests/integration/test_order_sync.py::test_sync_orders_to_warehouse",
                    "error_type": "TimeoutError",
                    "message": "connection to postgres-test:5432 timed out after 30s",
                    "module_under_test": "shop_api/sync/warehouse.py",
                }
            ],
        },
        "dependencies": {
            "manifest": "requirements.lock",
            "changed_in_latest_commit": False,
            "runner_python": "3.11",
            "resolution_errors": [],
            "packages": [
                {"name": "psycopg", "requested": "3.2.3", "status": "ok"},
                {"name": "fastapi", "requested": "0.115.4", "status": "ok"},
            ],
        },
        "recent_changes": {
            "summary": "1 commit since last run: documentation-only change to README.md.",
            "commits": [
                {
                    "sha": "f81aa05",
                    "author": "dev.kiran",
                    "message": "docs: update local setup instructions",
                    "files": ["README.md"],
                    "lines_added": 12,
                    "lines_removed": 4,
                }
            ],
        },
        "deployment": {
            "executed": False,
            "environment": "production",
            "previous_version": "2.8.0",
            "new_version": None,
            "health_checks": [],
            "error_rate_pct": None,
            "baseline_error_rate_pct": 0.4,
            "config_changes": [],
        },
        "run_history": [
            {"run_id": 4841, "commit": "f81aa05", "overall": "success", "failed_stage": None, "failed_tests": [],
             "note": "manual re-run of the same commit on ci-runner-02 passed"},
            {"run_id": 4840, "commit": "e5d2f19", "overall": "failed", "failed_stage": "unit_test",
             "failed_tests": ["tests/integration/test_order_sync.py::test_sync_orders_to_warehouse"],
             "runner": "ci-runner-07"},
            {"run_id": 4839, "commit": "e5d2f19", "overall": "success", "failed_stage": None, "failed_tests": []},
            {"run_id": 4836, "commit": "c9a0b37", "overall": "failed", "failed_stage": "unit_test",
             "failed_tests": ["tests/integration/test_order_sync.py::test_sync_orders_to_warehouse"],
             "runner": "ci-runner-07"},
            {"run_id": 4835, "commit": "c9a0b37", "overall": "success", "failed_stage": None, "failed_tests": []},
        ],
    },
}

SCENARIO_IDS = list(SCENARIOS.keys())


def get_scenario(scenario_id: str) -> dict:
    """Return an independent deep copy so no agent can mutate shared input."""
    return copy.deepcopy(SCENARIOS[scenario_id])