"""An AgentClient that quizzes an OpenAI model (GPT) against a live MCP server --
the same loop as MCPAgentClient (mcp_agent_runner.py), on OpenAI's Chat
Completions API instead of Anthropic's.

The conversation is sent to OpenAI in its own message format, but the trace it
returns is recorded in the format MCPAgentClient produces (`tool_use` blocks
with `input`, `tool_result` blocks linked by `tool_use_id`). sql_capture.py,
provenance scoring, storage, and the report's trace view all read that one
format, so none of them needs to know which provider ran the quiz.
"""

from __future__ import annotations

import json
import time
from typing import Any

from .agent_runner import AgentClient, AgentRunResult
from .llm import openai_client


def _mcp_tool_to_openai_schema(tool: Any) -> dict:
    return {
        "type": "function",
        "function": {"name": tool.name, "description": tool.description or "", "parameters": tool.input_schema},
    }


class OpenAIMCPAgentClient(AgentClient):
    """Sources its tools from a live, already-connected `mcp.Client`."""

    def __init__(self, mcp_client, model: str, max_tool_turns: int = 5, client: Any = None):
        self._openai = client or openai_client()
        self._mcp = mcp_client
        self._model = model
        self._max_tool_turns = max_tool_turns
        self._tools_cache: list[dict] | None = None

    async def _list_tools(self) -> list[dict]:
        if self._tools_cache is None:
            result = await self._mcp.list_tools()
            self._tools_cache = [_mcp_tool_to_openai_schema(t) for t in result.tools]
        return self._tools_cache

    async def run(self, prompt: str) -> AgentRunResult:
        start = time.monotonic()
        available_tools = await self._list_tools()
        chat: list[dict] = [{"role": "user", "content": prompt}]  # sent to OpenAI
        trace: list[dict] = [{"role": "user", "content": prompt}]  # stored, in the shared format
        tools_used: list[str] = []
        final_text = ""
        input_tokens = 0
        output_tokens = 0
        hit_turn_limit = False

        for _ in range(self._max_tool_turns):
            # No max_completion_tokens: on reasoning models it also counts hidden
            # reasoning tokens, so a cap can cut off the answer itself.
            response = await self._openai.chat.completions.create(
                model=self._model, messages=chat, tools=available_tools
            )
            input_tokens += response.usage.prompt_tokens
            output_tokens += response.usage.completion_tokens
            message = response.choices[0].message
            text = message.content or ""
            calls = message.tool_calls or []
            arguments = {call.id: json.loads(call.function.arguments or "{}") for call in calls}

            trace.append(
                {
                    "role": "assistant",
                    "content": ([{"type": "text", "text": text}] if text else [])
                    + [
                        {"type": "tool_use", "id": call.id, "name": call.function.name, "input": arguments[call.id]}
                        for call in calls
                    ],
                }
            )
            if not calls:
                final_text = text
                break

            chat.append(
                {
                    "role": "assistant",
                    "content": text or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.function.name, "arguments": call.function.arguments},
                        }
                        for call in calls
                    ],
                }
            )
            tool_results = []
            for call in calls:
                tools_used.append(call.function.name)
                result = await self._mcp.call_tool(call.function.name, arguments[call.id])
                result_text = "\n".join(
                    block.text for block in result.content if getattr(block, "type", None) == "text"
                )
                chat.append({"role": "tool", "tool_call_id": call.id, "content": result_text})
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": call.id, "content": result_text, "is_error": result.is_error}
                )
            trace.append({"role": "user", "content": tool_results})
        else:
            # Same as MCPAgentClient: the loop ran out of turns while the model was
            # still requesting tools, so there's no final answer to report.
            hit_turn_limit = True
            final_text = (
                f"[agent_quiz error] Exceeded max_tool_turns={self._max_tool_turns} without a final answer -- "
                "the agent was still requesting tools on the last turn. See agent_trace for detail."
            )

        return AgentRunResult(
            answer=final_text.strip(),
            tools_used=tools_used,
            raw_trace=trace,
            model_name=self._model,
            latency_ms=int((time.monotonic() - start) * 1000),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            hit_turn_limit=hit_turn_limit,
        )
