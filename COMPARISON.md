# Why the agents may make different decisions

| Agent | Decision mechanism | Why its recommendation can differ |
|---|---|---|
| Simple Reflex | Fixed rules | Reacts only to matching signals in the current observation; no history. |
| Model-Based Reflex | Current observation + internal stage model | Uses stage context and recent changes to distinguish build, test, and deployment failures. |
| Goal-Based | Goal satisfaction | Prioritizes the next action that advances safe recovery, even if another action is faster. |
| Utility-Based | Heuristic trade-off | Balances diagnostic value, effort, reversibility, and operational risk. |
| Learning | Experience counts | Uses prior success/failure labels to become more or less cautious for a failure category. |
| LLM | Language-model reasoning + tools | Can synthesize multiple tool outputs and explain relationships, but may hallucinate; evidence must be checked. |

## Fair comparison
All agents receive the same selected scenario dictionary. The classical agents receive it directly; the LLM receives the same dictionary through tool arguments. Compare failure category, evidence, likely cause, and recommended next step rather than expecting identical wording.

## Evaluation discussion
- Scenario A: A rule-based agent can detect test failure. Model-based and LLM agents can connect it to the changed calculation function. The goal-based agent emphasizes reproducing the regression.
- Scenario B: All agents should identify dependency resolution. The LLM can cite both the dependency metadata and build error. The utility-based agent avoids blindly upgrading the package.
- Scenario C: A stage-aware agent distinguishes successful tests from failed runtime health checks. The strongest evidence is the mismatch between the app's listening port (8000) and probe port (8080).
- Scenario D: A responsible agent should express uncertainty and ask for more diagnostics rather than inventing a root cause.

## Important evaluation caveat
Confidence values are illustrative heuristic scores, not calibrated probabilities. The Learning Agent's history is small and human-labelled. The LLM's output depends on the local model and tool-call behavior.
