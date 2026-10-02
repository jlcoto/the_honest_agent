from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from honest_agent.grading import grade_accuracy, grade_contains, grade_extract_match, grade_llm_judge
from honest_agent.llm import AnthropicJudge


def test_grade_contains():
    assert grade_contains("The answer is Jupiter.", "Jupiter") == 1.0
    assert grade_contains("The answer is Mars.", "Jupiter") == 0.0


def test_grade_accuracy_dispatches_by_method():
    score, rationale, input_tokens, output_tokens = asyncio.run(
        grade_accuracy("contains", "The answer is 4.", "4", "What is 2+2?")
    )
    assert score == 1.0
    assert rationale is None
    assert input_tokens == 0
    assert output_tokens == 0


def test_grade_accuracy_rejects_unknown_method():
    try:
        asyncio.run(grade_accuracy("exact", "4", "4", "What is 2+2?"))
        raise AssertionError("expected ValueError for removed 'exact' method")
    except ValueError:
        pass


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeUsage:
    input_tokens: int = 42
    output_tokens: int = 7


class _FakeMessages:
    def __init__(self, payload: dict, usage: _FakeUsage | None = None):
        self._payload = payload
        self._usage = usage or _FakeUsage()
        self.last_call: dict = {}

    async def create(self, **kwargs):
        self.last_call = kwargs
        text = json.dumps(self._payload)

        @dataclass
        class _Response:
            content: list
            usage: _FakeUsage

        return _Response(content=[_FakeTextBlock(text=text)], usage=self._usage)


class _FakeAnthropic:
    def __init__(self, payload: dict, usage: _FakeUsage | None = None):
        self.messages = _FakeMessages(payload, usage=usage)


class _FakeClient(AnthropicJudge):
    def __init__(self, extracted_answer: str, usage: _FakeUsage | None = None):
        super().__init__(_FakeAnthropic({"extracted_answer": extracted_answer}, usage=usage))


class _FakeJudgeClient(AnthropicJudge):
    def __init__(self, score: float, rationale: str = "", usage: _FakeUsage | None = None):
        super().__init__(_FakeAnthropic({"score": score, "rationale": rationale}, usage=usage))


def test_grade_extract_match_scores_match_after_normalization():
    client = _FakeClient(extracted_answer="Paris")

    score, rationale, _, _ = asyncio.run(
        grade_extract_match(client, "The capital of France is Paris.", "Paris", "What is the capital of France?")
    )

    assert score == 1.0
    assert "Paris" in rationale


def test_grade_extract_match_scores_mismatch():
    client = _FakeClient(extracted_answer="London")

    score, rationale, _, _ = asyncio.run(
        grade_extract_match(client, "It's London.", "Paris", "What is the capital of France?")
    )

    assert score == 0.0


def test_grade_extract_match_comparison_is_case_and_whitespace_insensitive():
    client = _FakeClient(extracted_answer="  paris ")

    score, _, _, _ = asyncio.run(
        grade_extract_match(client, "paris, obviously", "Paris", "What is the capital of France?")
    )

    assert score == 1.0


def test_grade_extract_match_returns_token_usage():
    client = _FakeClient(extracted_answer="Paris", usage=_FakeUsage(input_tokens=123, output_tokens=45))

    _, _, input_tokens, output_tokens = asyncio.run(
        grade_extract_match(client, "The capital of France is Paris.", "Paris", "What is the capital of France?")
    )

    assert input_tokens == 123
    assert output_tokens == 45


def test_grade_llm_judge_returns_token_usage():
    client = _FakeJudgeClient(score=1.0, rationale="Correct.", usage=_FakeUsage(input_tokens=200, output_tokens=15))

    score, rationale, input_tokens, output_tokens = asyncio.run(
        grade_llm_judge(client, "Paris.", "Paris", "What is the capital of France?")
    )

    assert score == 1.0
    assert rationale == "Correct."
    assert input_tokens == 200
    assert output_tokens == 15


def test_grade_accuracy_dispatches_extract_match_and_forwards_client():
    client = _FakeClient(extracted_answer="4")

    score, rationale, _, _ = asyncio.run(grade_accuracy("extract_match", "It's 4.", "4", "What is 2+2?", judge=client))

    assert score == 1.0


def test_grade_accuracy_extract_match_requires_client():
    try:
        asyncio.run(grade_accuracy("extract_match", "It's 4.", "4", "What is 2+2?"))
        raise AssertionError("expected ValueError when no client is given")
    except ValueError:
        pass


def test_grade_extract_match_within_tolerance_still_scores_full():
    """The case that motivated this: a raw query result (311928357.7805)
    against a rounded expected_answer (311928357.78) -- the agent reported
    the data faithfully, the mismatch is an eval-authoring precision issue,
    not something worth failing over.
    """
    client = _FakeClient(extracted_answer="311928357.7805")

    score, rationale, _, _ = asyncio.run(
        grade_extract_match(client, "It's 311928357.7805", "311928357.78", "What was 1996 revenue?", tolerance=0.01)
    )

    assert score == 1.0
    assert "tolerance=0.01" in rationale


def test_grade_extract_match_outside_tolerance_still_fails():
    client = _FakeClient(extracted_answer="500")

    score, _, _, _ = asyncio.run(grade_extract_match(client, "It's 500", "4", "What is 2+2?", tolerance=0.01))

    assert score == 0.0


def test_grade_extract_match_tolerance_ignored_for_non_numeric_values():
    """Tolerance only kicks in when both sides parse as numbers -- a
    non-numeric mismatch still fails exact comparison rather than silently
    passing because neither side parsed.
    """
    client = _FakeClient(extracted_answer="London")

    score, _, _, _ = asyncio.run(
        grade_extract_match(client, "It's London.", "Paris", "What is the capital of France?", tolerance=0.01)
    )

    assert score == 0.0


def test_grade_extract_match_without_tolerance_requires_exact_match():
    """Default behavior (tolerance=None) is unchanged -- still exact string
    equality, so an unrounded value still fails without opting in.
    """
    client = _FakeClient(extracted_answer="311928357.7805")

    score, _, _, _ = asyncio.run(
        grade_extract_match(client, "It's 311928357.7805", "311928357.78", "What was 1996 revenue?")
    )

    assert score == 0.0


def test_grade_accuracy_forwards_tolerance():
    client = _FakeClient(extracted_answer="4.001")

    score, _, _, _ = asyncio.run(
        grade_accuracy("extract_match", "It's 4.001", "4", "What is 2+2?", judge=client, tolerance=0.01)
    )

    assert score == 1.0


def test_grade_extract_match_within_tolerance_percent_still_scores_full():
    """1% of 1,000,000 is 10,000 -- 1,005,000 is within that."""
    client = _FakeClient(extracted_answer="1005000")

    score, rationale, _, _ = asyncio.run(
        grade_extract_match(client, "It's 1005000", "1000000", "What was revenue?", tolerance_percent=0.01)
    )

    assert score == 1.0
    assert "tolerance_percent=0.01" in rationale


def test_grade_extract_match_outside_tolerance_percent_fails():
    client = _FakeClient(extracted_answer="1200000")

    score, _, _, _ = asyncio.run(
        grade_extract_match(client, "It's 1200000", "1000000", "What was revenue?", tolerance_percent=0.01)
    )

    assert score == 0.0


def test_grade_extract_match_tolerance_percent_scales_with_magnitude():
    """The exact gap absolute tolerance can't cover: the same relative
    tolerance (1%) is a much smaller absolute allowance for a small expected
    value than for a large one -- proving this isn't just a renamed flat
    delta.
    """
    small_client = _FakeClient(extracted_answer="10.5")  # 5% off of 10 -- outside 1%
    score, _, _, _ = asyncio.run(
        grade_extract_match(small_client, "10.5", "10", "Small question?", tolerance_percent=0.01)
    )
    assert score == 0.0

    big_client = _FakeClient(extracted_answer="1009999")  # <1% off of 1,000,000
    score, _, _, _ = asyncio.run(
        grade_extract_match(big_client, "1009999", "1000000", "Big question?", tolerance_percent=0.01)
    )
    assert score == 1.0


def test_grade_extract_match_tolerance_and_tolerance_percent_are_ored():
    """Either tolerance being satisfied is enough -- not both required."""
    # Fails the (tight) absolute tolerance but passes the percent one.
    client = _FakeClient(extracted_answer="1005000")
    score, _, _, _ = asyncio.run(
        grade_extract_match(client, "1005000", "1000000", "What was revenue?", tolerance=1.0, tolerance_percent=0.01)
    )
    assert score == 1.0


def test_grade_accuracy_forwards_tolerance_percent():
    client = _FakeClient(extracted_answer="1005000")

    score, _, _, _ = asyncio.run(
        grade_accuracy("extract_match", "1005000", "1000000", "What was revenue?", judge=client, tolerance_percent=0.01)
    )

    assert score == 1.0
