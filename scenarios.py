"""Fixed, reproducible scenarios shared by every agent: one normal run, three failures, one ambiguous edge case."""
SCENARIOS = {
    "N - Normal: pipeline succeeds": {
        "scenario_id": "N",
        "pipeline_status": "SUCCEEDED - all stages passed",
        "build_logs": "Build successful. Release image created and pushed successfully.",
        "test_results": "120 passed, 0 failed. Integration tests passed against test environment.",
        "dependency_info": "Dependencies installed successfully and lockfile is unchanged.",
        "recent_change_summary": "Commit jkl012 updated README wording and a log message. No dependency or configuration changes.",
        "deployment_health": "Deployment completed. Readiness and liveness probes passing; GET /health returned HTTP 200."
    },
    "A - Unit tests fail after code change": {
        "scenario_id": "A",
        "pipeline_status": "FAILED at unit-test stage",
        "build_logs": "Build completed successfully. pytest: 2 failed, 118 passed. AssertionError: expected total=120, got total=100.",
        "test_results": "FAILED tests/test_invoice.py::test_total_includes_tax. Expected 120.00 but received 100.00.",
        "dependency_info": "All dependencies installed successfully; no dependency resolution errors.",
        "recent_change_summary": "Commit abc123 changed calculate_total() and modified tax calculation from inclusive to exclusive.",
        "deployment_health": "Deployment not started because the test stage failed."
    },
    "B - Dependency/version unavailable": {
        "scenario_id": "B",
        "pipeline_status": "FAILED at dependency installation stage",
        "build_logs": "ERROR: Could not find a version that satisfies the requirement fastapi==99.0.0. No matching distribution found.",
        "test_results": "Tests were not executed because dependency installation failed.",
        "dependency_info": "requirements.txt pins fastapi==99.0.0; configured package index has no matching release.",
        "recent_change_summary": "Commit def456 updated the FastAPI pin to 99.0.0. No application source files changed.",
        "deployment_health": "Deployment not started."
    },
    "C - Tests pass, deployment health checks fail": {
        "scenario_id": "C",
        "pipeline_status": "FAILED after release during deployment health checks",
        "build_logs": "Build successful. All unit and integration tests passed. Release image created successfully.",
        "test_results": "120 passed, 0 failed. Integration tests passed against test environment.",
        "dependency_info": "Dependencies installed successfully and lockfile is unchanged.",
        "recent_change_summary": "Commit ghi789 changed the container startup command and renamed the PORT environment variable.",
        "deployment_health": "Readiness probe failed repeatedly. GET /health returned HTTP 503. Container logs show application listening on 8000 while probe targets 8080."
    },
    "D - Ambiguous edge case": {
        "scenario_id": "D",
        "pipeline_status": "FAILED; stage attribution unavailable",
        "build_logs": "Pipeline marked failed. Log excerpt is truncated: 'process exited with code 1'.",
        "test_results": "No test report was attached.",
        "dependency_info": "Dependency installation output unavailable.",
        "recent_change_summary": "Several files changed; commit summary is unavailable.",
        "deployment_health": "Unknown; no health-check data supplied."
    }
}
