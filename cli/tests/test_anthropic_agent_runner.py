"""The Claude agent loop and its tool-schema conversion, with a fake Anthropic client and
MCP server (no API key or network needed)."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field

from honest_agent.anthropic_agent_runner import MAX_TOKENS, AnthropicMCPAgentClient, _mcp_tool_to_anthropic_schema


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
        self.sent: list[list[dict]] = []  # the full `messages` of each call
        self.kwargs: list[dict] = []  # everything else each call was given

    async def create(self, **kwargs):
        self.sent.append(copy.deepcopy(kwargs["messages"]))
        self.kwargs.append(copy.deepcopy({k: v for k, v in kwargs.items() if k != "messages"}))
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


class _Recorder:
    """Stands in for raw.EvalRecorder: keeps what each call was recorded with."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def call(self, kind, provider, request, pending):
        self.calls.append((kind, provider, copy.deepcopy(request)))
        return await pending


def _make_client(
    responses: list[_FakeResponse], max_tool_steps: int = 5, instructions: str | None = None
) -> AnthropicMCPAgentClient:
    # A fake Anthropic client, so this stays a pure unit test of the loop, no API key needed.
    return AnthropicMCPAgentClient(
        _FakeMCP(),
        model="claude-test",
        tools=[_FakeMCPTool(name="calculator", description="Does math", input_schema={})],
        max_tool_steps=max_tool_steps,
        instructions=instructions,
        client=type("_FakeAnthropicClient", (), {"messages": _FakeMessages(responses)})(),
    )


def _two_turns() -> list[_FakeResponse]:
    tool_call = _FakeToolUseBlock(type="tool_use", id="call_1", name="calculator", input={"expression": "1+1"})
    return [_FakeResponse(content=[tool_call]), _FakeResponse(content=[_FakeTextBlock(type="text", text="2")])]


def test_run_records_each_model_and_tool_call_in_order():
    client, recorder = _make_client(_two_turns()), _Recorder()

    asyncio.run(client.run("What is 1+1?", recorder))

    assert [(kind, provider) for kind, provider, _ in recorder.calls] == [
        ("model_call", "anthropic"),
        ("tool_call", "mcp"),
        ("model_call", "anthropic"),
    ]
    assert recorder.calls[1][2] == {"tool_use_id": "call_1", "name": "calculator", "arguments": {"expression": "1+1"}}


def test_a_model_calls_request_leaves_out_what_earlier_events_hold():
    """Claude gets the whole conversation every turn; the record keeps only what's new:
    the prompt first, then the tool results (the reply before them is the last response)."""
    client, recorder = _make_client(_two_turns()), _Recorder()

    asyncio.run(client.run("What is 1+1?", recorder))

    first, second = recorder.calls[0][2], recorder.calls[2][2]
    assert first == {
        "model": "claude-test",
        "max_tokens": MAX_TOKENS,
        "tools": ["calculator"],
        "messages": [{"role": "user", "content": "What is 1+1?"}],
    }
    assert second["messages"] == [
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "2", "is_error": False}],
        }
    ]
    assert len(client._anthropic.messages.sent[1]) == 3  # Claude itself got all three


def test_run_stops_at_max_tool_steps():
    tool_call = _FakeToolUseBlock(type="tool_use", id="call_1", name="calculator", input={"expression": "1+1"})
    client, recorder = _make_client([_FakeResponse(content=[tool_call])] * 2, max_tool_steps=2), _Recorder()

    asyncio.run(client.run("Keep going", recorder))

    assert [kind for kind, _, _ in recorder.calls] == ["model_call", "tool_call", "model_call", "tool_call"]


def test_server_instructions_go_in_the_system_prompt_with_the_cache_breakpoint():
    client, recorder = _make_client(_two_turns(), instructions="Use DuckDB SQL."), _Recorder()

    asyncio.run(client.run("What is 1+1?", recorder))

    for kwargs in client._anthropic.messages.kwargs:
        assert kwargs["system"] == [{"type": "text", "text": "Use DuckDB SQL.", "cache_control": {"type": "ephemeral"}}]
        assert "cache_control" not in kwargs["tools"][-1]  # one breakpoint, after tools and system
    # The record names the system prompt; its text is in the run's settings, once.
    assert recorder.calls[0][2]["system"] == "server instructions"


def test_without_instructions_the_tools_carry_the_cache_breakpoint():
    client, recorder = _make_client(_two_turns()), _Recorder()

    asyncio.run(client.run("What is 1+1?", recorder))

    kwargs = client._anthropic.messages.kwargs[0]
    assert "system" not in kwargs
    assert kwargs["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "system" not in recorder.calls[0][2]
