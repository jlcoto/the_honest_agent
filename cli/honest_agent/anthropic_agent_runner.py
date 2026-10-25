"""An AgentClient that evaluates an Anthropic model (Claude) against a live MCP
server; openai_agent_runner.py runs the same loop on OpenAI's API.

The tools come from the live MCP server (listed once per run, see cli.py and
mcp_client.py), never a local stand-in, so `tools_used` and provenance's SQL
checking reflect exactly what a real MCP-connected agent can call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .agent_runner import AgentClient, plain_content

if TYPE_CHECKING:
    from .raw import EvalRecorder

# Output cap per model turn. Models that think before answering spend part of it on that,
# so it leaves room; only the tokens used are billed. A turn cut off by it shows
# stop_reason "max_tokens" in its recorded response, and derive.py reports it.
MAX_TOKENS = 8192


def _mcp_tool_to_anthropic_schema(tool: Any) -> dict:
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema,
    }


class AnthropicMCPAgentClient(AgentClient):
    """Claude as the agent, with the tools of a live, already-connected `mcp.Client`."""

    def __init__(
        self,
        mcp_client,
        model: str,
        tools: list,
        max_tool_steps: int = 5,
        instructions: str | None = None,
        client: Any = None,
    ):
        if client is None:
            import anthropic

            client = anthropic.AsyncAnthropic()
        self._anthropic = client
        self._mcp = mcp_client
        self._model = model
        self._tools = [_mcp_tool_to_anthropic_schema(t) for t in tools]
        self._max_tool_steps = max_tool_steps
        # The server's instructions, sent as the system prompt like Claude's own clients do.
        self._system = [{"type": "text", "text": instructions}] if instructions else []
        # Tools and system are the same in every call: one cache breakpoint at their end
        # caches both. A prompt below the model's minimum is sent uncached, without error.
        last = self._system or self._tools
        if last:
            last[-1]["cache_control"] = {"type": "ephemeral"}

    async def run(self, prompt: str, record: EvalRecorder) -> None:
        messages: list[dict] = [{"role": "user", "content": prompt}]
        already_recorded = 0  # messages earlier events hold: past requests, and responses
        # When the loop runs out of steps while Claude still asks for tools, there is no
        # final answer; derive.py reads that from the last recorded response.
        for _ in range(self._max_tool_steps):
            request = {
                "model": self._model,
                "max_tokens": MAX_TOKENS,
                "tools": [tool["name"] for tool in self._tools],  # in full in raw.runs.tools_offered
                "messages": messages[already_recorded:],
            }
            if self._system:
                request["system"] = "server instructions"  # in full in raw.runs.settings
            optional = {"system": self._system} if self._system else {}
            response = await record.call(
                "model_call",
                "anthropic",
                request,
                self._anthropic.messages.create(
                    model=self._model, max_tokens=MAX_TOKENS, tools=self._tools, messages=messages, **optional
                ),
            )
            messages.append({"role": "assistant", "content": plain_content(response.content)})
            already_recorded = len(messages)  # the reply just appended is that call's response
            tool_calls = [block for block in response.content if block.type == "tool_use"]
            if not tool_calls:
                return

            tool_results = []
            for call in tool_calls:
                result = await record.call(
                    "tool_call",
                    "mcp",
                    {"tool_use_id": call.id, "name": call.name, "arguments": call.input},
                    self._mcp.call_tool(call.name, call.input),
                )
                text = "\n".join(block.text for block in result.content if getattr(block, "type", None) == "text")
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": call.id, "content": text, "is_error": result.is_error}
                )
            messages.append({"role": "user", "content": tool_results})
