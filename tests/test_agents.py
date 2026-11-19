"""Test suite: all six agents on the shared scenarios.

Run:  pytest -v
"""

import json
import os
import shutil

import pytest
from langchain_core.messages import AIMessage

from agents import (GoalBasedAgent, LearningAgent, ModelBasedReflexAgent,
                    SimpleReflexAgent, UtilityBasedAgent)
from agents.learning_agent import SEED_PATH
from agents.llm_agent import LLMAgent, extract_json, verify_quote
from core.compare import comparison_rows, explain_differences, run_classical
from core.knowledge import CATEGORIES, FLAKY_INFRA, TEST_FAILURE
from core.scenarios import SCENARIO_IDS, SCENARIOS, get_scenario
from core.tools import call_tool
from tests.fake_llm import FakeToolLLM, tool_call


@pytest.fixture
def learner(tmp_path):
    path = tmp_path / "experience.json"
    shutil.copy(SEED_PATH, path)
    return LearningAgent(str(path))


def classical(learner):
    return [SimpleReflexAgent(), ModelBasedReflexAgent(), GoalBasedAgent(), UtilityBasedAgent(), learner]


# ------------------------------------------------------------ shared input
def test_at_least_three_scenarios_including_edge_case():
    types = {s["type"] for s in SCENARIOS.values()}
    assert len(SCENARIOS) >= 3
    assert {"normal", "edge"} <= types and ({"critical"} & types or {"failure"} & types)


def test_agents_receive_identical_unmodified_input(learner):
    for sid in SCENARIO_IDS:
        before = json.dumps(SCENARIOS[sid], sort_keys=True)
        run_classical(sid, classical(learner))
        assert json.dumps(SCENARIOS[sid], sort_keys=True) == before
        assert get_scenario(sid) == SCENARIOS[sid] and get_scenario(sid) is not SCENARIOS[sid]


# ------------------------------------------------------------ output contract
@pytest.mark.parametrize("sid", SCENARIO_IDS)
def test_every_decision_has_required_fields(sid, learner):
    for name, d in run_classical(sid, classical(learner)).items():
        assert d.failure_category in CATEGORIES, name
        assert d.evidence, f"{name} gave no evidence"
        assert d.likely_cause and d.next_step, name
        assert len(d.verification_checklist) >= 3, name
        assert d.reasoning, name
        assert 0 <= d.confidence <= 1, name


# ------------------------------------------------------------ correctness
@pytest.mark.parametrize("sid", ["A", "B", "C"])
def test_all_classical_agents_correct_on_clear_scenarios(sid, learner):
    expected = SCENARIOS[sid]["expected_category"]
    for name, d in run_classical(sid, classical(learner)).items():
        assert d.failure_category == expected, f"{name} on {sid}: {d.failure_category}"


def test_edge_case_simple_reflex_misled_others_recover(learner):
    res = run_classical("D", classical(learner))
    assert res["Simple Reflex"].failure_category == TEST_FAILURE  # documented limitation
    for name in ["Model-Based Reflex", "Goal-Based", "Utility-Based", "Learning"]:
        assert res[name].failure_category == FLAKY_INFRA, name
    # learning agent signals ambiguity with lower confidence
    assert res["Learning"].confidence < res["Utility-Based"].confidence


# ------------------------------------------------------------ mechanisms
def test_model_based_uses_history_state():
    agent = ModelBasedReflexAgent()
    d = agent.decide(get_scenario("D"))
    assert "test_sync_orders_to_warehouse" in json.dumps(d.details["flaky_tests"])
    assert agent.decide(get_scenario("A")).details["last_green_commit"] == "7d02be1"


def test_goal_based_plan_reaches_goal():
    d = GoalBasedAgent().decide(get_scenario("B"))
    assert len(d.details["plan"]) == 3 and d.next_step == d.details["plan"][0]


def test_utility_based_rejects_risky_rollback_in_c():
    d = UtilityBasedAgent().decide(get_scenario("C"))
    table = {r["action"]: r["expected_utility"] for r in d.details["utility_table"]}
    rollback = next(v for k, v in table.items() if "rollback" in k)
    assert d.details["utility_table"][0]["expected_utility"] > rollback
    assert abs(sum(d.details["beliefs"].values()) - 1) < 0.01  # rounded to 3 dp


def test_learning_agent_updates_experience_and_changes_decision(learner):
    sc = get_scenario("D")
    before = learner.decide(sc)
    assert before.failure_category == FLAKY_INFRA
    # engineers repeatedly report that this signature was really a code regression
    for _ in range(4):
        learner.record_outcome(sc, before.failure_category, TEST_FAILURE, before.next_step, False)
    after = LearningAgent(learner.path).decide(sc)  # reload from disk -> persisted
    assert after.failure_category == TEST_FAILURE
    assert len(learner.experience["episodes"]) == 4
    row = next(r for r in learner.action_stats(FLAKY_INFRA) if r["action"] == before.next_step)
    assert row["failure"] == 1 + 4


def test_learning_agent_success_raises_rate(learner):
    sc = get_scenario("A")
    d = learner.decide(sc)
    rate_before = d.details["action_stats"][0]["success_rate"]
    learner.record_outcome(sc, d.failure_category, d.failure_category, d.next_step, True)
    assert learner.decide(sc).details["action_stats"][0]["success_rate"] > rate_before


# ------------------------------------------------------------ tools
def test_tools_return_scenario_data():
    sc = get_scenario("B")
    assert "orjson==3.12.9" in call_tool("read_build_logs", sc)
    assert json.loads(call_tool("get_pipeline_status", sc))["failed_stage"] == "build"


# ------------------------------------------------------------ LLM agent (fake model)
def _final(category, evidence):
    return AIMessage(content=json.dumps({
        "failure_category": category, "evidence": evidence,
        "likely_cause": "x", "next_step": "y", "verification_checklist": ["a", "b", "c"],
        "confidence": 0.9, "reasoning": "z"}))


def test_llm_agent_tool_loop_and_grounding():
    fake = FakeToolLLM([
        AIMessage(content="", tool_calls=[tool_call("get_pipeline_status")]),
        AIMessage(content="", tool_calls=[tool_call("get_test_results"), tool_call("get_recent_change_summary")]),
        _final("TEST_FAILURE", [
            {"tool": "get_test_results", "quote": "assert 81.0 == 90.0"},
            {"tool": "get_recent_change_summary", "quote": "Refactor discount calculation"},
            {"tool": "get_test_results", "quote": "database exploded"},  # hallucinated
        ]),
    ])
    d = LLMAgent(llm=fake).decide(get_scenario("A"))
    assert d.failure_category == TEST_FAILURE
    assert len(d.details["distinct_tools"]) == 3
    assert d.details["grounding_score"] == pytest.approx(0.67, abs=0.01)
    assert [c["verified"] for c in d.details["evidence_check"]] == [True, True, False]
    assert "get_pipeline_status" in fake.bound_tools


def test_llm_agent_forced_to_use_two_tools():
    fake = FakeToolLLM([
        AIMessage(content="", tool_calls=[tool_call("get_pipeline_status")]),
        _final("TEST_FAILURE", []),  # premature answer -> rejected
        AIMessage(content="", tool_calls=[tool_call("read_build_logs", {"max_lines": 20})]),
        _final("FLAKY_TEST_OR_CI_INFRA", [{"tool": "read_build_logs", "quote": "disk usage at 96%"}]),
    ])
    d = LLMAgent(llm=fake).decide(get_scenario("D"))
    assert d.failure_category == FLAKY_INFRA
    assert any("asked to call at least 2" in r for r in d.reasoning)
    assert d.details["grounding_score"] == 1.0


def test_llm_agent_handles_unavailable_ollama():
    d = LLMAgent(base_url="http://127.0.0.1:9").decide(get_scenario("A"))
    assert d.failure_category == "UNKNOWN" and "error" in d.details


def test_json_extraction_and_quote_verification():
    assert extract_json("<think>hmm</think>```json\n{\"a\": 1}\n```") == {"a": 1}
    assert extract_json("Here: {\"a\": {\"b\": 2}} done") == {"a": {"b": 2}}
    assert verify_quote("KeyError: 'PAYMENT_GATEWAY_URL'", call_tool("read_build_logs", get_scenario("C")))
    assert not verify_quote("segmentation fault in kernel", call_tool("read_build_logs", get_scenario("C")))
    # a 'key: value' quote must match JSON tool output '"key": "value"' (regression: was marked NOT found)
    assert verify_quote("failed_stage: unit_test", call_tool("get_pipeline_status", get_scenario("D")))


# ------------------------------------------------------------ comparison
def test_comparison_and_explanation(learner):
    res = run_classical("D", classical(learner))
    rows = comparison_rows("D", res)
    assert len(rows) == 5 and sum(r["Correct"] == "yes" for r in rows) == 4
    text = " ".join(explain_differences("D", res))
    assert "Simple Reflex" in text