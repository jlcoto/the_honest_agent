from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


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
    # True if the tool-use loop hit its max_tool_turns cap while the agent
    # was still requesting tools -- i.e. there was no final, text-only turn
    # to report as `answer`. See MCPAgentClient.run's `for...else`.
    hit_turn_limit: bool = False


def plain_content(content: Any) -> Any:
    """Converts Anthropic SDK content blocks (pydantic models, from
    `response.content`) into plain JSON-safe dicts/lists, leaving content
    that's already plain (our own hand-built tool_result dicts) untouched.

    `MCPAgentClient` calls this before appending a turn to `messages`, so the
    full `messages` list returned as `raw_trace` is always `json.dumps`-able
    as-is -- that's what lets `cli.py` persist it as the agent's
    reasoning/tool-call trace without the caller having to know about the
    SDK's internal block types.
    """
    if isinstance(content, list):
        return [plain_content(item) for item in content]
    if hasattr(content, "model_dump"):
        return content.model_dump(mode="json")
    return content


class AgentClient(ABC):
    """Interface any agent backend must implement to be quizzable.

    `MCPAgentClient` (mcp_agent_runner.py) is currently the only
    implementation -- it sources tools from a live MCP server rather than a
    local stand-in, which is what `honest-agent` needs to test the actual
    agent employees connect to (see mcp_agent_runner.py's module docstring).
    This stays an ABC, rather than `cli.py` depending on `MCPAgentClient`
    directly, so the quiz loop doesn't need to know which concrete backend
    it's driving if another one is ever added.
    """

    @abstractmethod
    async def run(self, prompt: str) -> AgentRunResult: ...
