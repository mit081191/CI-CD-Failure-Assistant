"""Five classical agents for CI/CD failure diagnosis."""
from copy import deepcopy
import json
import os

HEALTHY = "Healthy - no failure"

def _base(category, cause, action, evidence, reasoning, confidence=0.75):
    if category == HEALTHY:
        checklist = [
            "Confirm every pipeline stage reports success.",
            "Spot-check post-deployment health checks and application logs.",
            "Record this run as the last known-good baseline."
        ]
    else:
        checklist = [
            "Apply the proposed fix in a separate branch or controlled environment.",
            "Re-run the relevant build and automated tests.",
            "Confirm deployment health checks and application logs are healthy.",
            "Review the pipeline result before approving any release."
        ]
    return {
        "failure_category": category,
        "likely_cause": cause,
        "recommended_next_step": action,
        "supporting_evidence": evidence,
        "reasoning": reasoning,
        "verification_checklist": checklist,
        "confidence": confidence
    }

def _classify(s):
    # Match explicit failure evidence, not benign mentions such as "dependencies installed successfully".
    build = str(s.get("build_logs", "")).lower()
    tests = str(s.get("test_results", "")).lower()
    deps = str(s.get("dependency_info", "")).lower()
    health = str(s.get("deployment_health", "")).lower()
    status = str(s.get("pipeline_status", "")).lower()

    # Normal run: the pipeline reports success and nothing reports a failure.
    if ("succeeded" in status or "passed" in status) and "fail" not in status:
        return "healthy"
    if any(k in health for k in ["health check", "readiness probe", "deployment unhealthy", "http 503"]):
        return "deployment_health"
    if any(k in build + " " + deps for k in ["no matching distribution", "version not found", "could not resolve", "dependency resolution failed", "incompatible version", "failed to install"]):
        return "dependency"
    if any(k in tests + " " + build for k in ["assertionerror", "test failed", "tests failed", "failed tests", "pytest:", "unit test failure"]):
        return "test_regression"
    if "dependency" in status and "failed" in status:
        return "dependency"
    return "ambiguous"

class SimpleReflexAgent:
    name = "Simple Reflex"
    def decide(self, scenario):
        s = deepcopy(scenario)
        category = _classify(s)
        rules = {
            "healthy": (HEALTHY, "No failure signal is present; all stages passed.", "No corrective action needed; continue normal monitoring."),
            "test_regression": ("Test regression", "A recent code change likely introduced a behavior regression.", "Inspect the failing assertion and the latest changed function; reproduce the failure locally."),
            "dependency": ("Dependency/build failure", "A required package version cannot be resolved or is incompatible.", "Check the package index, lockfile, Python version, and supported dependency constraints."),
            "deployment_health": ("Deployment/runtime health failure", "The deployed service is not passing its health or readiness checks.", "Inspect application startup logs, readiness endpoint configuration, environment variables, and service connectivity."),
            "ambiguous": ("Unclassified pipeline failure", "The available signals do not uniquely identify the failure.", "Collect the full failing job log, test report, dependency lockfile, and deployment events before changing anything.")
        }
        c, cause, action = rules[category]
        return _base(c, cause, action, [s.get("build_logs", ""), s.get("test_results", "")], f"Matched the scenario against fixed condition-action rules. Classified signal: {category}.", 0.65 if category == "ambiguous" else 0.82)

class ModelBasedReflexAgent:
    name = "Model-Based Reflex"
    def decide(self, scenario):
        s = deepcopy(scenario)
        category = _classify(s)
        history = s.get("recent_change_summary", "No recent change summary supplied.")
        status = s.get("pipeline_status", "Unknown")
        mapping = {
            "healthy": (HEALTHY, "Every stage in the internal pipeline model reports success, and the recent change did not affect build, tests, or deployment.", "No action needed; keep this run as the new last-known-good baseline."),
            "test_regression": ("Test regression", "The failure appeared in the test stage and is temporally associated with a code change.", "Compare the failing test and changed files with the last successful commit; isolate the smallest regression."),
            "dependency": ("Dependency/build failure", "The build environment cannot obtain or use the declared dependency.", "Compare the lockfile with the last successful build and verify package/version availability in the configured registry."),
            "deployment_health": ("Deployment/runtime health failure", "The test stage passed, but the deployed service failed runtime health validation.", "Compare release configuration and runtime logs with the previous healthy release; inspect probes and external dependencies."),
            "ambiguous": ("Unclassified pipeline failure", "The internal state model lacks enough observations to identify a single failure stage.", "Gather stage-level timestamps, complete logs, and the last known-good pipeline state.")
        }
        c, cause, action = mapping[category]
        return _base(c, cause, action, [f"Pipeline status: {status}", f"Recent changes: {history}", f"Build log: {s.get('build_logs','')}"], "Maintained a simple internal model of pipeline stages and combined current observations with recent-change context.", 0.86 if category != "ambiguous" else 0.55)

class GoalBasedAgent:
    name = "Goal-Based"
    def decide(self, scenario):
        s = deepcopy(scenario)
        category = _classify(s)
        goals = {
            "healthy": (HEALTHY, "The safe-recovery goal is already satisfied: the pipeline is green and the service is healthy.", "No action needed; proceed with normal release review."),
            "test_regression": ("Test regression", "Restore a passing, trustworthy test suite without masking the failure.", "Reproduce the failing unit test, inspect the changed code path, and create a focused regression fix."),
            "dependency": ("Dependency/build failure", "Produce a reproducible build with resolvable, compatible dependencies.", "Validate the requested version against the package registry and runtime; update constraints/lockfile only after confirming compatibility."),
            "deployment_health": ("Deployment/runtime health failure", "Restore service health while preserving release safety.", "Inspect readiness/liveness probe results and application startup logs; compare runtime configuration with the last healthy release."),
            "ambiguous": ("Unclassified pipeline failure", "Reduce uncertainty before taking corrective action.", "Collect missing diagnostics and identify the first failing pipeline stage.")
        }
        c, goal, action = goals[category]
        return _base(c, "The next step is selected to satisfy the operational goal: " + goal, action, [s.get("pipeline_status",""), s.get("test_results",""), s.get("deployment_health","")], "Selected an action by evaluating which step best advances the explicit recovery goal while avoiding unverified changes.", 0.84 if category != "ambiguous" else 0.5)

class UtilityBasedAgent:
    name = "Utility-Based"
    def decide(self, scenario):
        s = deepcopy(scenario)
        category = _classify(s)
        # Transparent heuristic utility: diagnostic value + risk reduction - effort.
        choices = {
            "healthy": (HEALTHY, "Take no corrective action; continue routine monitoring.", "With no failure present, any intervention adds risk and effort with no diagnostic gain, so doing nothing has the highest utility."),
            "test_regression": ("Test regression", "Inspect the failing test and changed code first.", "High diagnostic value, low operational risk, and moderate effort make targeted test investigation the best utility choice."),
            "dependency": ("Dependency/build failure", "Verify package availability and compatibility before editing dependency constraints.", "Registry and compatibility checks have high diagnostic value and low risk compared with blindly upgrading packages."),
            "deployment_health": ("Deployment/runtime health failure", "Inspect readiness failures and application startup logs; compare runtime configuration with the previous healthy release.", "This prioritizes service safety and diagnostic value while avoiding an automatic rollback or redeployment."),
            "ambiguous": ("Unclassified pipeline failure", "Gather complete stage logs and identify the first failing stage.", "When evidence is weak, information gathering has higher expected utility than a speculative fix.")
        }
        c, action, why = choices[category]
        cause = ("No failure detected; all observed signals are healthy." if category == "healthy"
                 else "Most likely cause associated with the observed " + category.replace("_", " ") + " signals.")
        return _base(c, cause, action, [s.get("build_logs",""), s.get("test_results",""), s.get("dependency_info",""), s.get("deployment_health","")], why + " The heuristic favors evidence, reversibility, and low risk.", 0.8 if category != "ambiguous" else 0.45)

class LearningAgent:
    name = "Learning Agent"
    def __init__(self, experience_path="data/experience.json"):
        self.experience_path = experience_path
        self.experience = self._load()

    def _load(self):
        try:
            with open(self.experience_path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self):
        os_dir = __import__("os").path.dirname(self.experience_path)
        if os_dir:
            __import__("os").makedirs(os_dir, exist_ok=True)
        with open(self.experience_path, "w", encoding="utf-8") as f:
            json.dump(self.experience, f, indent=2)

    def record_outcome(self, category, success):
        item = self.experience.setdefault(category, {"success": 0, "failure": 0})
        item["success" if success else "failure"] += 1
        self._save()

    def decide(self, scenario):
        s = deepcopy(scenario)
        category = _classify(s)
        item = self.experience.get(category, {"success": 0, "failure": 0})
        successes, failures = item.get("success", 0), item.get("failure", 0)
        total = successes + failures
        success_rate = (successes + 1) / (total + 2)  # Laplace-smoothed estimate
        actions = {
            "healthy": (HEALTHY, "No corrective action needed; continue normal monitoring."),
            "test_regression": ("Test regression", "Reproduce the failing unit test and inspect the recent code diff."),
            "dependency": ("Dependency/build failure", "Verify package registry availability, runtime compatibility, and lockfile consistency."),
            "deployment_health": ("Deployment/runtime health failure", "Inspect startup logs, readiness probes, and configuration differences from the last healthy release."),
            "ambiguous": ("Unclassified pipeline failure", "Gather missing stage-level evidence before choosing a fix.")
        }
        c, default_action = actions[category]
        action = default_action
        if total and success_rate < 0.5:
            action = "Prior attempts for this category have had a low success rate. First gather additional diagnostics, then perform a small reversible investigation: " + default_action.lower()
        elif total and success_rate >= 0.75:
            action = "Prior experience has been mostly successful for this category. Follow the proven diagnostic approach: " + default_action.lower()
        reasoning = (f"Experience for '{category}': {successes} successes, {failures} failures; "
                     f"Laplace-smoothed success estimate = {success_rate:.2f}. "
                     "This history adjusts how cautious the recommended next step is.")
        cause = ("No failure detected in the current signals." if category == "healthy"
                 else "Likely cause inferred from current signals; past outcomes influence the investigation strategy.")
        result = _base(c, cause, action,
                       [s.get("build_logs",""), s.get("test_results",""), s.get("dependency_info",""), s.get("deployment_health","")],
                       reasoning, round(min(0.9, 0.55 + success_rate * 0.35), 2))
        result["experience"] = {"success": successes, "failure": failures, "estimated_success_rate": round(success_rate, 2)}
        return result
