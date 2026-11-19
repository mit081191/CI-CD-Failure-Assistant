"""Common pieces shared by all agents: the Decision output and the sensor.

`sense()` converts the raw scenario into *current-run* percepts (what a sensor
can observe right now). It deliberately does NOT look at run history - agents
that keep an internal model (model-based, learning) read history themselves.
"""

import re
from dataclasses import asdict, dataclass, field

from core.knowledge import CATEGORY_LABELS, VERIFICATION_CHECKLISTS

DOC_EXTENSIONS = (".md", ".rst", ".txt")
DOC_PREFIXES = ("docs/",)

LOG_PATTERNS = {
    "dependency_resolution_error": r"No matching distribution|Could not find a version|ResolutionImpossible",
    "python_version_incompatible": r"Requires-Python|requires a different python",
    "assertion_error": r"AssertionError",
    "timeout_error": r"TimeoutError|timed out",
    "connection_error": r"connection to .* (timed out|refused)|Connection refused",
    "readiness_probe_failed": r"Readiness probe failed",
    "missing_config": r"KeyError: '[A-Z_]+'",
    "infra_warning": r"disk usage at 9\d%|out of memory|No space left",
    "log_truncated": r"truncated",
}


@dataclass
class Decision:
    agent: str
    mechanism: str
    failure_category: str
    evidence: list
    likely_cause: str
    next_step: str
    verification_checklist: list
    reasoning: list
    confidence: float
    details: dict = field(default_factory=dict)

    @property
    def category_label(self) -> str:
        return CATEGORY_LABELS.get(self.failure_category, self.failure_category)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category_label"] = self.category_label
        return d


def checklist_for(category: str) -> list:
    return list(VERIFICATION_CHECKLISTS.get(category, VERIFICATION_CHECKLISTS["UNKNOWN"]))


def is_doc_file(path: str) -> bool:
    return path.endswith(DOC_EXTENSIONS) or path.startswith(DOC_PREFIXES)


def sense(scenario: dict) -> dict:
    """Extract current-run percepts from a scenario (no history)."""
    ps = scenario["pipeline_status"]
    logs = scenario["build_logs"]
    tests = scenario["test_results"]
    deps = scenario["dependencies"]
    dep = scenario["deployment"]
    commits = scenario["recent_changes"]["commits"]

    signals = {k: bool(re.search(p, logs, re.IGNORECASE)) for k, p in LOG_PATTERNS.items()}
    matched_lines = {
        k: [ln for ln in logs.splitlines() if re.search(p, ln, re.IGNORECASE)]
        for k, p in LOG_PATTERNS.items()
    }

    changed_files = sorted({f for c in commits for f in c.get("files", [])})
    code_files = [f for f in changed_files if not is_doc_file(f)]
    failing_modules = {f.get("module_under_test") for f in tests.get("failures", [])}
    failing_tests = [f["test"] for f in tests.get("failures", [])]

    failing_checks = [h for h in dep.get("health_checks", []) if h["status"] != "passing"]
    error_rate = dep.get("error_rate_pct")
    baseline = dep.get("baseline_error_rate_pct") or 0

    return {
        "failed_stage": ps.get("failed_stage"),
        "overall": ps.get("overall"),
        "signals": signals,
        "matched_lines": matched_lines,
        "tests_executed": tests.get("executed", False),
        "tests_failed": tests.get("failed", 0) > 0,
        "failed_count": tests.get("failed", 0),
        "failing_tests": failing_tests,
        "failed_on_retry": tests.get("failed_on_retry"),
        "error_types": sorted({f["error_type"] for f in tests.get("failures", [])}),
        "changed_files": changed_files,
        "code_files_changed": code_files,
        "only_docs_changed": bool(changed_files) and not code_files,
        "change_touches_failing_module": bool(failing_modules & set(code_files)),
        "deps_changed": deps.get("changed_in_latest_commit", False),
        "dependency_errors": deps.get("resolution_errors", []),
        "deployment_executed": dep.get("executed", False),
        "health_failed": bool(failing_checks),
        "failing_checks": failing_checks,
        "error_rate_pct": error_rate,
        "error_rate_spike": error_rate is not None and error_rate > max(5 * baseline, 2.0),
        "config_changes": dep.get("config_changes", []),
        "commit": ps.get("commit"),
        "parent_commit": ps.get("parent_commit"),
    }


def first_line(percepts: dict, signal: str) -> str:
    lines = percepts["matched_lines"].get(signal) or []
    return lines[0] if lines else ""


def evidence_for(category: str, p: dict) -> list:
    """Category-specific evidence lines pulled from the percepts (shared helper)."""
    ev = [f"Pipeline failed at stage '{p['failed_stage']}'"]
    if category == "TEST_FAILURE":
        ev += [f"Failing test: {t}" for t in p["failing_tests"]]
        ev.append(first_line(p, "assertion_error"))
        if p["failed_on_retry"]:
            ev.append(f"{p['failed_on_retry']} test(s) failed again on retry (deterministic)")
        if p["change_touches_failing_module"]:
            ev.append(f"Latest change touches module under test: {', '.join(p['code_files_changed'])}")
    elif category == "DEPENDENCY_FAILURE":
        ev += p["dependency_errors"]
        ev.append(first_line(p, "dependency_resolution_error"))
        if p["deps_changed"]:
            ev.append("Dependency manifest changed in the latest commit")
    elif category == "DEPLOYMENT_HEALTH_FAILURE":
        ev += [f"{c['name']}: {c['detail']}" for c in p["failing_checks"]]
        if p["error_rate_pct"] is not None:
            ev.append(f"Error rate {p['error_rate_pct']}% after release")
        ev.append(first_line(p, "missing_config"))
        ev += p["config_changes"]
    elif category == "FLAKY_TEST_OR_CI_INFRA":
        ev += [f"Failing test: {t}" for t in p["failing_tests"]]
        ev.append(first_line(p, "timeout_error"))
        ev.append(first_line(p, "infra_warning"))
        if p["only_docs_changed"]:
            ev.append(f"Only documentation changed: {', '.join(p['changed_files'])}")
        if p["signals"]["log_truncated"]:
            ev.append("Build log is truncated - evidence is incomplete")
    return [e for e in ev if e]