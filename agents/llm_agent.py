"""Local Ollama Qwen3 agent using LangChain tool calling."""
import json
from langchain_core.tools import tool
from langchain_ollama import ChatOllama

@tool
def get_pipeline_status(scenario_json: str) -> str:
    """Read the pipeline status and deployment health from the selected scenario."""
    s = json.loads(scenario_json)
    return json.dumps({"pipeline_status": s.get("pipeline_status"), "deployment_health": s.get("deployment_health")})

@tool
def read_build_logs(scenario_json: str) -> str:
    """Read build logs and extract the supplied build-log evidence."""
    s = json.loads(scenario_json)
    return json.dumps({"build_logs": s.get("build_logs", "")})

@tool
def get_test_results(scenario_json: str) -> str:
    """Read unit and integration test results for the selected scenario."""
    s = json.loads(scenario_json)
    return json.dumps({"test_results": s.get("test_results", "")})

@tool
def get_recent_change_summary(scenario_json: str) -> str:
    """Read recent code changes and dependency information."""
    s = json.loads(scenario_json)
    return json.dumps({"recent_change_summary": s.get("recent_change_summary"), "dependency_info": s.get("dependency_info")})

TOOLS = [get_pipeline_status, read_build_logs, get_test_results, get_recent_change_summary]

def run_llm_agent(scenario, model="qwen3:8b", max_tool_rounds=5):
    """Call Qwen3 locally. The model must request tools; their outputs are fed back."""
    llm = ChatOllama(model=model, temperature=0)
    llm_tools = llm.bind_tools(TOOLS)
    scenario_json = json.dumps(scenario)
    messages = [
        ("system",
         "You are a cautious CI/CD failure investigation assistant. Diagnose only from tool-returned evidence. "
         "You MUST call at least two relevant tools before recommending. Never change code, restart services, "
         "rollback, or deploy. Return a JSON object with keys: failure_category, supporting_evidence (array), "
         "likely_cause, recommended_next_step, reasoning, verification_checklist (array), confidence (0 to 1). "
         "If evidence is insufficient, say so and recommend collecting diagnostics."),
        ("human", "Investigate this selected scenario. Scenario data is provided only as tool input: " + scenario_json)
    ]
    tool_calls_made = []
    for _ in range(max_tool_rounds):
        response = llm_tools.invoke(messages)
        messages.append(response)
        calls = getattr(response, "tool_calls", [])
        if not calls:
            content = response.content
            if isinstance(content, list):
                content = "".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in content)
            try:
                result = json.loads(content)
            except Exception:
                result = {
                    "failure_category": "LLM response needs review",
                    "supporting_evidence": [],
                    "likely_cause": "The model did not return valid JSON.",
                    "recommended_next_step": "Review the model response and inspect the pipeline evidence manually.",
                    "reasoning": str(content),
                    "verification_checklist": ["Validate the diagnosis against raw pipeline logs."],
                    "confidence": 0.2
                }
            result["tools_called"] = tool_calls_made
            result["agent"] = "LLM (Ollama)"
            return result
        for call in calls:
            name = call["name"]
            args = dict(call["args"])
            # The selected scenario is the only permitted diagnostic data source.
            args["scenario_json"] = scenario_json
            tool = next(t for t in TOOLS if t.name == name)
            tool_result = tool.invoke(args)
            tool_calls_made.append(name)
            from langchain_core.messages import ToolMessage
            messages.append(ToolMessage(content=str(tool_result), tool_call_id=call["id"]))
    raise RuntimeError("LLM exceeded the tool-call limit without producing a final recommendation.")
