from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class AgentRunResult:
    answer: str
    tools_used: list[str]
    raw_trace: Any
    model_name: str
    latency_ms: int
    # Summed across every turn of the tool-use loop (each turn is its own
    # `messages.create` call, so a multi-turn quiz genuinely spends tokens
    # more than once) -- not just the final turn's usage.
    input_tokens: int
    output_tokens: int


def plain_content(content: Any) -> Any:
    """Converts Anthropic SDK content blocks (pydantic models, from
    `response.content`) into plain JSON-safe dicts/lists, leaving content
    that's already plain (our own hand-built tool_result dicts) untouched.

    Both agent backends call this before appending a turn to `messages`, so
    the full `messages` list returned as `raw_trace` is always
    `json.dumps`-able as-is -- that's what lets `cli.py` persist it as the
    agent's reasoning/tool-call trace without each caller having to know
    about the SDK's internal block types.
    """
    if isinstance(content, list):
        return [plain_content(item) for item in content]
    if hasattr(content, "model_dump"):
        return content.model_dump(mode="json")
    return content


class AgentClient(ABC):
    """Interface any agent backend must implement to be quizzable.

    Claude-with-local-tools is the first implementation; MCPAgentClient
    (mcp_agent_runner.py) is the second, sourcing tools from a live MCP
    server instead. Both are async because the MCP SDK is async-native --
    every backend implements the same async interface so the CLI's quiz
    loop doesn't need to know which one it's driving.
    """

    @abstractmethod
    async def run(self, prompt: str, tools: list[dict] | None = None) -> AgentRunResult: ...


class ClaudeAgentClient(AgentClient):
    """Runs a quiz prompt against Claude via the Messages API, executing any
    tool calls locally against `tool_executors` and looping until Claude
    stops asking for tools (or `max_tool_turns` is hit).
    """

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        tool_executors: dict[str, Callable[[dict], str]] | None = None,
        max_tool_turns: int = 5,
    ):
        import anthropic

        self._client = anthropic.AsyncAnthropic()
        self._model = model
        self._tool_executors = tool_executors or {}
        self._max_tool_turns = max_tool_turns

    async def run(self, prompt: str, tools: list[dict] | None = None) -> AgentRunResult:
        start = time.monotonic()
        messages: list[dict] = [{"role": "user", "content": prompt}]
        tools_used: list[str] = []
        response = None
        input_tokens = 0
        output_tokens = 0

        for _ in range(self._max_tool_turns):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                tools=tools or [],
                messages=messages,
            )
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens
            tool_calls = [block for block in response.content if block.type == "tool_use"]
            if not tool_calls:
                # Final, text-only turn -- append it so `raw_trace` captures the
                # agent's actual stated answer, not just what led up to it.
                messages.append({"role": "assistant", "content": plain_content(response.content)})
                break

            messages.append({"role": "assistant", "content": plain_content(response.content)})
            tool_results = []
            for call in tool_calls:
                tools_used.append(call.name)
                executor = self._tool_executors.get(call.name)
                if executor is None:
                    output = f"error: no local executor registered for tool '{call.name}'"
                else:
                    output = str(executor(call.input))
                tool_results.append({"type": "tool_result", "tool_use_id": call.id, "content": output})
            messages.append({"role": "user", "content": tool_results})

        final_text = "".join(block.text for block in (response.content if response else []) if block.type == "text")
        latency_ms = int((time.monotonic() - start) * 1000)

        return AgentRunResult(
            answer=final_text.strip(),
            tools_used=tools_used,
            raw_trace=messages,
            model_name=self._model,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
