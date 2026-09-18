import asyncio
import json
from dataclasses import dataclass, field

from agent_quiz_cli.agent_runner import ClaudeAgentClient, plain_content


@dataclass
class _FakeSDKBlock:
    """Stands in for an Anthropic SDK content block (a pydantic model with
    `.model_dump()`), without depending on the real `anthropic` package.
    """

    type: str
    text: str

    def model_dump(self, mode: str = "python") -> dict:
        return {"type": self.type, "text": self.text}


def test_plain_content_converts_sdk_blocks_to_plain_dicts():
    blocks = [_FakeSDKBlock(type="text", text="hello")]

    result = plain_content(blocks)

    assert result == [{"type": "text", "text": "hello"}]
    json.dumps(result)  # must not raise


def test_plain_content_leaves_plain_dicts_untouched():
    tool_results = [{"type": "tool_result", "tool_use_id": "abc", "content": "42"}]

    assert plain_content(tool_results) == tool_results


def test_plain_content_handles_mixed_list():
    blocks = [_FakeSDKBlock(type="text", text="hi"), {"type": "tool_result", "content": "ok"}]

    result = plain_content(blocks)

    assert result == [{"type": "text", "text": "hi"}, {"type": "tool_result", "content": "ok"}]


def test_plain_content_passes_through_scalars():
    assert plain_content("just a string") == "just a string"


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


def _make_client(responses: list[_FakeResponse], tool_executors=None) -> ClaudeAgentClient:
    # Bypasses __init__ (which builds a real anthropic.AsyncAnthropic(),
    # requiring a real API key) so this stays a pure unit test of the loop.
    client = ClaudeAgentClient.__new__(ClaudeAgentClient)
    client._client = type("_FakeAnthropicClient", (), {"messages": _FakeMessages(responses)})()
    client._model = "claude-test"
    client._tool_executors = tool_executors or {}
    client._max_tool_turns = 5
    return client


def test_run_appends_final_text_only_turn_to_raw_trace():
    """Regression test for the bug found via a live run: the agent's final,
    text-only turn used to be dropped from raw_trace (the loop broke before
    appending it), even though result.answer was always correct -- so
    agent_logs.agent_trace was silently missing the agent's actual stated
    answer.
    """
    tool_call = _FakeToolUseBlock(type="tool_use", id="call_1", name="calculator", input={"expression": "1+1"})
    final_text = _FakeTextBlock(type="text", text="The answer is 2.")
    client = _make_client(
        [_FakeResponse(content=[tool_call]), _FakeResponse(content=[final_text])],
        tool_executors={"calculator": lambda inp: "2"},
    )

    result = asyncio.run(client.run("What is 1+1?", tools=[]))

    assert result.answer == "The answer is 2."
    assert len(result.raw_trace) == 4  # user, assistant(tool_use), user(tool_result), assistant(text)
    assert result.raw_trace[-1] == {
        "role": "assistant",
        "content": [{"type": "text", "text": "The answer is 2."}],
    }


def test_run_with_no_tool_calls_still_appends_final_turn():
    final_text = _FakeTextBlock(type="text", text="Paris.")
    client = _make_client([_FakeResponse(content=[final_text])])

    result = asyncio.run(client.run("What is the capital of France?"))

    assert result.answer == "Paris."
    assert len(result.raw_trace) == 2  # user, assistant(text)
    assert result.raw_trace[-1]["role"] == "assistant"


def test_run_sums_tokens_across_every_turn():
    """Each turn of the tool-use loop is its own messages.create call, so a
    multi-turn quiz spends tokens more than once -- input/output_tokens on
    the result should be the sum across turns, not just the final turn's.
    """
    tool_call = _FakeToolUseBlock(type="tool_use", id="call_1", name="calculator", input={"expression": "1+1"})
    final_text = _FakeTextBlock(type="text", text="The answer is 2.")
    client = _make_client(
        [
            _FakeResponse(content=[tool_call], usage=_FakeUsage(input_tokens=100, output_tokens=20)),
            _FakeResponse(content=[final_text], usage=_FakeUsage(input_tokens=150, output_tokens=10)),
        ],
        tool_executors={"calculator": lambda inp: "2"},
    )

    result = asyncio.run(client.run("What is 1+1?", tools=[]))

    assert result.input_tokens == 250
    assert result.output_tokens == 30
