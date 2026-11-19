"""Step checks for the step-by-step guide.

Usage (VS Code terminal, any OS):
    python check.py 3          # run the check for step 3
    python check.py 12 qwen3:4b  # step 12 with another Ollama model

Each check imports only files created up to that step.
"""

import sys

OK, FAIL = "PASS", "FAIL"


def result(cond, msg):
    print(f"[{OK if cond else FAIL}] {msg}")
    return cond


def step1():
    import langchain_ollama, pandas, streamlit  # noqa: F401
    return result(True, "streamlit, langchain_ollama and pandas import correctly")


def step2():
    from core.knowledge import CATEGORIES
    print(CATEGORIES)
    return result(len(CATEGORIES) == 5, "5 failure categories defined")


def step3():
    from core.scenarios import SCENARIOS
    for k, v in SCENARIOS.items():
        print(f"  {k}: {v['type']:8} expected {v['expected_category']}")
    return result(list(SCENARIOS) == ["A", "B", "C", "D"], "scenarios A-D loaded")


def step4():
    from core.scenarios import get_scenario
    from core.tools import TOOL_FUNCTIONS, call_tool
    logs = call_tool("read_build_logs", get_scenario("B"))
    print(logs[:400], "...")
    ok = all(call_tool(t, get_scenario(s)) for t in TOOL_FUNCTIONS for s in "ABCD")
    return result(ok and "orjson==3.12.9" in logs, f"{len(TOOL_FUNCTIONS)} tools return data; B logs show orjson error")


def step5():
    from core.scenarios import get_scenario
    from agents.base import sense
    p = sense(get_scenario("D"))
    print("  failed_stage:", p["failed_stage"], "| only_docs_changed:", p["only_docs_changed"],
          "| timeout signal:", p["signals"]["timeout_error"])
    return result(p["failed_stage"] == "unit_test" and p["only_docs_changed"] and p["signals"]["timeout_error"],
                  "percepts extracted for D")


def _run(agent_cls, scenarios="ABCD", same_instance=False):
    from core.scenarios import get_scenario
    agent = agent_cls()
    out = {}
    for s in scenarios:
        a = agent if same_instance else agent_cls()
        d = a.decide(get_scenario(s))
        out[s] = d
        print(f"  {s}: {d.failure_category:28} conf {d.confidence:<5} next: {d.next_step[:70]}")
    return out


def step6():
    from agents.simple_reflex import SimpleReflexAgent
    out = _run(SimpleReflexAgent)
    return result(out["D"].failure_category == "TEST_FAILURE" and out["A"].failure_category == "TEST_FAILURE",
                  "A-C correct; D = TEST_FAILURE (intended reflex limitation)")


def step7():
    from agents.model_based import ModelBasedReflexAgent
    out = _run(ModelBasedReflexAgent, same_instance=True)
    return result(out["D"].failure_category == "FLAKY_TEST_OR_CI_INFRA", "D recognised as flaky from history")


def step8():
    from core.scenarios import get_scenario
    from agents.goal_based import GoalBasedAgent
    d = GoalBasedAgent().decide(get_scenario("B"))
    for i, step in enumerate(d.details["plan"], 1):
        print(f"  plan {i}: {step}")
    return result(d.failure_category == "DEPENDENCY_FAILURE" and len(d.details["plan"]) == 3,
                  "B: dependency failure with a 3-step plan")


def step9():
    from core.scenarios import get_scenario
    from agents.utility_based import UtilityBasedAgent
    d = UtilityBasedAgent().decide(get_scenario("C"))
    print("  beliefs:", d.details["beliefs"])
    for r in d.details["utility_table"][:3]:
        print(f"  EU {r['expected_utility']:>6}  {r['action']}")
    return result("config" in d.details["utility_table"][0]["action"], "C: config diff beats rollback")


def step10():
    from core.scenarios import get_scenario
    from agents.learning_agent import LearningAgent
    d = LearningAgent().decide(get_scenario("D"))
    print(*("  " + r for r in d.reasoning), sep="\n")
    return result(d.failure_category == "FLAKY_TEST_OR_CI_INFRA" and d.confidence == 0.5,
                  "D = flaky with confidence 0.5 from experience")


def step11():
    from agents import CLASSICAL_AGENTS
    from core.compare import run_classical
    from core.scenarios import SCENARIOS
    wrong = []
    for s in "ABCD":
        res = run_classical(s, [c() for c in CLASSICAL_AGENTS])
        print(f"  {s}: " + ", ".join(f"{n}={d.failure_category}" for n, d in res.items()))
        wrong += [(s, n) for n, d in res.items() if d.failure_category != SCENARIOS[s]["expected_category"]]
    return result(wrong == [("D", "Simple Reflex")], "all correct except Simple Reflex on D")


def step12(model="qwen3:8b"):
    from core.scenarios import get_scenario
    from agents.llm_agent import LLMAgent
    print(f"  Running {model} on scenario A (first call may take 1-2 minutes)...")
    d = LLMAgent(model=model).decide(get_scenario("A"))
    print(*("  " + r for r in d.reasoning), sep="\n")
    print(*("  evidence: " + e for e in d.evidence), sep="\n")
    if d.details.get("error"):
        return result(False, "LLM could not run: " + d.details["error"][:200])
    return result(len(d.details["distinct_tools"]) >= 2,
                  f"category {d.failure_category}, {len(d.details['distinct_tools'])} tools, "
                  f"grounding {d.details['grounding_score']}")


CHECKS = {1: step1, 2: step2, 3: step3, 4: step4, 5: step5, 6: step6, 7: step7, 8: step8,
          9: step9, 10: step10, 11: step11, 12: step12}

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2 or int(sys.argv[1]) not in CHECKS:
        print("Usage: python check.py <step 1-12> [model]")
        sys.exit(1)
    n = int(sys.argv[1])
    ok = CHECKS[n](*sys.argv[2:]) if n == 12 and len(sys.argv) > 2 else CHECKS[n]()
    sys.exit(0 if ok else 1)
