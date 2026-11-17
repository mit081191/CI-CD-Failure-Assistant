# Intelligent CI/CD Pipeline Failure Assistant

A read-only diagnostic assistant that compares five classical AI agents and one local LLM agent on CI/CD pipeline runs.

## Features
- Simple Reflex, Model-Based Reflex, Goal-Based, Utility-Based, and Learning agents ([agents/classical.py](agents/classical.py)).
- Local Ollama model (Qwen3) connected through LangChain tool calling ([agents/llm_agent.py](agents/llm_agent.py)).
- Four diagnostic tools; the LLM must call at least two different tools before producing its recommendation (enforced in code).
- One shared scenario dictionary passed to every agent.
- Streamlit UI with reasoning, evidence, confidence, verification checklist, comparison table, and JSON export.
- Persistent Learning Agent experience in `data/experience.json`.
- Batch runner that saves all six agents' results for every scenario (`run_all_scenarios.py`).
- Pytest coverage for scenario classification, shared inputs, the normal scenario, and learning persistence.

## Project structure

```
agents/classical.py     Five classical agents and the shared signal classifier
agents/llm_agent.py     Qwen3 agent with four read-only LangChain tools
scenarios.py            Shared scenarios N, A, B, C, D
app.py                  Streamlit dashboard
run_all_scenarios.py    Runs all six agents on every scenario -> results/
data/experience.json    Learning Agent success/failure counts
tests/test_agents.py    Pytest suite
results/                Saved agent outputs per scenario + summary.md
screenshots/            Dashboard screenshots from local runs
COMPARISON.md           Comparison table and why decisions differ
```

## Requirements
- Python 3.10–3.12 (3.12 recommended; newer versions may lack wheels for some dependencies)
- Ollama installed and running locally
- Qwen3 model downloaded locally (`qwen3:8b`, about 5.2 GB)

## Setup (Windows PowerShell)

```powershell
# 1. Create and activate a virtual environment
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install Python dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 3. Install Ollama from https://ollama.com/download
#    (no account needed: choose "use Ollama locally"), then download the model
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

If your computer has limited RAM, try a smaller Qwen3 variant such as `qwen3:4b` and enter its exact tag in the dashboard's model field (or pass `--model` to the batch runner).

### Troubleshooting
- **`llama-server process has terminated: exit status 0xe06d7363`** when the LLM agent runs: Ollama crashed while loading the model onto the GPU. On our test machine (GTX 1060) this was caused by an outdated NVIDIA driver from 2020; installing the current NVIDIA driver and restarting fixed it. To confirm the model itself is fine, it also runs CPU-only (slower).
- **"LLM unavailable" in the dashboard:** check that Ollama is running (`ollama list`) and the model tag matches.
- The LLM agent takes roughly 2 minutes per scenario on a GTX 1060; the classical agents are instant.

## Run tests

```bash
pytest -v
```

The tests cover the classical agents and run without Ollama. Saved output: [test_results.txt](test_results.txt).

## Run all scenarios (saved results)

```bash
python run_all_scenarios.py
```

Runs all six agents (including the LLM, so Ollama must be running) on every scenario and writes:
- `results/scenario_<ID>.json` – the scenario input and every agent's full output
- `results/summary.md` – one comparison table per scenario, with the LLM's tool calls and runtime

## Scenarios

| ID | Type | Scenario |
|---|---|---|
| N | Normal | Pipeline succeeds; all stages and health checks pass |
| A | Failure | Unit tests fail after a code change |
| B | Failure | A pinned dependency version cannot be resolved |
| C | Critical failure | Tests pass, but deployment readiness checks fail |
| D | Edge / ambiguous | Failure with truncated, incomplete evidence |

Every agent receives the same selected scenario object. The LLM receives only the scenario ID in its prompt and must retrieve the evidence through its tools, which read that same object. No agent has write/deploy tools.

## Agent mechanisms
1. **Simple Reflex:** fixed condition-action rules based on current signals.
2. **Model-Based Reflex:** combines current signals with a lightweight model of pipeline stages and recent changes.
3. **Goal-Based:** selects a diagnostic action that advances the goal of safe recovery.
4. **Utility-Based:** favors high diagnostic value, low risk, and reversible actions.
5. **Learning:** uses persisted success/failure counts by failure category. It calculates a Laplace-smoothed success estimate `(success + 1) / (total + 2)`: below 0.5 it recommends a more cautious, diagnostics-first step; at 0.75 or above it follows the proven approach; the estimate also sets its confidence. A human reviewer records outcomes in the UI, which updates `data/experience.json`.
6. **LLM:** Qwen3 calls read-only LangChain tools (`get_pipeline_status`, `read_build_logs`, `get_test_results`, `get_recent_change_summary`) and reasons over the returned evidence. If it tries to answer after fewer than two distinct tools, the code sends it back to gather more evidence. Tool calls are shown in the result.

## Expected diagnosis guide

| Scenario | Expected category | Useful next investigation |
|---|---|---|
| N | Healthy - no failure | None; keep as last-known-good baseline |
| A | Test regression | Inspect failing assertion and changed function |
| B | Dependency/build failure | Verify package registry and version constraints |
| C | Deployment/runtime health failure | Compare readiness probe port and application listening port |
| D | Unclassified | Collect complete logs and identify first failing stage |

## Screenshots
Captured from actual local runs (`streamlit run app.py`, select a scenario, click **Run all six agents**). Each scenario has a series of screenshots covering the scenario input, each agent's output, the LLM's tool calls, and the comparison table:

- `screenshots/Scenario-N_01.png` … (normal scenario)
- `screenshots/Scenario-A_01.png` … `Scenario-A_08.png`
- `screenshots/Scenario-B_01.png` … `Scenario-B_08.png`
- `screenshots/Scenario-C_01.png` … `Scenario-C_08.png`

## Changes from the original version
- **LLM tool calling fixed:** the original prompt included the full scenario evidence, so the model answered without calling any tools. The prompt now carries only the scenario ID, and the "at least two tools" rule is enforced in code.
- **Normal scenario added:** scenario N and a "Healthy - no failure" category for all agents, to cover the required normal / failure / edge set.
- Added `run_all_scenarios.py`, saved results, extra tests, `.gitignore`, and troubleshooting notes.

## Limitations
- Scenario evidence is synthetic and intended for an academic demonstration.
- The Learning Agent learns from human-entered outcome labels, not automatic production feedback.
- The utility values are transparent heuristics, not a statistically calibrated optimizer.
- The LLM may choose different tools, wording, or conclusions across runs and model versions. Verify recommendations against raw logs.
- The application is advisory only and does not perform remediation.
