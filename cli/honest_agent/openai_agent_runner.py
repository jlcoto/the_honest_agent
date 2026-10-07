"""An AgentClient that evaluates an OpenAI model (GPT) against a live MCP server --
the same loop as MCPAgentClient (mcp_agent_runner.py), on OpenAI's Chat
Completions API instead of Anthropic's.

Every call is recorded as OpenAI sent and returned it (raw.py); derive.py turns
the record into the one conversation format the rest of honest-agent reads, so
nothing downstream needs to know which provider ran the eval.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .agent_runner import AgentClient
from .llm import openai_client

if TYPE_CHECKING:
    from .raw import EvalRecorder


def _mcp_tool_to_openai_schema(tool: Any) -> dict:
    return {
        "type": "function",
        "function": {"name": tool.name, "description": tool.description or "", "parameters": tool.input_schema},
    }


class OpenAIMCPAgentClient(AgentClient):
    """GPT as the agent, with the tools of a live, already-connected `mcp.Client`."""

    def __init__(self, mcp_client, model: str, tools: list, max_tool_turns: int = 5, client: Any = None):
        self._openai = client or openai_client()
        self._mcp = mcp_client
        self._model = model
        self._tools = [_mcp_tool_to_openai_schema(t) for t in tools]
        self._max_tool_turns = max_tool_turns

    async def run(self, prompt: str, record: EvalRecorder) -> None:
        chat: list[dict] = [{"role": "user", "content": prompt}]
        already_recorded = 0  # messages earlier events hold: past requests, and responses
        for _ in range(self._max_tool_turns):
            # No max_completion_tokens: on reasoning models it also counts hidden
            # reasoning tokens, so a cap can cut off the answer itself.
            request = {
                "model": self._model,
                "tools": [tool["function"]["name"] for tool in self._tools],  # in full in raw.runs.tools_offered
                "messages": chat[already_recorded:],
            }
            response = await record.call(
                "model_call",
                "openai",
                request,
                self._openai.chat.completions.create(model=self._model, messages=chat, tools=self._tools),
            )
            message = response.choices[0].message
            calls = message.tool_calls or []
            chat.append(
                {
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.function.name, "arguments": call.function.arguments},
                        }
                        for call in calls
                    ]
                    or None,
                }
            )
            already_recorded = len(chat)  # the reply just appended is that call's response
            if not calls:
                return

            for call in calls:
                arguments = json.loads(call.function.arguments or "{}")
                result = await record.call(
                    "tool_call",
                    "mcp",
                    {"tool_use_id": call.id, "name": call.function.name, "arguments": arguments},
                    self._mcp.call_tool(call.function.name, arguments),
                )
                result_text = "\n".join(
                    block.text for block in result.content if getattr(block, "type", None) == "text"
                )
                chat.append({"role": "tool", "tool_call_id": call.id, "content": result_text})
