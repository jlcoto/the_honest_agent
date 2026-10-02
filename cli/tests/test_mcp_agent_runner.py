"""Tests only the pure logic in mcp_agent_runner.py (argument validation and
tool-schema conversion), which runs before build_mcp_client() imports `mcp`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from agent_quiz_cli.mcp_agent_runner import (
    MCPAgentClient,
    _mcp_tool_to_anthropic_schema,
    build_mcp_client,
)


def test_build_mcp_client_rejects_both_command_and_url():
    with pytest.raises(ValueError, match="not both"):
        build_mcp_client(command="python server.py", url="https://example.com/mcp")


def test_build_mcp_client_requires_one_of_command_or_url():
    with pytest.raises(ValueError, match="neither"):
        build_mcp_client()


def test_build_mcp_client_rejects_empty_command():
    with pytest.raises(ValueError, match="empty"):
        build_mcp_client(command="   ")


@dataclass
class _FakeMCPTool:
    name: str
    description: str | None
    input_schema: dict


def test_mcp_tool_to_anthropic_schema_maps_fields():
    tool = _FakeMCPTool(name="calculator", description="Does math", input_schema={"type": "object"})
    schema = _mcp_tool_to_anthropic_schema(tool)
    assert schema == {
        "name": "calculator",
        "description": "Does math",
        "input_schema": {"type": "object"},
    }


def test_mcp_tool_to_anthropic_schema_handles_missing_description():
    tool = _FakeMCPTool(name="calculator", description=None, input_schema={"type": "object"})
    schema = _mcp_tool_to_anthropic_schema(tool)
    assert schema["description"] == ""


@dataclass
class _FakeToolUseBlock:
    type: str
    id: str
    name: str
    input: dict

    def model_dump(self, mode: str = "python") -> dict:
        return {"type": self.type, "id": self.id, "name": self.name, "input": self.input}


@dataclass
class _FakeTextBlock:
    type: str
    text: str

    def model_dump(self, mode: str = "python") -> dict:
        return {"type": self.type, "text": self.text}


@dataclass
class _FakeUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class _FakeResponse:
    content: list
    usage: _FakeUsage = field(default_factory=_FakeUsage)


class _FakeMessages:
    def __init__(self, responses: list[_FakeResponse]):
        self._responses = list(responses)

    async def create(self, **kwargs):
        return self._responses.pop(0)


@dataclass
class _FakeToolResultBlock:
    type: str
    text: str


@dataclass
class _FakeCallToolResult:
    content: list
    is_error: bool = False


class _FakeMCP:
    async def call_tool(self, name, args):
        return _FakeCallToolResult(content=[_FakeToolResultBlock(type="text", text="2")])


def _make_client(responses: list[_FakeResponse], max_tool_turns: int = 5) -> MCPAgentClient:
    # Bypasses __init__ (which builds a real anthropic.AsyncAnthropic()) so
    # this stays a pure unit test of the loop, no real API key needed.
    client = MCPAgentClient.__new__(MCPAgentClient)
    client._anthropic = type("_FakeAnthropicClient", (), {"messages": _FakeMessages(responses)})()
    client._mcp = _FakeMCP()
    client._model = "claude-test"
    client._max_tool_turns = max_tool_turns
    client._tools_cache = []  # skip list_tools() -- no real MCP tool schema needed for these tests
    return client


def test_run_appends_final_text_only_turn_to_raw_trace():
    """Regression test for the same bug fixed in agent_runner.py: the
    agent's final, text-only turn used to be dropped from raw_trace.
    """
    tool_call = _FakeToolUseBlock(type="tool_use", id="call_1", name="calculator", input={"expression": "1+1"})
    final_text = _FakeTextBlock(type="text", text="The answer is 2.")
    client = _make_client([_FakeResponse(content=[tool_call]), _FakeResponse(content=[final_text])])

    result = asyncio.run(client.run("What is 1+1?"))

    assert result.answer == "The answer is 2."
    assert result.hit_turn_limit is False
    assert len(result.raw_trace) == 4  # user, assistant(tool_use), user(tool_result), assistant(text)
    assert result.raw_trace[-1] == {
        "role": "assistant",
        "content": [{"type": "text", "text": "The answer is 2."}],
    }


def test_run_sums_tokens_across_every_turn():
    tool_call = _FakeToolUseBlock(type="tool_use", id="call_1", name="calculator", input={"expression": "1+1"})
    final_text = _FakeTextBlock(type="text", text="The answer is 2.")
    client = _make_client(
        [
            _FakeResponse(content=[tool_call], usage=_FakeUsage(input_tokens=100, output_tokens=20)),
            _FakeResponse(content=[final_text], usage=_FakeUsage(input_tokens=150, output_tokens=10)),
        ]
    )

    result = asyncio.run(client.run("What is 1+1?"))

    assert result.input_tokens == 250
    assert result.output_tokens == 30


def test_run_reports_error_when_max_tool_turns_exhausted():
    """If Claude is still requesting tools on the very last allowed turn,
    the loop has no further `messages.create` call to let it respond -- so
    `hit_turn_limit` should be set and `answer` should clearly say why,
    rather than silently coming back empty (see the `for...else` in
    MCPAgentClient.run).
    """
    tool_call_1 = _FakeToolUseBlock(type="tool_use", id="call_1", name="calculator", input={"expression": "1+1"})
    tool_call_2 = _FakeToolUseBlock(type="tool_use", id="call_2", name="calculator", input={"expression": "2+2"})
    client = _make_client(
        [_FakeResponse(content=[tool_call_1]), _FakeResponse(content=[tool_call_2])],
        max_tool_turns=2,
    )

    result = asyncio.run(client.run("What is 1+1, then 2+2?"))

    assert result.hit_turn_limit is True
    assert "max_tool_turns=2" in result.answer
    assert result.tools_used == ["calculator", "calculator"]


def test_run_hit_turn_limit_false_when_within_budget():
    final_text = _FakeTextBlock(type="text", text="Paris.")
    client = _make_client([_FakeResponse(content=[final_text])], max_tool_turns=1)

    result = asyncio.run(client.run("What is the capital of France?"))

    assert result.hit_turn_limit is False
    assert result.answer == "Paris."
