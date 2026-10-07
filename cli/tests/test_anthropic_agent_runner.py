"""The Claude agent loop and its tool-schema conversion, with a fake Anthropic client and
MCP server (no API key or network needed)."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field

from honest_agent.anthropic_agent_runner import AnthropicMCPAgentClient, _mcp_tool_to_anthropic_schema


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

    async def create(self, **kwargs):
        self.sent.append(copy.deepcopy(kwargs["messages"]))
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


def _make_client(responses: list[_FakeResponse], max_tool_turns: int = 5) -> AnthropicMCPAgentClient:
    # Bypasses __init__ (which builds a real anthropic.AsyncAnthropic()) so
    # this stays a pure unit test of the loop, no real API key needed.
    client = AnthropicMCPAgentClient.__new__(AnthropicMCPAgentClient)
    client._anthropic = type("_FakeAnthropicClient", (), {"messages": _FakeMessages(responses)})()
    client._mcp = _FakeMCP()
    client._model = "claude-test"
    client._max_tool_turns = max_tool_turns
    client._tools = [{"name": "calculator", "description": "Does math", "input_schema": {}}]
    return client


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
        "max_tokens": 1024,
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


def test_run_stops_at_max_tool_turns():
    tool_call = _FakeToolUseBlock(type="tool_use", id="call_1", name="calculator", input={"expression": "1+1"})
    client, recorder = _make_client([_FakeResponse(content=[tool_call])] * 2, max_tool_turns=2), _Recorder()

    asyncio.run(client.run("Keep going", recorder))

    assert [kind for kind, _, _ in recorder.calls] == ["model_call", "tool_call", "model_call", "tool_call"]
