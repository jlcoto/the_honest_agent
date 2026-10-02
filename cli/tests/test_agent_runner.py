import json
from dataclasses import dataclass

from honest_agent.agent_runner import plain_content


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
