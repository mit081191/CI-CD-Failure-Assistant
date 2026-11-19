"""Run all agents on the same scenario and explain why their decisions differ."""

from collections import Counter

from core.scenarios import SCENARIOS, get_scenario

AGENT_ORDER = ["Simple Reflex", "Model-Based Reflex", "Goal-Based", "Utility-Based", "Learning",
               "LLM (Ollama + tools)"]

MECHANISM_NOTES = {
    "Simple Reflex": "fires the first matching rule on the current percept only - no memory, no history",
    "Model-Based Reflex": "applies rules to an internal state built from run history (last green commit, per-test pass/fail history)",
    "Goal-Based": "searches for the cheapest action plan that confirms the root cause and a fix path",
    "Utility-Based": "weighs probability of each cause against action value, cost and risk",
    "Learning": "uses success/failure counts from past investigations for this failure signature",
    "LLM (Ollama + tools)": "reads tool outputs in natural language and reasons over all evidence; answer is checked against tool output",
}

SCENARIO_NOTES = {
    "A": ("All signals point the same way (assertion errors, deterministic on retry, change touches the "
          "module under test), so all five classical agents agree on the category. They differ in the NEXT STEP: the goal-based "
          "agent picks the first step of its plan (map tests to changed files), the utility-based and learning "
          "agents pick 'reproduce locally' because it has the best expected utility / learned success rate."),
    "B": ("The dependency error text is unambiguous, so even the simple reflex rule R1 is correct. Agents "
          "differ in depth: model-based relates it to the last green commit, goal-based plans index check -> "
          "identify commit -> propose pin, utility-based shows that 'recommend revert' has lower utility "
          "because of its risk."),
    "C": ("Tests passed, so only deployment evidence matters. Reflex agents react to the failed health check; "
          "the utility-based agent explicitly rejects 'immediate rollback' because its risk outweighs its "
          "value compared with diagnosing the config first; the learning agent prefers config diff because "
          "'restart pods' has failed 4/4 times in its experience."),
    "D": ("Edge case. The surface percept 'unit_test failed' misleads the SIMPLE REFLEX agent into blaming the "
          "code. Agents that use more context recover: model-based sees the same test pass and fail on the same "
          "commit (flaky), goal-based can only satisfy its goal via the timeout+infra path, utility-based "
          "weighs 'only README changed' and 'disk 96%' against 'tests failed', and the learning agent's history "
          "for 'unit_test|timeout_error' (5 flaky vs 3 regressions) gives a lower confidence (0.50) that "
          "honestly reflects ambiguity."),
}


def run_classical(scenario_id: str, agents: list) -> dict:
    """Each agent receives its own deep copy of the SAME scenario data."""
    return {a.name: a.decide(get_scenario(scenario_id)) for a in agents}


def comparison_rows(scenario_id: str, decisions: dict) -> list:
    expected = SCENARIOS[scenario_id]["expected_category"]
    rows = []
    for name in AGENT_ORDER:
        d = decisions.get(name)
        if d is None:
            continue
        rows.append({
            "Agent": name,
            "Failure category": d.failure_category,
            "Correct": "yes" if d.failure_category == expected else "no",
            "Confidence": d.confidence,
            "Recommended next step": d.next_step,
            "Likely cause": d.likely_cause,
        })
    return rows


def explain_differences(scenario_id: str, decisions: dict) -> list:
    expected = SCENARIOS[scenario_id]["expected_category"]
    cats = Counter(d.failure_category for d in decisions.values())
    majority, n = cats.most_common(1)[0]
    lines = [f"{n} of {len(decisions)} agents chose **{majority}** (expected: **{expected}**)."]
    wrong = [name for name, d in decisions.items() if d.failure_category != expected]
    if wrong:
        lines.append("Disagreeing / incorrect agents: " + ", ".join(wrong) + ".")
    steps = {d.next_step for d in decisions.values()}
    lines.append(f"{len(steps)} distinct next-step recommendations were produced.")
    lines.append(SCENARIO_NOTES[scenario_id])
    for name in AGENT_ORDER:
        if name in decisions:
            d = decisions[name]
            lines.append(f"- **{name}** {MECHANISM_NOTES[name]} -> {d.failure_category} "
                         f"(confidence {d.confidence}).")
    return lines