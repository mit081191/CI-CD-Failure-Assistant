from scenarios import SCENARIOS
from agents.classical import (
    SimpleReflexAgent, ModelBasedReflexAgent, GoalBasedAgent,
    UtilityBasedAgent, LearningAgent
)

AGENTS = [SimpleReflexAgent(), ModelBasedReflexAgent(), GoalBasedAgent(), UtilityBasedAgent()]

def test_all_classical_agents_return_required_fields():
    for scenario in SCENARIOS.values():
        for agent in AGENTS:
            result = agent.decide(scenario)
            for field in ["failure_category", "likely_cause", "recommended_next_step",
                          "supporting_evidence", "reasoning", "verification_checklist"]:
                assert field in result
            assert result["recommended_next_step"]

def test_scenarios_classify_expected_failure():
    expected = {
        "N - Normal: pipeline succeeds": "Healthy - no failure",
        "A - Unit tests fail after code change": "Test regression",
        "B - Dependency/version unavailable": "Dependency/build failure",
        "C - Tests pass, deployment health checks fail": "Deployment/runtime health failure",
        "D - Ambiguous edge case": "Unclassified pipeline failure"
    }
    agent = SimpleReflexAgent()
    for name, category in expected.items():
        assert agent.decide(SCENARIOS[name])["failure_category"] == category

def test_all_agents_agree_on_normal_and_failure_scenarios():
    # Every classical agent shares the classifier, so all five must agree on the category.
    agents = AGENTS + [LearningAgent("does-not-exist.json")]
    for name, scenario in SCENARIOS.items():
        categories = {agent.decide(scenario)["failure_category"] for agent in agents}
        assert len(categories) == 1, f"{name}: agents disagree {categories}"

def test_normal_scenario_recommends_no_corrective_action():
    scenario = SCENARIOS["N - Normal: pipeline succeeds"]
    for agent in AGENTS + [LearningAgent("does-not-exist.json")]:
        result = agent.decide(scenario)
        assert result["failure_category"] == "Healthy - no failure"
        assert "no" in result["recommended_next_step"].lower()

def test_learning_agent_persists_experience(tmp_path):
    path = tmp_path / "experience.json"
    agent = LearningAgent(str(path))
    agent.record_outcome("test_regression", True)
    agent.record_outcome("test_regression", False)
    reloaded = LearningAgent(str(path))
    assert reloaded.experience["test_regression"] == {"success": 1, "failure": 1}
    assert "experience" in reloaded.decide(SCENARIOS["A - Unit tests fail after code change"])

def test_agents_do_not_mutate_shared_scenario():
    import copy
    scenario = copy.deepcopy(SCENARIOS["A - Unit tests fail after code change"])
    original = copy.deepcopy(scenario)
    for agent in AGENTS:
        agent.decide(scenario)
    assert scenario == original
