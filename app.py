"""Streamlit UI - Intelligent CI/CD Pipeline Failure Assistant (Group 7).

Run:  streamlit run app.py
"""

import json
import urllib.request

import pandas as pd
import streamlit as st

from agents import CLASSICAL_AGENTS, LearningAgent, ModelBasedReflexAgent
from agents.learning_agent import ACTION_MENU
from agents.llm_agent import LLMAgent
from core.compare import AGENT_ORDER, comparison_rows, explain_differences
from core.knowledge import CATEGORIES, CATEGORY_LABELS, SAFETY_NOTE
from core.scenarios import SCENARIO_IDS, SCENARIOS, get_scenario

st.set_page_config(page_title="CI/CD Failure Assistant - Group 7", layout="wide")

# ------------------------------------------------------------------ state
if "agents" not in st.session_state:
    st.session_state.agents = [cls() for cls in CLASSICAL_AGENTS]
if "results" not in st.session_state:
    st.session_state.results = {}  # scenario id -> {agent name: Decision}


def learning_agent() -> LearningAgent:
    return next(a for a in st.session_state.agents if isinstance(a, LearningAgent))


def ollama_status(base_url: str):
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=3) as r:
            models = [m["name"] for m in json.load(r).get("models", [])]
        return True, models
    except Exception as exc:
        return False, str(exc)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Scenario")
    sid = st.selectbox("Select a failed pipeline scenario", SCENARIO_IDS,
                       format_func=lambda s: SCENARIOS[s]["name"])
    st.divider()
    st.header("LLM agent (Ollama)")
    use_llm = st.checkbox("Run LLM agent", value=True)
    model = st.text_input("Model", value="qwen3:8b")
    base_url = st.text_input("Ollama URL", value="http://localhost:11434")
    think = st.checkbox("Enable model thinking (slower)", value=False)
    if st.button("Check Ollama connection"):
        ok, info = ollama_status(base_url)
        if ok:
            st.success(f"Connected. Models: {', '.join(info) or 'none pulled'}")
            if not any(m.startswith(model) for m in info):
                st.warning(f"Model '{model}' not found - run `ollama pull {model}`")
        else:
            st.error(f"Ollama not reachable: {info}")
    st.divider()
    st.header("Learning agent")
    if st.button("Reset experience to seed data"):
        learning_agent().reset()
        st.success("Experience reset.")
    st.caption(SAFETY_NOTE)

# ------------------------------------------------------------------ header
st.title("Intelligent CI/CD Pipeline Failure Assistant")
st.caption("BITS Pilani PG AI/ML - Agentic AI Assignment 1 (Set 2) - Group 7 - "
           "Five classical agents + one LLM agent on identical scenario data")

sc = SCENARIOS[sid]
c1, c2, c3 = st.columns([3, 1, 2])
c1.subheader(sc["name"])
c1.write(sc["description"])
c2.metric("Scenario type", sc["type"])
c3.markdown("**Expected category (ground truth)**")
c3.code(sc["expected_category"], language=None)

with st.expander("Shared input data - identical copy given to all six agents"):
    tabs = st.tabs(["Pipeline status", "Build logs", "Test results", "Dependencies",
                    "Recent changes", "Deployment", "Run history"])
    tabs[0].json(sc["pipeline_status"])
    tabs[1].code(sc["build_logs"], language="log")
    tabs[2].json(sc["test_results"])
    tabs[3].json(sc["dependencies"])
    tabs[4].json(sc["recent_changes"])
    tabs[5].json(sc["deployment"])
    tabs[6].json(sc["run_history"])

# ------------------------------------------------------------------ run
col_a, col_b = st.columns([1, 4])
run = col_a.button("Run all agents", type="primary")
if run:
    decisions = {}
    with st.spinner("Running classical agents..."):
        for agent in st.session_state.agents:
            decisions[agent.name] = agent.decide(get_scenario(sid))
    if use_llm:
        with st.spinner(f"LLM agent investigating with {model} (tool calling)..."):
            decisions[LLMAgent.name] = LLMAgent(model=model, base_url=base_url, think=think).decide(get_scenario(sid))
    st.session_state.results[sid] = decisions

decisions = st.session_state.results.get(sid)
if not decisions:
    st.info("Click **Run all agents** to investigate this scenario.")
    st.stop()

llm_d = decisions.get(LLMAgent.name)
if llm_d and llm_d.details.get("error"):
    st.warning(f"LLM agent could not run: {llm_d.details['error'][:300]}  \n"
               f"Suggested fix: {llm_d.next_step}")

# ------------------------------------------------------------------ tabs
names = [n for n in AGENT_ORDER if n in decisions]
tab_objs = st.tabs(["Comparison"] + names + ["Learning feedback", "All scenarios"])

# ---- comparison
with tab_objs[0]:
    st.subheader("Decision comparison")
    df = pd.DataFrame(comparison_rows(sid, decisions))

    def highlight(row):
        color = "#e6f4ea" if row["Correct"] == "yes" else "#fde8e8"
        return [f"background-color: {color}"] * len(row)

    st.dataframe(df.style.apply(highlight, axis=1).format({"Confidence": "{:.2f}"}),
                 width="stretch", hide_index=True)
    correct = (df["Correct"] == "yes").sum()
    m1, m2, m3 = st.columns(3)
    m1.metric("Agents with correct category", f"{correct} / {len(df)}")
    m2.metric("Distinct categories", df["Failure category"].nunique())
    m3.metric("Distinct next steps", df["Recommended next step"].nunique())
    st.subheader("Why the decisions differ")
    for line in explain_differences(sid, decisions):
        st.markdown(line)

# ---- per-agent tabs
for name, tab in zip(names, tab_objs[1:1 + len(names)]):
    d = decisions[name]
    with tab:
        st.markdown(f"**Mechanism:** {d.mechanism}")
        a, b = st.columns(2)
        a.markdown("**Failure category**")
        a.code(d.failure_category, language=None)
        b.metric("Confidence", d.confidence)
        st.caption(CATEGORY_LABELS.get(d.failure_category, ""))
        st.markdown(f"**Likely cause:** {d.likely_cause}")
        st.markdown(f"**Recommended next step:** {d.next_step}")
        left, right = st.columns(2)
        with left:
            st.markdown("**Supporting evidence**")
            for e in d.evidence or ["(none)"]:
                st.markdown(f"- {e}")
        with right:
            st.markdown("**Post-fix verification checklist**")
            for item in d.verification_checklist:
                st.markdown(f"- [ ] {item}")
        with st.expander("Reasoning trace", expanded=True):
            for r in d.reasoning:
                st.text(r)

        det = d.details
        if "utility_table" in det:
            st.markdown("**Expected-utility table**")
            st.dataframe(pd.DataFrame(det["utility_table"]), width="stretch", hide_index=True)
            st.markdown("**Beliefs P(cause | evidence)**")
            st.bar_chart(pd.Series(det["beliefs"], name="probability"))
        if "plan" in det and det["plan"]:
            st.markdown("**Plan found by search**")
            for i, step in enumerate(det["plan"], 1):
                st.markdown(f"{i}. {step}")
            st.caption(f"Estimated cost: {det.get('plan_cost_min')} min | initial facts: {det.get('facts')}")
        if "flaky_tests" in det:
            st.markdown("**Internal state (world model)**")
            st.json({k: v for k, v in det.items()})
        if "action_stats" in det:
            st.markdown(f"**Learned action success rates** (signature `{det['signature']}`, "
                        f"past outcomes {det['signature_counts']})")
            st.dataframe(pd.DataFrame(det["action_stats"]), width="stretch", hide_index=True)
        if "tool_calls" in det and det["tool_calls"]:
            st.markdown(f"**Tool calls** ({len(det.get('distinct_tools', []))} distinct tools, "
                        f"{det.get('elapsed_s', '?')} s, model `{det.get('model')}`)")
            for tc in det["tool_calls"]:
                with st.expander(f"Step {tc['step']}: {tc['tool']}({tc['args'] or ''})"):
                    st.code(tc["output"], language="json")
            if det.get("evidence_check"):
                st.markdown(f"**Grounding check** - score {det['grounding_score']}")
                st.dataframe(pd.DataFrame(det["evidence_check"]), width="stretch", hide_index=True)
            with st.expander("Raw model response"):
                st.code(det.get("raw_response", ""))

# ---- learning feedback
with tab_objs[1 + len(names)]:
    la = learning_agent()
    ld = decisions["Learning"]
    st.subheader("Teach the learning agent (critic feedback)")
    st.write(f"Learning agent predicted **{ld.failure_category}** and recommended: *{ld.next_step}*")
    actual = st.selectbox("Actual root-cause category (confirmed by engineer)", CATEGORIES[:-1],
                          index=CATEGORIES.index(sc["expected_category"]))
    menu = ACTION_MENU.get(ld.failure_category, [])
    action = st.selectbox("Action that was tried", menu,
                          index=menu.index(ld.next_step) if ld.next_step in menu else 0)
    helped = st.radio("Did the action help resolve the failure?", ["Yes - success", "No - failure"],
                      horizontal=True)
    if st.button("Record outcome and update experience"):
        ep = la.record_outcome(get_scenario(sid), ld.failure_category, actual, action,
                               helped.startswith("Yes"))
        st.success(f"Recorded: {ep}")
        new_d = la.decide(get_scenario(sid))
        st.session_state.results[sid]["Learning"] = new_d
        st.info(f"Re-evaluated: category {new_d.failure_category} (confidence {new_d.confidence}), "
                f"next step: {new_d.next_step}")
    st.markdown("**Current signature -> category counts**")
    st.json(la.experience["signature_outcomes"])
    if la.experience["episodes"]:
        st.markdown("**Feedback episodes**")
        st.dataframe(pd.DataFrame(la.experience["episodes"]), width="stretch", hide_index=True)

# ---- all scenarios matrix
with tab_objs[2 + len(names)]:
    st.subheader("Category chosen by each agent across all scenarios")
    st.caption("Classical agents are run fresh on every scenario. LLM column uses results already "
               "computed in this session (run each scenario to fill it).")
    matrix = {}
    fresh = [cls() for cls in CLASSICAL_AGENTS[:-1]] + [learning_agent()]
    for s in SCENARIO_IDS:
        row = {"Expected": SCENARIOS[s]["expected_category"]}
        for agent in fresh:
            cat = agent.decide(get_scenario(s)).failure_category
            row[agent.name] = cat + (" ✓" if cat == row["Expected"] else " ✗")
        llm_prev = st.session_state.results.get(s, {}).get(LLMAgent.name)
        if llm_prev:
            row[LLMAgent.name] = llm_prev.failure_category + (" ✓" if llm_prev.failure_category == row["Expected"] else " ✗")
        matrix[SCENARIOS[s]["name"]] = row
    st.dataframe(pd.DataFrame(matrix).T, width="stretch")
