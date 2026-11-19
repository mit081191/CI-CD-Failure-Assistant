# Intelligent CI/CD Pipeline Failure Assistant

**BITS Pilani PG AI/ML - Agentic AI, Assignment 1 (Set 2) - Group 7**

| Team member | BITS ID |
|---|---|
| Biju Krishna | _2025paml522_ |
| Navneet Kashyap | _2025paml528_ |
| Solanki Mitul | _2025paml560_ |

Who built what is described in the separate contribution statement.

This assistant looks into failed build-and-deploy pipelines. It reads the pipeline status, build logs, test results, dependency info, deployment health and recent code changes, then recommends the **next troubleshooting step**. It is **advisory only**: it never changes code, edits configuration, re-runs deployments or rolls back by itself.

Six agents look at the **same scenario data**, so their decisions can be compared fairly:

| # | Agent | File | Decision mechanism |
|---|---|---|---|
| 1 | Simple Reflex | `agents/simple_reflex.py` | Ordered condition-action rules on the **current percept only**. The first rule that matches decides. No memory. |
| 2 | Model-Based Reflex | `agents/model_based.py` | Rules applied to an **internal world model**. The model is built from run history (last green commit, last healthy version, pass/fail history for each test) plus the current percept. The state carries over between calls. |
| 3 | Goal-Based | `agents/goal_based.py` | Explicit goal `{root_cause_confirmed, fix_path_identified}`. Each action has preconditions and effects (STRIPS style). **Uniform-cost search** finds the cheapest plan to the goal, and the next step is the first action of that plan. |
| 4 | Utility-Based | `agents/utility_based.py` | Evidence weights are turned into beliefs `P(cause / evidence)` with a softmax. Each action gets **expected utility** = 100·Σ P(h)·value(a,h) − 0.8·cost − 60·risk, and the agent picks the highest. |
| 5 | Learning | `agents/learning_agent.py` | Driven by **experience data** in `data/experience.json`: counts of which category each failure signature turned out to be, plus success/failure counts for each action. Engineer feedback updates these counts (critic + learning element). |
| 6 | LLM agent | `agents/llm_agent.py` | A **local Ollama model (qwen3:8b)** run through LangChain `ChatOllama.bind_tools`. It gets only the run id, so it has to call tools to see any data. Its JSON answer is checked against the tool outputs. |

All agents return the same `Decision` structure (`agents/base.py`): **failure category, supporting evidence, likely cause, recommended next step, post-fix verification checklist**, reasoning trace and confidence.

---

## 1. Setup and run

### Prerequisites

- Python 3.10 or newer
- [Ollama](https://ollama.com/download) installed and running
- About 6 GB free disk space for the model (`qwen3:4b` is a lighter option on machines with less than 16 GB RAM)

### Windows (PowerShell)

```powershell
# 1. Create and activate a virtual environment
py -3.11 -m venv .venv          # 3.10-3.12 all work
.venv\Scripts\Activate.ps1
# If activation is blocked, run once: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 2. Install Python dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 3. Start the Ollama app, then download the model
ollama pull qwen3:8b

# 4. Run the dashboard (opens http://localhost:8501)
streamlit run app.py
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ollama pull qwen3:8b            # run `ollama serve` first if the Ollama app is not running
streamlit run app.py
```

### Visual Studio Code

1. **File → Open Folder** and open the project folder.
2. `Ctrl+Shift+P` → **Python: Create Environment → Venv**, and tick `requirements.txt`.
3. **Run and Debug** (`Ctrl+Shift+D`) → **Streamlit: app.py** → **F5**.
4. The **Testing** panel (beaker icon) runs the pytest suite.

### Using the UI

1. Pick a scenario (A-D) in the sidebar. **Check Ollama connection** confirms that the model is available.
2. Click **Run all agents**. Every agent gets its own deep copy of the same scenario.
3. **Comparison** tab: a colour-coded table (green = correct category), agreement metrics, and an explanation of why the decisions differ.
4. One tab per agent: category, cause, next step, evidence, checklist and reasoning trace, plus details specific to the mechanism:
   - utility table and belief chart
   - plan found by search
   - world-model state
   - learned success rates
   - LLM tool calls with their raw outputs, and the grounding check
5. **Learning feedback** tab: record the actual category and whether the step helped. The experience file is updated and the Learning agent runs again straight away. **Reset experience** in the sidebar restores the seed data.
6. **All scenarios** tab: a matrix of each agent's category for every scenario.

### Tests and the results report

```bash
pytest -v                                   # 21 tests; the LLM loop is tested with a scripted fake model
python run_scenarios.py                     # all six agents -> test_results/results.md + results.json
python run_scenarios.py --no-llm            # classical agents only
python run_scenarios.py --model qwen3:4b    # use another model
```

---

## 2. Scenarios (shared input, `core/scenarios.py`)

| ID | Type | Situation | Expected category |
|---|---|---|---|
| A | Normal | A discount refactor in `pricing.py` breaks 2 unit tests. The failures are assertion errors and repeat on retry. | `TEST_FAILURE` |
| B | Failure | `requirements.txt` bumps `orjson==3.12.9`, which does not exist, and `numpy==2.3.1`, which needs Python ≥3.11 while the runner has 3.10. The build fails. | `DEPENDENCY_FAILURE` |
| C | Critical | All 194 tests pass and v2.8.0 goes to a 10% canary. Readiness returns 503, the error rate is 34% against a 0.4% baseline, and the log shows `KeyError: 'PAYMENT_GATEWAY_URL'`, because the env var was renamed but the manifest was not updated. | `DEPLOYMENT_HEALTH_FAILURE` |
| D | **Edge / ambiguous** | An integration test times out reaching the test DB on a **README-only** commit. The runner disk is at 96%, the log is truncated, and the same test has passed and failed on the same commit before. The surface signal "tests failed" is misleading. | `FLAKY_TEST_OR_CI_INFRA` |

Each scenario contains `pipeline_status`, `build_logs`, `test_results`, `dependencies`, `recent_changes`, `deployment` and `run_history`. `get_scenario()` returns a deep copy, and a test checks that no agent changes the shared input.

---

## 3. The LLM agent and tool calling

**Tools** (`core/tools.py`, all read-only):

- `get_pipeline_status()`
- `read_build_logs(max_lines)`
- `get_test_results()`
- `get_recent_change_summary()`
- `get_dependency_info()`
- `get_deployment_health()`
- `get_run_history()`

**Loop:** system prompt → model → tool calls are run against the selected scenario → `ToolMessage` results go back to the model. This repeats for up to 10 iterations, until the model returns a final JSON answer.

**Evidence checking:**

1. **At least 2 tools.** If the model answers after fewer than 2 distinct tool calls, it is told to investigate further.
2. **Structured output.** The answer must be JSON with the required fields. Qwen3 `<think>` blocks and code fences are stripped. If the JSON is still invalid, the agent re-asks using Ollama structured output (a JSON schema that forces valid JSON), and as a last resort salvages the key fields with pattern matching. The reasoning trace records when this happens.
3. **Grounding check.** Each evidence item must give `{"tool", "quote"}`. The quote is checked against that tool's actual output (normalised substring match, or ≥80% token overlap). The UI shows a verified/unverified table and a grounding score.
4. **Confidence penalty.** The reported confidence is scaled by `0.5 + 0.5 × grounding_score`, so ungrounded answers get lower confidence.
5. **Category check.** A category outside the allowed list is mapped to `UNKNOWN`.
6. **Graceful failure.** If Ollama is down or the model is missing, the agent returns `UNKNOWN` with setup instructions instead of crashing the UI.

---

## 4. The Learning agent

- **Signature** = `failed_stage|dominant_log_signal`, for example `unit_test|timeout_error`.
- **Category** = the most frequent confirmed category for that signature, as a Laplace-smoothed probability `(n_c+1)/(N+4)`. The agent uses this value as its confidence.
- **Action** = the action with the highest Laplace success rate `(s+1)/(s+f+2)` in that category's action menu.
- **Feedback** (UI or `record_outcome()`) does three things:
  - increments the signature→category count with the actual category
  - credits success or failure to the chosen action
  - logs an episode, recording whether the prediction was right
- **Unseen signature**: the agent falls back to a prior based on the failed stage and marks the decision as exploratory.

Example from scenario D with the seed data: `unit_test|timeout_error` has 5 flaky and 3 regression outcomes, so P = 0.50 and the agent picks FLAKY with honest, low confidence. The test `test_learning_agent_updates_experience_and_changes_decision` records 4 outcomes saying "this was really a code regression". After that, the agent switches to `TEST_FAILURE`, which shows that experience changes its decision. Similarly, in C it avoids "Restart the failing pods" because that action has 0 successes and 4 failures in its history.

---

## 5. Comparison of results

Results from `python run_scenarios.py` with Ollama (`qwen3:8b`). Classical agents use the seed experience.

| Scenario | Expected | Simple Reflex | Model-Based Reflex | Goal-Based | Utility-Based | Learning | LLM (Ollama + tools) |
|---|---|---|---|---|---|---|---|
| A - Unit tests fail after a code change | TEST_FAILURE | TEST_FAILURE ✓ | TEST_FAILURE ✓ | TEST_FAILURE ✓ | TEST_FAILURE ✓ | TEST_FAILURE ✓ | TEST_FAILURE ✓ |
| B - Build fails: dependency version unavailable/incompatible | DEPENDENCY_FAILURE | DEPENDENCY_FAILURE ✓ | DEPENDENCY_FAILURE ✓ | DEPENDENCY_FAILURE ✓ | DEPENDENCY_FAILURE ✓ | DEPENDENCY_FAILURE ✓ | DEPENDENCY_FAILURE ✓ |
| C - Tests pass, deployment health checks fail after release | DEPLOYMENT_HEALTH_FAILURE | DEPLOYMENT_HEALTH_FAILURE ✓ | DEPLOYMENT_HEALTH_FAILURE ✓ | DEPLOYMENT_HEALTH_FAILURE ✓ | DEPLOYMENT_HEALTH_FAILURE ✓ | DEPLOYMENT_HEALTH_FAILURE ✓ |DEPLOYMENT_HEALTH_FAILURE ✓ |
| D - Edge case: intermittent timeout on a docs-only commit | FLAKY_TEST_OR_CI_INFRA | TEST_FAILURE ✗ | FLAKY_TEST_OR_CI_INFRA ✓ | FLAKY_TEST_OR_CI_INFRA ✓ | FLAKY_TEST_OR_CI_INFRA ✓ | FLAKY_TEST_OR_CI_INFRA ✓ | DEPENDENCY_FAILURE ✗ |

Recommended next steps for scenario D:

| Agent | Next step | Confidence |
|---|---|---|
| Simple Reflex | Compare the failing test with the latest code change (**wrong: only README changed**) | 0.60 |
| Model-Based | Re-run on a different runner; check the test DB and runner disk | 0.80 |
| Goal-Based | Re-run the failed job on a different runner (step 1 of a 3-step plan) | 0.80 |
| Utility-Based | Re-run on a different runner and check runner/test-DB health (EU 68.7 vs 18.3 for "reproduce locally") | 0.85 |
| Learning | Re-run on a different runner (learned success rate 0.75) | 0.50 |
| LLM (Ollama + tools) | Check the PostgreSQL test database connection and ensure it is running and accessible (**wrong category: DEPENDENCY_FAILURE**) | 0.95 |

The full per-agent details are in `test_results/results.md`.

### Why the decisions differ

- **Scenarios A-C are clear.** All five classical agents agree on the category. They differ in the **next step**, because each mechanism optimises something different:
  - goal-based takes the first step of the cheapest complete plan
  - utility-based takes the best value per cost and risk; in C it ranks "immediate rollback" below "diagnose config first" because of the rollback's risk
  - learning takes whatever worked historically, and avoids "restart pods"
- **Scenario D separates the mechanisms.**
  - The **simple reflex** agent sees only "unit_test stage failed", and rule R2 fires before anything else is considered. This is the textbook weakness of reflex agents in a partially observable environment.
  - The **model-based** agent remembers that the same test passed and failed on the same commit, so it marks the test as flaky.
  - The **goal-based** agent can only reach its goal through the timeout + infrastructure path, because the code-regression path needs "change touches the failing module", which is false here.
  - The **utility-based** agent sets "only README changed" and "disk 96%" against "tests failed" and ends up with P(flaky) = 0.85.
  - The **learning** agent is right but uncertain, because its history for this signature is mixed.
  - The **LLM** agent got D wrong in our run. It called only the minimum two tools, `get_pipeline_status` and `get_test_results`, saw a timeout connecting to the test database, and labelled it a `DEPENDENCY_FAILURE`. It never called `get_recent_change_summary` (README-only commit) or `get_run_history` (the same test passed and failed on the same commit), which are the two pieces of evidence that reveal a flaky test. Like the simple reflex agent, it reacted to the surface signal. Unlike the model-based and utility-based agents, nothing forces it to look at history. The tool trace makes this visible (screenshot `07_scenario_D_llm_tools.png`). Its confidence was still 0.95: both evidence quotes were genuinely in the tool output, so the grounding check passed. This shows the grounding check's limit: it confirms that the evidence is real, not that the conclusion follows from it. In A–C, where the first tools already contain the decisive evidence, it was correct.

---

## 6. Limitations

- The scenarios are synthetic and hand-built. The rules, evidence weights, action values and costs were set by hand, not fitted to real pipeline data.
- The simple reflex and model-based rule sets cover only the four categories. A new failure type, such as a security-scan stage, falls to `UNKNOWN`.
- The utility weights (benefit 100, cost 0.8/min, risk 60, softmax temperature 2.5) are subjective, and different weights can change the ranking.
- The learning agent starts from invented seed counts. It is greedy, with no exploration once a signature is known, and it trusts engineer feedback without question.
- The LLM agent's results depend on the model and its size. Small models sometimes skip tools or produce weak JSON. The grounding check only confirms that a quote **appears** in the tool output, not that the conclusion follows from it. Results can also vary between runs, even at temperature 0.
- Confidence values are illustrative scores, not calibrated probabilities.
- None of the agents takes real actions. Re-runs, rollbacks and fixes are recommendations only, which is a deliberate safety constraint.

---

## 7. Project structure

```
cicd_failure_assistant/
├── app.py                  # Streamlit UI
├── run_scenarios.py        # runs every agent on every scenario -> test_results/
├── check.py                # quick checks of each component (python check.py <1-12>)
├── requirements.txt
├── .vscode/                # VS Code settings (pytest) + launch configs (Streamlit, report)
├── agents/
│   ├── base.py             # Decision dataclass, sensor (percepts), shared evidence helper
│   ├── simple_reflex.py
│   ├── model_based.py
│   ├── goal_based.py
│   ├── utility_based.py
│   ├── learning_agent.py
│   └── llm_agent.py        # LangChain + ChatOllama tool-calling agent
├── core/
│   ├── scenarios.py        # scenarios A-D (shared input)
│   ├── tools.py            # read-only investigation tools
│   ├── knowledge.py        # categories and verification checklists
│   └── compare.py          # comparison table + explanation
├── data/experience_seed.json   # seed experience (experience.json is created at runtime)
├── tests/                  # pytest suite + fake LLM
├── test_results/           # results.md, results.json, pytest_output.txt
└── screenshots/
```

## 8. Screenshots

All screenshots were taken from a local run with Ollama (`qwen3:8b`) running. To reproduce them, follow "Using the UI" in section 1.

| File | Shows |
|---|---|
| `01_setup_ollama_connected.png` | Sidebar: Ollama connection check with the model listed |
| `02_scenario_A_comparison.png` | Scenario A: comparison table, metrics and "why decisions differ" |
| `03_scenario_B_comparison.png` | Scenario B: comparison table |
| `04_scenario_C_comparison.png` | Scenario C: comparison table |
| `05_scenario_D_comparison.png` | Scenario D (edge case): Simple Reflex wrong, the others right |
| `06_scenario_A_llm_tools.png` | LLM tab, scenario A: tool calls and grounding check |
| `07_scenario_D_llm_tools.png` | LLM tab, scenario D: tool calls and grounding check |
| `08_shared_input_data.png` | Shared input data viewer (identical for all six agents) |
| `09_D_model_based_state.png` | Model-Based Reflex: world-model state (flaky test detected) |
| `10_D_goal_based_plan.png` | Goal-Based: plan found by search |
| `11_D_utility_table.png` | Utility-Based: expected-utility table and belief chart |
| `12_D_learning_rates.png` | Learning: signature counts and learned action success rates |
| `13_learning_feedback_recorded.png` | Learning feedback recorded and the re-evaluated decision |
| `14_all_scenarios_matrix.png` | All scenarios x all agents matrix |
| `15_pytest_passed.png` | Terminal: 21 tests passed |
