# Intelligent CI/CD Pipeline Failure Assistant

A read-only diagnostic assistant that compares five classical AI agents and one local LLM agent for CI/CD pipeline failures.

## Features
- Simple Reflex, Model-Based Reflex, Goal-Based, Utility-Based, and Learning agents.
- Local Ollama model (Qwen3) connected through LangChain tool calling.
- Four diagnostic tools; the LLM must call at least two before producing its recommendation.
- Shared scenario dictionary passed to every agent.
- Streamlit UI with reasoning, evidence, confidence, verification checklist, comparison table, and JSON export.
- Persistent Learning Agent experience in `data/experience.json`.
- Pytest coverage for the scenarios, shared inputs, and learning persistence.

## Requirements
- Python 3.10 or newer
- Ollama installed and running locally
- Qwen3 model downloaded locally

## Setup (Windows PowerShell)

```powershell
# 1. Create and activate a virtual environment
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install Python dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 3. Install Ollama from https://ollama.com/download
# Start Ollama, then download the model
ollama pull qwen3:8b

# 4. Run the dashboard
streamlit run app.py
```

Open the local URL printed by Streamlit (usually http://localhost:8501).

### macOS/Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ollama pull qwen3:8b
streamlit run app.py
```

If your computer has limited RAM, try a smaller Qwen3 variant available in your Ollama library and enter its exact tag in the dashboard's model field.

## Run tests

```bash
pytest -v
```

The classical-agent tests run without Ollama. To evaluate the LLM, Ollama must be running and the model must be available.

## Scenarios
- A: Unit tests fail after a code change.
- B: A pinned dependency version cannot be resolved.
- C: Tests pass, but deployment readiness checks fail.
- D: Ambiguous failure with incomplete evidence (extra edge-case scenario).

Every agent receives the same selected scenario object. The LLM receives that same object as the input to its diagnostic tools. No agent has write/deploy tools.

## Agent mechanisms
1. **Simple Reflex:** fixed condition-action rules based on current signals.
2. **Model-Based Reflex:** combines current signals with a lightweight model of pipeline stages and recent changes.
3. **Goal-Based:** selects a diagnostic action that advances the goal of safe recovery.
4. **Utility-Based:** favors high diagnostic value, low risk, and reversible actions.
5. **Learning:** uses persisted success/failure counts by failure category. It calculates a Laplace-smoothed success estimate `(success + 1) / (total + 2)` and changes the caution level accordingly. A human reviewer records outcomes in the UI.
6. **LLM:** Qwen3 reasons over evidence returned by LangChain tools. Tool calls and evidence are shown in the result.

## Expected diagnosis guide

| Scenario | Expected category | Useful next investigation |
|---|---|---|
| A | Test regression | Inspect failing assertion and changed function |
| B | Dependency/build failure | Verify package registry and version constraints |
| C | Deployment/runtime health failure | Compare readiness probe port and application listening port |
| D | Unclassified | Collect complete logs and identify first failing stage |

## Screenshots for submission
1. Run `streamlit run app.py`.
2. Select scenario A, click **Run all six agents**, and capture the dashboard showing agent outputs and comparison table.
3. Repeat for scenarios B and C.
4. Save screenshots as:
   - `screenshots/scenario_A.png`
   - `screenshots/scenario_B.png`
   - `screenshots/scenario_C.png`
5. Optionally capture scenario D and the Learning Agent outcome update.

Screenshots must be captured from your actual local run; do not use mock screenshots as proof of execution.

## Test results
The automated classical-agent tests are in `tests/test_agents.py`. Run `pytest -v` and include the terminal output in your submission. LLM execution is environment-dependent and should be demonstrated with Ollama running.

## Limitations
- Scenario evidence is synthetic and intended for an academic demonstration.
- The Learning Agent learns from human-entered outcome labels, not automatic production feedback.
- The utility values are transparent heuristics, not a statistically calibrated optimizer.
- The LLM may produce different wording or conclusions across model versions. Verify recommendations against raw logs.
- The application is advisory only and does not perform remediation.
