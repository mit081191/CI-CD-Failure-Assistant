"""A scripted stand-in for ChatOllama so the LLM agent's tool-calling loop,
minimum-tool enforcement and grounding check can be tested without Ollama."""

from langchain_core.messages import AIMessage


class FakeToolLLM:
    def __init__(self, script):
        """script: list of AIMessage objects returned in order by invoke()."""
        self.script = list(script)
        self.calls = 0
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = [t.name for t in tools]
        return self

    def invoke(self, messages):
        self.calls += 1
        if not self.script:
            return AIMessage(content="{}")
        return self.script.pop(0)


def tool_call(name, args=None, cid=None):
    return {"name": name, "args": args or {}, "id": cid or f"call_{name}", "type": "tool_call"}