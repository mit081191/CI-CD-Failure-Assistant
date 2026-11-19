"""Read-only investigation tools over a scenario.

These functions are the *only* way the LLM agent can see the scenario: it must
call them (via LangChain tool calling) and ground its answer in what they return.
None of them modify code, configuration or deployments.
"""

import json


def get_pipeline_status(scenario: dict) -> dict:
    """Overall pipeline result, failed stage and per-stage statuses."""
    return scenario["pipeline_status"]


def read_build_logs(scenario: dict, max_lines: int = 50) -> dict:
    """Last `max_lines` lines of the build/deploy log for the failed run."""
    lines = scenario["build_logs"].splitlines()
    return {
        "run_id": scenario["pipeline_status"]["run_id"],
        "line_count": len(lines),
        "truncated_by_tool": len(lines) > max_lines,
        "lines": lines[-max_lines:],
    }


def get_test_results(scenario: dict) -> dict:
    """Test totals, failing tests with error type/message, retry outcome."""
    return scenario["test_results"]


def get_recent_change_summary(scenario: dict) -> dict:
    """Commits since the last green run, with files touched and diff hints."""
    return scenario["recent_changes"]


def get_dependency_info(scenario: dict) -> dict:
    """Dependency manifest, runner Python version, resolution errors."""
    return scenario["dependencies"]


def get_deployment_health(scenario: dict) -> dict:
    """Deployment status, health checks, error rate vs baseline, config changes."""
    return scenario["deployment"]


def get_run_history(scenario: dict) -> dict:
    """Recent previous runs of the same pipeline (newest first)."""
    return {"runs": scenario["run_history"]}


TOOL_FUNCTIONS = {
    "get_pipeline_status": get_pipeline_status,
    "read_build_logs": read_build_logs,
    "get_test_results": get_test_results,
    "get_recent_change_summary": get_recent_change_summary,
    "get_dependency_info": get_dependency_info,
    "get_deployment_health": get_deployment_health,
    "get_run_history": get_run_history,
}


def call_tool(name: str, scenario: dict) -> str:
    """Run a tool and return its JSON string output (what the LLM sees)."""
    return json.dumps(TOOL_FUNCTIONS[name](scenario), indent=1)