"""Run all agents on all scenarios and write the test-results report.

Usage:
    python run_scenarios.py                 # classical agents + LLM agent (needs Ollama)
    python run_scenarios.py --no-llm        # classical agents only
    python run_scenarios.py --model qwen3:8b --base-url http://localhost:11434

Outputs:
    test_results/results.md    - comparison tables + per-agent details
    test_results/results.json  - full machine-readable decisions
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

from agents import (GoalBasedAgent, LearningAgent, ModelBasedReflexAgent,
                    SimpleReflexAgent, UtilityBasedAgent)
from agents.learning_agent import SEED_PATH
from agents.llm_agent import LLMAgent
from core.compare import comparison_rows, explain_differences
from core.scenarios import SCENARIO_IDS, SCENARIOS, get_scenario

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_results")


def md_table(rows, cols):
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(c, "")).replace("|", "/").replace("\n", " ") for c in cols) + " |")
    return "\n".join(out)


def main():
    # Windows consoles/redirects default to cp1252, which cannot print the check marks
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--base-url", default="http://localhost:11434")
    args = ap.parse_args()

    # learning agent works on a temporary copy of the seed so the report is reproducible
    tmp = os.path.join(tempfile.mkdtemp(), "experience.json")
    shutil.copy(SEED_PATH, tmp)
    agents = [SimpleReflexAgent(), ModelBasedReflexAgent(), GoalBasedAgent(), UtilityBasedAgent(),
              LearningAgent(tmp)]
    llm = None if args.no_llm else LLMAgent(model=args.model, base_url=args.base_url)

    os.makedirs(OUT_DIR, exist_ok=True)
    all_json, md = {}, []
    md.append("# Test results - Intelligent CI/CD Pipeline Failure Assistant (Group 7)\n")
    md.append(f"Generated: {datetime.now():%Y-%m-%d %H:%M}  \n"
              f"LLM agent: {'disabled (--no-llm)' if llm is None else args.model + ' via Ollama'}\n")

    matrix = []
    for sid in SCENARIO_IDS:
        sc = SCENARIOS[sid]
        decisions = {a.name: a.decide(get_scenario(sid)) for a in agents}
        if llm:
            print(f"[{sid}] running LLM agent ({args.model}) ...", flush=True)
            decisions[llm.name] = llm.decide(get_scenario(sid))
        all_json[sid] = {n: d.to_dict() for n, d in decisions.items()}

        row = {"Scenario": sc["name"], "Expected": sc["expected_category"]}
        for n, d in decisions.items():
            row[n] = d.failure_category + (" ✓" if d.failure_category == sc["expected_category"] else " ✗")
        matrix.append(row)

        md.append(f"\n## Scenario {sc['name']}  ({sc['type']})\n")
        md.append(sc["description"] + "\n")
        md.append(f"**Expected category:** `{sc['expected_category']}`\n")
        md.append(md_table(comparison_rows(sid, decisions),
                           ["Agent", "Failure category", "Correct", "Confidence", "Recommended next step"]))
        md.append("\n### Why decisions differ\n")
        md.extend(explain_differences(sid, decisions))
        md.append("\n### Agent details\n")
        for n, d in decisions.items():
            md.append(f"<details><summary><b>{n}</b> - {d.failure_category}</summary>\n")
            md.append(f"- **Mechanism:** {d.mechanism}")
            md.append(f"- **Likely cause:** {d.likely_cause}")
            md.append(f"- **Next step:** {d.next_step}")
            md.append("- **Evidence:**\n" + "\n".join(f"  - {e}" for e in d.evidence))
            md.append("- **Verification checklist:**\n" + "\n".join(f"  - [ ] {c}" for c in d.verification_checklist))
            md.append("- **Reasoning trace:**\n" + "\n".join(f"  - {r}" for r in d.reasoning))
            md.append("\n</details>\n")

    cols = ["Scenario", "Expected"] + [n for n in matrix[0] if n not in ("Scenario", "Expected")]
    summary = ["\n## Summary matrix (all scenarios x all agents)\n", md_table(matrix, cols), ""]
    md[2:2] = summary

    with open(os.path.join(OUT_DIR, "results.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))
    with open(os.path.join(OUT_DIR, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(all_json, fh, indent=2, default=str)
    print("\n".join(summary))
    print(f"Wrote {OUT_DIR}/results.md and results.json")


if __name__ == "__main__":
    main()
