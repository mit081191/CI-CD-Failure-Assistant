# Submission checklist

Mapped to the official Assignment 1 (set 2) instructions.

## Instructions
- [x] Five separate Python agents: Simple Reflex, Model-Based Reflex, Goal-Based, Utility-Based, Learning – `agents/classical.py`
- [x] One LLM agent using a local Ollama model (Qwen3) with tool calling – `agents/llm_agent.py`
- [x] All six agents receive the same selected scenario data – `app.py`, `run_all_scenarios.py`; checked by `test_agents_do_not_mutate_shared_scenario`
- [x] At least three scenarios: normal (N), failure/critical (A, B, C), edge/ambiguous (D) – `scenarios.py`
- [x] Streamlit UI to select a scenario and show each agent's decision, reasoning, and comparison – `app.py`
- [x] LLM calls at least two relevant tools and grounds its answer in returned evidence – enforced in code; tool calls listed in `results/summary.md`
- [x] Learning Agent uses and updates success/failure counts and explains the effect – `data/experience.json`, reasoning text, "Record outcome" in the UI

## Submission items
- [x] Python source for all five classical agents and the LLM agent
- [x] `requirements.txt`, `README.md`, Streamlit UI, setup/run instructions
- [x] Test results – `test_results.txt` (pytest) and `results/` (all six agents on every scenario)
- [x] Screenshots – scenarios A, B, C in `screenshots/`
- [ ] Screenshots – scenario N (normal) in `screenshots/`
- [x] Comparison table and explanation of why decisions differ – `COMPARISON.md`
- [x] No secrets, credentials, or real production logs included
