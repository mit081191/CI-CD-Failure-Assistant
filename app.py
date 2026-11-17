import json
import pandas as pd
import streamlit as st
from scenarios import SCENARIOS
from agents.classical import (SimpleReflexAgent, ModelBasedReflexAgent, GoalBasedAgent,
                              UtilityBasedAgent, LearningAgent)
from agents.llm_agent import run_llm_agent

st.set_page_config(page_title="CI/CD Failure Assistant", page_icon="🛠️", layout="wide")
st.title("🛠️ Intelligent CI/CD Pipeline Failure Assistant")
st.caption("Read-only diagnosis · Six agents · Shared scenario input")

scenario_name = st.selectbox("Select a test scenario", list(SCENARIOS.keys()))
scenario = SCENARIOS[scenario_name]
with st.expander("Inspect shared scenario data", expanded=True):
    st.json(scenario)

model = st.text_input("Ollama model", value="qwen3:8b", help="Must already be pulled locally, e.g. qwen3:8b.")
run_classical = st.button("Run all six agents", type="primary", use_container_width=True)

if run_classical:
    results = {}
    agents = [
        SimpleReflexAgent(),
        ModelBasedReflexAgent(),
        GoalBasedAgent(),
        UtilityBasedAgent(),
        LearningAgent()
    ]
    for agent in agents:
        results[agent.name] = agent.decide(scenario)

    with st.spinner("Running local Ollama model and diagnostic tools..."):
        try:
            results["LLM (Ollama)"] = run_llm_agent(scenario, model=model)
        except Exception as exc:
            results["LLM (Ollama)"] = {
                "failure_category": "LLM unavailable",
                "likely_cause": str(exc),
                "recommended_next_step": "Check that Ollama is running, the model is pulled, and the LangChain Ollama integration is installed.",
                "supporting_evidence": [],
                "reasoning": "The LLM agent could not complete. Classical agent results are still valid.",
                "verification_checklist": ["Run `ollama list`.", "Run `ollama run qwen3:8b`.", "Retry the dashboard."],
                "confidence": 0.0,
                "tools_called": []
            }

    st.session_state["results"] = results
    st.session_state["scenario_name"] = scenario_name

if "results" in st.session_state:
    results = st.session_state["results"]
    st.subheader("Agent decisions")
    for name, result in results.items():
        with st.expander(name, expanded=(name == "LLM (Ollama)")):
            st.markdown(f"**Failure category:** {result.get('failure_category', 'N/A')}")
            st.markdown(f"**Likely cause:** {result.get('likely_cause', 'N/A')}")
            st.markdown(f"**Recommended next step:** {result.get('recommended_next_step', 'N/A')}")
            st.markdown("**Reasoning:** " + str(result.get("reasoning", "N/A")))
            st.markdown("**Supporting evidence:**")
            for evidence in result.get("supporting_evidence", []):
                st.write("• " + str(evidence))
            if result.get("tools_called") is not None:
                st.write("**LLM tools called:**", result.get("tools_called"))
            if result.get("experience") is not None:
                st.write("**Learning experience:**", result["experience"])
            st.write("**Verification checklist:**")
            for item in result.get("verification_checklist", []):
                st.checkbox(item, key=f"{name}-{item}")
            st.progress(float(max(0, min(1, result.get("confidence", 0.0)))))

    st.subheader("Comparison table")
    table = []
    for name, r in results.items():
        table.append({
            "Agent": name,
            "Failure category": r.get("failure_category", ""),
            "Recommended next step": r.get("recommended_next_step", ""),
            "Confidence": r.get("confidence", 0)
        })
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

    st.subheader("Learning Agent: record outcome")
    st.write("After a human reviewer verifies the diagnosis and action, record whether the approach helped. This updates data/experience.json.")
    outcome = st.radio("Was the Learning Agent's diagnostic approach successful?", ["Not evaluated", "Success", "Failure"], horizontal=True)
    if st.button("Save learning outcome", disabled=(outcome == "Not evaluated")):
        category = {
            "N": "healthy", "A": "test_regression", "B": "dependency",
            "C": "deployment_health", "D": "ambiguous"
        }.get(scenario.get("scenario_id"), "ambiguous")
        learner = LearningAgent()
        learner.record_outcome(category, outcome == "Success")
        st.success("Experience updated. Run the agents again to see how the history affects the recommendation.")

    st.download_button("Download results as JSON", json.dumps(results, indent=2), file_name="agent_results.json", mime="application/json")

st.divider()
st.caption("Safety: This assistant only reads supplied diagnostic evidence and recommends investigation steps. It does not modify source code, infrastructure, or deployments.")
