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

# Output cap per model turn. A turn cut off by it shows stop_reason "max_tokens" in its
# recorded response.
MAX_TOKENS = 1024


def _mcp_tool_to_anthropic_schema(tool: Any) -> dict:
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema,
    }


class AnthropicMCPAgentClient(AgentClient):
    """Claude as the agent, with the tools of a live, already-connected `mcp.Client`."""

    def __init__(self, mcp_client, model: str, tools: list, max_tool_turns: int = 5):
        import anthropic

        self._anthropic = anthropic.AsyncAnthropic()
        self._mcp = mcp_client
        self._model = model
        self._tools = [_mcp_tool_to_anthropic_schema(t) for t in tools]
        self._max_tool_turns = max_tool_turns

    async def run(self, prompt: str, record: EvalRecorder) -> None:
        messages: list[dict] = [{"role": "user", "content": prompt}]
        already_recorded = 0  # messages earlier events hold: past requests, and responses
        # When the loop runs out of turns while Claude still asks for tools, there is no
        # final answer; derive.py reads that from the last recorded response.
        for _ in range(self._max_tool_turns):
            request = {
                "model": self._model,
                "max_tokens": MAX_TOKENS,
                "tools": [tool["name"] for tool in self._tools],  # in full in raw.runs.tools_offered
                "messages": messages[already_recorded:],
            }
            response = await record.call(
                "model_call",
                "anthropic",
                request,
                self._anthropic.messages.create(
                    model=self._model, max_tokens=MAX_TOKENS, tools=self._tools, messages=messages
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
