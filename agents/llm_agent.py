"""LLM Agent (local Ollama model via LangChain, with tool calling).

Decision mechanism: a local LLM (default qwen3:8b served by Ollama) is given
only the pipeline name and run id. To see anything it must call read-only tools
through LangChain tool calling:

    get_pipeline_status, read_build_logs, get_test_results,
    get_recent_change_summary, get_dependency_info, get_deployment_health,
    get_run_history

Safeguards implemented here (rubric: "evidence is checked"):
  1. Minimum tool use - if the model tries to answer after fewer than
     MIN_TOOLS distinct tool calls, it is told to investigate further.
  2. Structured output - the final answer must be JSON with category, evidence,
     cause, next step and checklist; invalid JSON triggers one repair request.
  3. Grounding check - every evidence item must name the tool it came from and
     quote it; the quote is verified against that tool's actual output. The
     grounding score and unverified items are shown in the UI.
  4. Category validation - unknown categories are mapped to UNKNOWN.
"""

import json
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from core.knowledge import CATEGORIES, UNKNOWN
from core.tools import TOOL_FUNCTIONS, call_tool
from agents.base import Decision, checklist_for

MIN_TOOLS = 2
MAX_ITERATIONS = 10

SYSTEM_PROMPT = f"""You are a CI/CD pipeline failure investigator.
You are ADVISORY ONLY: never propose that you change code, edit configuration,
redeploy or roll back yourself - recommend steps for a human to take.

Investigate the failed pipeline run by calling the available tools. Rules:
- Call get_pipeline_status first, then at least one more RELEVANT tool
  (e.g. build logs, test results, recent changes, dependency info,
  deployment health, run history). Call as many as you need.
- Base every claim on tool output. Do not invent facts.
- Watch for misleading signals: a test that fails on a commit that did not touch
  related code, or that passed before on the same commit, may be flaky or an
  infrastructure problem rather than a code bug.

When you have enough evidence, reply with ONLY a JSON object (no markdown):
{{
  "failure_category": one of {CATEGORIES},
  "evidence": [{{"tool": "<tool name>", "quote": "<short plain text copied from that tool's output>"}}],
  "likely_cause": "<one or two sentences>",
  "next_step": "<the single most useful next troubleshooting step for a human>",
  "verification_checklist": ["<post-fix check>", "..."],
  "confidence": <number between 0 and 1>,
  "reasoning": "<2-4 sentences explaining how the evidence leads to the category>"
}}
Each quote must be plain text WITHOUT double-quote characters or braces,
e.g. failed_stage: unit_test   or   AssertionError: assert 81.0 == 90.0"""

# JSON schema for Ollama structured output (guarantees syntactically valid JSON)
FINAL_SCHEMA = {
    "type": "object",
    "properties": {
        "failure_category": {"type": "string", "enum": CATEGORIES},
        "evidence": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"tool": {"type": "string"}, "quote": {"type": "string"}},
                      "required": ["tool", "quote"]},
        },
        "likely_cause": {"type": "string"},
        "next_step": {"type": "string"},
        "verification_checklist": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": ["failure_category", "evidence", "likely_cause", "next_step",
                 "verification_checklist", "confidence", "reasoning"],
}


# ---------------------------------------------------------------- tool schemas
# These @tool functions define the schemas the model sees. Execution is routed
# to core.tools with the *selected scenario*, so every agent sees identical data.
@tool
def get_pipeline_status() -> str:
    """Get the overall pipeline result, the failed stage and the status of every stage."""
    return ""


@tool
def read_build_logs(max_lines: int = 50) -> str:
    """Read the last lines of the build / test / deploy log of the failed run."""
    return ""


@tool
def get_test_results() -> str:
    """Get test totals, failing tests with error type and message, and retry outcome."""
    return ""


@tool
def get_recent_change_summary() -> str:
    """Get the commits since the last green run, with files changed and diff hints."""
    return ""


@tool
def get_dependency_info() -> str:
    """Get dependency manifest details, runner Python version and dependency resolution errors."""
    return ""


@tool
def get_deployment_health() -> str:
    """Get deployment status, health-check results, error rate vs baseline and config changes."""
    return ""


@tool
def get_run_history() -> str:
    """Get recent previous runs of this pipeline (newest first), including failed tests per run."""
    return ""


LC_TOOLS = [get_pipeline_status, read_build_logs, get_test_results, get_recent_change_summary,
            get_dependency_info, get_deployment_health, get_run_history]


# ---------------------------------------------------------------- helpers
def _norm(text: str) -> str:
    text = re.sub(r"[^a-z0-9.=:%/_\-]+", " ", str(text).lower())
    # JSON tool output ('"key": "value"') loses its quotes above and becomes 'key : value',
    # while the model usually quotes it as 'key: value'. Normalise spacing around ':' and '='
    # so both forms match.
    text = re.sub(r"\s*([:=])\s*", r"\1 ", text)
    return re.sub(r"\s+", " ", text).strip()


def verify_quote(quote: str, tool_output: str) -> bool:
    """True if the quote appears in the tool output (exact after normalisation),
    or if >= 80% of its meaningful tokens occur in the output."""
    q, out = _norm(quote), _norm(tool_output)
    if not q:
        return False
    if q in out:
        return True
    tokens = [t for t in q.split() if len(t) > 2]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in out)
    return hits / len(tokens) >= 0.8


def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()


def extract_json(text: str):
    text = strip_thinking(text)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start, depth = text.find("{"), 0
    if start == -1:
        return None
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return None
    return None


def salvage_json(text: str):
    """Last resort when the model's JSON is malformed (e.g. unescaped quotes inside
    an evidence quote): pull the key fields out with regular expressions."""
    text = strip_thinking(text)

    def field(name):
        m = re.search(rf'"{name}"\s*:\s*"(.*?)"\s*(?:,\s*"[a-z_]+"\s*:|}}\s*$)', text, re.DOTALL)
        return m.group(1).strip() if m else ""

    cat = re.search(r'"failure_category"\s*:\s*"([A-Z_]+)"', text)
    if not cat:
        return None
    conf = re.search(r'"confidence"\s*:\s*([0-9.]+)', text)
    evidence = [{"tool": t, "quote": q.strip()} for t, q in re.findall(
        r'"tool"\s*:\s*"([a-z_]+)"\s*,\s*"quote"\s*:\s*(.+?)\s*}', text)]
    return {
        "failure_category": cat.group(1),
        "evidence": [{"tool": e["tool"], "quote": e["quote"].strip('"')} for e in evidence],
        "likely_cause": field("likely_cause"),
        "next_step": field("next_step"),
        "verification_checklist": [],
        "confidence": float(conf.group(1)) if conf else 0.5,
        "reasoning": field("reasoning"),
        "_salvaged": True,
    }


def make_ollama_llm(model: str, base_url: str, temperature: float = 0.0, think: bool = False,
                    json_schema: dict = None):
    from langchain_ollama import ChatOllama
    kwargs = {"format": json_schema} if json_schema else {}
    return ChatOllama(model=model, base_url=base_url, temperature=temperature,
                      reasoning=think, num_ctx=8192, **kwargs)


# ---------------------------------------------------------------- agent
class LLMAgent:
    name = "LLM (Ollama + tools)"
    mechanism = "Local LLM via LangChain; investigates by tool calling; grounded, verified JSON answer"

    def __init__(self, model: str = "qwen3:8b", base_url: str = "http://localhost:11434",
                 temperature: float = 0.0, think: bool = False, llm=None, json_llm=None):
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.think = think
        self._llm = llm  # injectable (used by tests with a fake chat model)
        self._json_llm = json_llm if json_llm is not None else llm

    def _get_llm(self):
        if self._llm is None:
            self._llm = make_ollama_llm(self.model, self.base_url, self.temperature, self.think)
        return self._llm

    def _get_json_llm(self):
        """Same model, but Ollama is forced to emit JSON matching FINAL_SCHEMA."""
        if self._json_llm is None:
            self._json_llm = make_ollama_llm(self.model, self.base_url, self.temperature, False,
                                             json_schema=FINAL_SCHEMA)
        return self._json_llm

    def _execute(self, name: str, args: dict, scenario: dict) -> str:
        if name not in TOOL_FUNCTIONS:
            return json.dumps({"error": f"unknown tool '{name}'", "available": list(TOOL_FUNCTIONS)})
        if name == "read_build_logs" and isinstance(args, dict) and "max_lines" in args:
            try:
                return json.dumps(TOOL_FUNCTIONS[name](scenario, int(args["max_lines"])), indent=1)
            except (TypeError, ValueError):
                pass
        return call_tool(name, scenario)

    def decide(self, scenario: dict) -> Decision:
        t0 = time.time()
        trace, tool_log = [], []
        try:
            llm = self._get_llm()
            llm_tools = llm.bind_tools(LC_TOOLS)
            ps = scenario["pipeline_status"]
            messages = [
                SystemMessage(SYSTEM_PROMPT),
                HumanMessage(f"Pipeline '{ps['pipeline']}' run {ps['run_id']} failed. "
                             "Investigate with the tools and give your JSON assessment."),
            ]
            final_text = None
            for it in range(1, MAX_ITERATIONS + 1):
                ai = llm_tools.invoke(messages)
                messages.append(ai)
                if ai.tool_calls:
                    for tc in ai.tool_calls:
                        out = self._execute(tc["name"], tc.get("args") or {}, scenario)
                        tool_log.append({"step": it, "tool": tc["name"], "args": tc.get("args") or {},
                                         "output": out})
                        trace.append(f"Step {it}: called {tc['name']}({tc.get('args') or ''})")
                        messages.append(ToolMessage(content=out, tool_call_id=tc.get("id") or tc["name"]))
                    continue
                distinct = {t["tool"] for t in tool_log if t["tool"] in TOOL_FUNCTIONS}
                if len(distinct) < MIN_TOOLS:
                    trace.append(f"Step {it}: model answered after {len(distinct)} tool(s) - "
                                 f"asked to call at least {MIN_TOOLS} relevant tools")
                    messages.append(HumanMessage(
                        f"You have used {len(distinct)} tool(s). Call at least {MIN_TOOLS} different relevant "
                        "tools before answering."))
                    continue
                final_text = ai.content
                trace.append(f"Step {it}: model produced final answer")
                break

            if final_text is None:
                messages.append(HumanMessage("Stop calling tools. Reply now with ONLY the JSON object."))
                final_text = llm.invoke(messages).content
                trace.append("Max iterations reached - requested final answer")

            result = extract_json(final_text)
            if result is None:
                # Repair 1: ask again with Ollama structured output (schema-constrained JSON)
                trace.append("Final answer was not valid JSON - re-asked with Ollama structured output (JSON schema)")
                messages.append(HumanMessage(
                    "Your last answer was not valid JSON. Using only the tool results above, reply with the "
                    "JSON object again. Quotes must be plain text without double-quote characters."))
                try:
                    repaired = self._get_json_llm().invoke(messages).content
                    result = extract_json(repaired)
                    if result is not None:
                        final_text = repaired
                except Exception as exc:  # keep going to the salvage step
                    trace.append(f"Structured-output retry failed: {type(exc).__name__}: {exc}"[:200])
            if result is None:
                # Repair 2: salvage the key fields from the malformed text
                result = salvage_json(final_text)
                if result is not None:
                    trace.append("Salvaged category/cause/next step from malformed JSON with regex parsing")
            if result is None:
                raise ValueError("LLM did not return parseable JSON: " + strip_thinking(final_text)[:300])

            return self._build_decision(result, tool_log, trace, final_text, time.time() - t0)

        except Exception as exc:  # Ollama not running, model missing, etc.
            msg = f"{type(exc).__name__}: {exc}"
            trace.append(f"ERROR: {msg}")
            return Decision(
                agent=self.name, mechanism=self.mechanism, failure_category=UNKNOWN,
                evidence=[], likely_cause=f"LLM agent unavailable ({msg[:200]})",
                next_step=("Re-run the scenario; if it repeats, try another model (e.g. qwen3:4b / llama3.1:8b)."
                           if isinstance(exc, ValueError) else
                           f"Start Ollama (`ollama serve`) and pull the model (`ollama pull {self.model}`), then re-run."),
                verification_checklist=checklist_for(UNKNOWN), reasoning=trace, confidence=0.0,
                details={"error": msg, "tool_calls": tool_log, "model": self.model},
            )

    def _build_decision(self, result: dict, tool_log: list, trace: list, raw: str, elapsed: float) -> Decision:
        outputs_by_tool = {}
        for t in tool_log:
            outputs_by_tool.setdefault(t["tool"], []).append(t["output"])

        checked, evidence_lines = [], []
        for item in result.get("evidence") or []:
            if isinstance(item, str):
                item = {"tool": "?", "quote": item}
            tool_name, quote = str(item.get("tool", "?")), str(item.get("quote", ""))
            pool = "\n".join(outputs_by_tool.get(tool_name, [])) or "\n".join(
                o for outs in outputs_by_tool.values() for o in outs)
            ok = verify_quote(quote, pool)
            same_tool = tool_name in outputs_by_tool
            checked.append({"tool": tool_name, "quote": quote, "verified": ok, "tool_was_called": same_tool})
            evidence_lines.append(f"[{tool_name}] {quote}  {'(verified)' if ok else '(NOT found in tool output)'}")

        n_ok = sum(c["verified"] for c in checked)
        grounding = round(n_ok / len(checked), 2) if checked else 0.0
        category = str(result.get("failure_category", UNKNOWN)).strip().upper()
        if category not in CATEGORIES:
            trace.append(f"Category '{category}' not in allowed list - mapped to UNKNOWN")
            category = UNKNOWN

        distinct_tools = sorted({t["tool"] for t in tool_log})
        trace.append(f"Tools used ({len(distinct_tools)} distinct): {', '.join(distinct_tools)}")
        trace.append(f"Grounding check: {n_ok}/{len(checked)} evidence quotes found in tool outputs")
        if result.get("reasoning"):
            trace.append(f"Model reasoning: {result['reasoning']}")

        try:
            conf = float(result.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        # penalise confidence when evidence is not grounded
        conf = round(max(0.0, min(1.0, conf)) * (0.5 + 0.5 * grounding), 2)

        checklist = result.get("verification_checklist") or checklist_for(category)
        if isinstance(checklist, str):
            checklist = [checklist]
        return Decision(
            agent=self.name, mechanism=self.mechanism, failure_category=category,
            evidence=evidence_lines, likely_cause=str(result.get("likely_cause", "")),
            next_step=str(result.get("next_step", "")), verification_checklist=list(checklist),
            reasoning=trace, confidence=conf,
            details={"model": self.model, "tool_calls": tool_log, "distinct_tools": distinct_tools,
                     "grounding_score": grounding, "evidence_check": checked,
                     "raw_response": strip_thinking(raw), "elapsed_s": round(elapsed, 1)},
        )
