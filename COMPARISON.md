# Agent comparison: results and why decisions differ

All six agents received the same scenario dictionary for each run. The five classical agents receive it directly; the LLM receives only the scenario ID in its prompt and reads the same dictionary through its tools. Results below come from `run_all_scenarios.py` with `qwen3:8b` (full outputs in [results/](results/), dashboard runs in [screenshots/](screenshots/)).

## 1. Decision mechanisms

| Agent | Decision mechanism | What it uses | Why its recommendation can differ |
|---|---|---|---|
| Simple Reflex | Fixed condition → action rules | Current signals only | No context or history; the same signal always produces the same action. |
| Model-Based Reflex | Rules + internal model of pipeline stages | Current signals + pipeline status + recent changes | Can relate the failure to the stage it happened in and to the last change, e.g. "compare with the last successful commit". |
| Goal-Based | Chooses the action that advances the goal (safe recovery) | Current signals + an explicit goal per category | Phrases the next step as progress toward a goal ("restore a passing test suite"), even if a faster action exists. |
| Utility-Based | Heuristic trade-off: diagnostic value + risk reduction − effort | Current signals + utility heuristic | Prefers cheap, reversible, low-risk investigation; with weak evidence, information gathering wins. Lowest confidence in the ambiguous case (0.45). |
| Learning | Laplace-smoothed success rate from past outcomes | Current signals + `data/experience.json` | Same category as the others, but its caution level and confidence come from history, not from the evidence. |
| LLM (Qwen3) | Language-model reasoning over tool results | Only what its tools return | Decides which tools to call, combines evidence across tools, and writes a specific cause, but uses its own category names and may skip a tool or infer beyond the evidence. |

## 2. Results per scenario

### N – Normal: pipeline succeeds
| Agent | Category | Next step | Conf. |
|---|---|---|---|
| Simple Reflex | Healthy - no failure | No corrective action; continue monitoring | 0.82 |
| Model-Based Reflex | Healthy - no failure | Keep this run as the last-known-good baseline | 0.86 |
| Goal-Based | Healthy - no failure | Proceed with normal release review | 0.84 |
| Utility-Based | Healthy - no failure | Take no action (any action only adds risk) | 0.80 |
| Learning | Healthy - no failure | No corrective action; continue monitoring | 0.73 |
| LLM | Healthy - no failure | No corrective action; monitor production metrics | 1.00 |

All six agree. The LLM called 3 tools (status, build logs, test results) and stopped once the evidence was conclusive.

### A – Unit tests fail after code change
| Agent | Category | Next step | Conf. |
|---|---|---|---|
| Simple Reflex | Test regression | Inspect failing assertion and latest changed function | 0.82 |
| Model-Based Reflex | Test regression | Compare with last successful commit; isolate the regression | 0.86 |
| Goal-Based | Test regression | Reproduce the test, inspect changed path, make a focused fix | 0.84 |
| Utility-Based | Test regression | Inspect failing test and changed code first | 0.80 |
| Learning | Test regression | Reproduce the test and inspect the recent diff | 0.76 |
| LLM | Test Failure | Analyze test results and code changes around the failing test | 0.85 |

**Difference:** the LLM called only `get_pipeline_status` and `read_build_logs`, so it never saw the commit that changed tax calculation from inclusive to exclusive. Its cause ("logic error in the code under test") is correct but generic. The Model-Based agent's recent-change context gives it a sharper next step here. This shows that the LLM is only as good as the tools it chooses to call.

### B – Dependency / version unavailable
| Agent | Category | Next step | Conf. |
|---|---|---|---|
| Simple Reflex | Dependency/build failure | Check package index, lockfile, Python version, constraints | 0.82 |
| Model-Based Reflex | Dependency/build failure | Compare lockfile with last good build; verify version in registry | 0.86 |
| Goal-Based | Dependency/build failure | Validate version, update constraints only after confirming compatibility | 0.84 |
| Utility-Based | Dependency/build failure | Verify availability before editing constraints | 0.80 |
| Learning | Dependency/build failure | Verify registry, runtime compatibility, lockfile consistency | 0.78 |
| LLM | Dependency Resolution Failure | Verify `fastapi==99.0.0` in the index; revert the pin if invalid | 0.95 |

**Difference:** every agent finds the category, but only the LLM names the exact package and version and links the build error to commit def456. The Utility-Based and Goal-Based agents deliberately avoid recommending an upgrade until compatibility is confirmed.

### C – Tests pass, deployment health checks fail
| Agent | Category | Next step | Conf. |
|---|---|---|---|
| Simple Reflex | Deployment/runtime health failure | Inspect startup logs, readiness config, env vars, connectivity | 0.82 |
| Model-Based Reflex | Deployment/runtime health failure | Compare release config and logs with previous healthy release | 0.86 |
| Goal-Based | Deployment/runtime health failure | Inspect probes and startup logs; compare runtime config | 0.84 |
| Utility-Based | Deployment/runtime health failure | Inspect readiness failures; compare with previous release | 0.80 |
| Learning | Deployment/runtime health failure | Inspect logs, probes, and config differences | 0.73 |
| LLM | Deployment Configuration | Align probe/manifest port with the container's listening port (8000); check the renamed PORT variable | 0.95 |

**Difference:** this is where the LLM adds the most value. It combined three tool results (health data: app on 8000, probe on 8080; change summary: PORT variable renamed) into one specific root cause. The classical agents correctly identify the stage but give general checklists. Caveat: the LLM's statement that the deployment config "still references the old port" is an inference, not something the evidence shows directly. It should be verified.

### D – Ambiguous edge case
| Agent | Category | Next step | Conf. |
|---|---|---|---|
| Simple Reflex | Unclassified pipeline failure | Collect full logs, test report, lockfile, deployment events | 0.65 |
| Model-Based Reflex | Unclassified pipeline failure | Gather stage timestamps, complete logs, last known-good state | 0.55 |
| Goal-Based | Unclassified pipeline failure | Collect diagnostics; find the first failing stage | 0.50 |
| Utility-Based | Unclassified pipeline failure | Gather complete logs; find the first failing stage | 0.45 |
| Learning | Unclassified pipeline failure | Gather missing stage-level evidence | 0.73 |
| LLM | Insufficient Evidence | Collect full logs, test reports, dependency output, stage metrics | 0.30 |

**Difference:** all agents correctly refuse to guess a root cause. The LLM called all four tools and reported the lowest confidence (0.30). The Learning Agent reports a relatively high 0.73 because it has no history for this category: the default 0.5 prior maps to 0.73. Its confidence reflects past outcomes, not evidence quality, which is a known limitation of this design.

## 3. Summary: why decisions differ

1. **Same classifier, different policies.** The five classical agents share one signal classifier, so they always agree on the category (verified by `test_all_agents_agree_on_normal_and_failure_scenarios`). They differ in the action they choose and in their confidence, because each applies a different decision policy: rules, state model, goal, utility, or experience.
2. **Context changes specificity.** Agents that use more context (Model-Based: recent changes; LLM: whichever tools it calls) produce more specific causes. Agents without it fall back to general checklists.
3. **Confidence means different things.** Rule-based confidence is a fixed score per agent. Utility-Based confidence drops when evidence is weak. Learning confidence follows past success rates. LLM confidence is self-reported. None of them are calibrated probabilities.
4. **The LLM is the most specific and the least predictable.** It gave the best root cause in B and C, a generic one in A because it skipped a tool, and invented its own category labels ("Test Failure", "Deployment Configuration"). Its tool choices and wording vary between runs, so its recommendations must be checked against raw evidence.
5. **All agents are safe by design.** None can change code, restart services, or deploy. In the normal scenario all six recommend no action, and in the ambiguous one all recommend collecting evidence first.

## 4. Evaluation caveats
- Scenarios are synthetic; results show agent behaviour, not production accuracy.
- Learning Agent history is small and human-labelled; record outcomes in the dashboard to see its caution level change.
- LLM results are from one run each with `qwen3:8b` at temperature 0; other runs or model versions can call different tools and phrase things differently.
