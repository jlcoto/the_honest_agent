"""Decision models as llm_judge graders (TypeSafe's Jev, OpenAI's Decisions API, Google's
Gemini Decisions): naming, the request each adapter sends, reading their answers back from
each SDK's own response objects, pass/fail at min_score, per-method grading models in a
run, and the config and CLI checks around them. No call leaves the machine."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import openai.types
import pytest
import typesafe_sdk
from click.testing import CliRunner
from recorded import claude_reply, definition, model_call, text

from honest_agent.agent_runner import to_jsonable
from honest_agent.cli import main
from honest_agent.config_file import ConfigError, load_config
from honest_agent.grading import DECISION_QUESTION, NOT_GRADED, decision_grade, judge_state
from honest_agent.llm import (
    GOOGLE,
    OPENAI_DECISIONS,
    TYPESAFE,
    GeminiDecisionJudge,
    OpenAIDecisionJudge,
    TypeSafeDecisionJudge,
    api_key_name,
    api_key_set,
    decision_answer,
    is_alias,
    is_decision_model,
    provider_for,
    response_tokens,
    served_model,
)
from honest_agent.notify import alert_message
from honest_agent.raw import RunRecorder, read_records
from honest_agent.runner import eval_loop, failure_summary, saved_prices
from honest_agent.storage import connect
from honest_agent.thresholds import failing_rows

# Each SDK's own response, serialized the way the run records it (to_jsonable).
TYPESAFE_RESPONSE = to_jsonable(
    typesafe_sdk.SystemOneResponse.model_validate(
        {
            "model": "jev-1.14.0",
            "usage": {"input_tokens": 120, "output_tokens": 0},
            "answers": {"correct": {"type": "noul", "noul": 0.85}},
        }
    )
)
OPENAI_RESPONSE = to_jsonable(
    openai.types.Decision.model_validate(
        {
            "model": "gpt-6-luna",
            "usage": {
                "input_tokens": 130,
                "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
                "output_tokens": 0,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 130,
            },
            "answers": [{"type": "predicate", "name": "correct", "probability": 0.32}],
        }
    )
)
# Google's SDK needs Python 3.11, so it isn't installed on 3.10: its response is then the
# JSON as recorded.
_GOOGLE_JSON = {
    "answers": {"correct": {"type": "noul", "noul": 0.99, "confidence": 0.9}},
    "usage": {"total_input_tokens": 140, "total_output_tokens": 0},
}
try:
    from google.genai._gaos.types.decisions import CreateDecisionResponse
except ImportError:
    CreateDecisionResponse = None
GOOGLE_RESPONSE = (
    to_jsonable(CreateDecisionResponse.model_validate(_GOOGLE_JSON)) if CreateDecisionResponse else _GOOGLE_JSON
)


@pytest.mark.parametrize(
    ("model", "provider"),
    [
        ("jev-1.14.0", TYPESAFE),
        ("jev-latest", TYPESAFE),
        ("gemini-decision-1", GOOGLE),
        ("decision:gpt-6-luna", OPENAI_DECISIONS),
        ("gpt-6-luna", "openai"),  # plain gpt-6-luna stays the chat model
        ("claude-sonnet-5-5", "anthropic"),
    ],
)
def test_the_name_says_which_api_a_model_is_called_through(model, provider):
    assert provider_for(model) == provider
    assert is_decision_model(model) == (provider in (TYPESAFE, GOOGLE, OPENAI_DECISIONS))


def test_only_typesafes_aliases_count_as_aliases():
    assert is_alias("jev-latest") and is_alias("jev-preview")
    assert not is_alias("jev-1.14.0") and not is_alias("gemini-decision-1")


def test_googles_key_can_be_either_variable_its_sdk_reads():
    assert api_key_set(GOOGLE, {"GOOGLE_API_KEY": "k"})
    assert api_key_set(GOOGLE, {"GEMINI_API_KEY": "k"})
    assert not api_key_set(GOOGLE, {})
    assert api_key_name(GOOGLE) == "GEMINI_API_KEY (or GOOGLE_API_KEY)"
    assert api_key_name(TYPESAFE) == "TYPESAFE_API_KEY"


class _Recorder:
    """A stand-in for an SDK method: keeps the keyword arguments it was called with."""

    def __init__(self, response):
        self.calls: list[dict] = []
        self._response = response

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _Namespace:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)


def test_each_adapter_asks_one_yes_no_question_about_the_state():
    typesafe = _Recorder(TYPESAFE_RESPONSE)
    openai_create = _Recorder(OPENAI_RESPONSE)
    gemini_create = _Recorder(GOOGLE_RESPONSE)

    asyncio.run(TypeSafeDecisionJudge(_Namespace(system_one=typesafe)).decide("STATE", "Q?", "jev-1.14.0"))
    asyncio.run(
        OpenAIDecisionJudge(_Namespace(decisions=_Namespace(create=openai_create))).decide(
            "STATE", "Q?", "decision:gpt-6-luna"
        )
    )
    asyncio.run(
        GeminiDecisionJudge(_Namespace(decisions=_Namespace(create=gemini_create))).decide(
            "STATE", "Q?", "gemini-decision-1"
        )
    )

    assert typesafe.calls == [
        {"state": "STATE", "questions": {"correct": {"type": "noul", "instructions": "Q?"}}, "model": "jev-1.14.0"}
    ]
    # The prefix only says which API to use; OpenAI gets its own model name.
    assert openai_create.calls == [
        {
            "model": "gpt-6-luna",
            "input": "STATE",
            "questions": [{"type": "predicate", "name": "correct", "instructions": "Q?"}],
        }
    ]
    assert gemini_create.calls == [
        {
            "model": "models/gemini-decision-1",
            "input": "STATE",
            "questions": {"correct": {"type": "noul", "instructions": "Q?"}},
        }
    ]


def test_each_providers_answer_tokens_and_model_are_read_from_its_own_response():
    assert decision_answer(TYPESAFE, TYPESAFE_RESPONSE) == (0.85, None)
    assert decision_answer(OPENAI_DECISIONS, OPENAI_RESPONSE) == (0.32, None)
    assert decision_answer(GOOGLE, GOOGLE_RESPONSE) == (0.99, 0.9)
    assert [response_tokens(p, r) for p, r in [(TYPESAFE, TYPESAFE_RESPONSE), (GOOGLE, GOOGLE_RESPONSE)]] == [
        (120, 0),
        (140, 0),
    ]
    assert served_model(TYPESAFE, TYPESAFE_RESPONSE) == "jev-1.14.0"
    assert served_model(GOOGLE, GOOGLE_RESPONSE) is None  # Google's response doesn't name it


def test_a_refused_question_has_no_answer():
    refused = {"answers": [{"type": "refusal", "name": "correct"}], "model": "gpt-6-luna", "usage": {}}
    assert decision_answer(OPENAI_DECISIONS, refused) == (None, None)


def test_p_yes_passes_at_min_score_and_is_kept_as_the_confidence():
    assert decision_grade(0.85, 0.8) == (1.0, None, None, 0.85)
    assert decision_grade(0.8, 0.8) == (1.0, None, None, 0.8)
    assert decision_grade(0.32, 0.8) == (0.0, None, None, 0.32)
    grade = decision_grade(None, 0.8)
    assert grade.score == 0.0 and grade.rationale.startswith(NOT_GRADED) and grade.confidence is None


def test_the_decision_state_is_the_llm_judge_prompts_body():
    state = judge_state("Revenue was 1.2M.", "1.2M", "What was revenue?")
    assert "Question: What was revenue?" in state
    assert "Expected answer: 1.2M" in state
    assert "<answer>\nRevenue was 1.2M.\n</answer>" in state


class _ScriptedAgent:
    def __init__(self, answer: str):
        self._answer = answer

    async def run(self, prompt, record):
        kind, provider, request, response = model_call(claude_reply(text(self._answer)))
        await record.call(kind, provider, request, _returns(response))


class _ScriptedLLMJudge:
    async def complete(self, prompt, model, max_tokens, schema, effort=None):
        return claude_reply(text('{"extracted_answer": "4"}'))


class _ScriptedDecisionJudge:
    def __init__(self, response: dict):
        self._response = response
        self.asked: list[tuple] = []

    async def decide(self, state, question, model):
        self.asked.append((state, question, model))
        return self._response


async def _returns(value):
    return value


def _run(path: str, graders: dict[str, str], judges: dict, definitions) -> list[dict]:
    con = connect(path)
    try:
        recorder = RunRecorder(con)
        recorder.start_run(
            "run_1",
            agent_name="demo",
            target="demo",
            model="claude-test",
            judge_model="label",
            settings={
                "max_tool_steps": 5,
                "mcp": {},
                "ignore_tools": [],
                "grading_effort": "low",
                "prices": saved_prices("claude-test", graders, None),
            },
            tools_offered=[],
        )
        return asyncio.run(eval_loop(_ScriptedAgent("4"), definitions, graders, judges, "run_1", recorder, con, "low"))
    finally:
        con.close()


def test_a_run_grades_each_method_with_its_own_model(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    decision = _ScriptedDecisionJudge(TYPESAFE_RESPONSE)
    graders = {"extract_match": "claude-sonnet-5-5", "llm_judge": "jev-1.14.0"}
    evals = [
        definition(eval_id="judged", grading_method="llm_judge"),
        definition(eval_id="extracted", grading_method="extract_match"),
    ]

    judged, extracted = _run(path, graders, {"claude-sonnet-5-5": _ScriptedLLMJudge(), "jev-1.14.0": decision}, evals)

    # The decision model: pass/fail at min_score (0.8), its P(yes) kept, no rationale or effort.
    assert (judged["accuracy_score"], judged["accuracy_confidence"]) == (1.0, 0.85)
    assert judged["accuracy_rationale"] is None
    assert (judged["grading_model"], judged["grading_effort"]) == ("jev-1.14.0", None)
    assert judged["grading_cost_usd"] == pytest.approx(120 * 0.042 / 1_000_000)
    # The LLM that extracts, in the same run, records its own model and effort.
    assert (extracted["accuracy_score"], extracted["accuracy_confidence"]) == (1.0, None)
    assert (extracted["grading_model"], extracted["grading_effort"]) == ("claude-sonnet-5-5", "low")

    ((state, question, model),) = decision.asked
    assert (question, model) == (DECISION_QUESTION, "jev-1.14.0")
    assert "Expected answer: 4" in state
    grading = next(e for e in read_records(path)[0]["events"] if e["kind"] == "grading_call")
    assert grading["provider"] == TYPESAFE
    assert json.loads(grading["request"]) == {"model": "jev-1.14.0", "state": state, "question": DECISION_QUESTION}


def test_a_decision_model_below_min_score_fails_and_says_how_sure_it_was(tmp_path: Path):
    graders = {"extract_match": "claude-sonnet-5-5", "llm_judge": "decision:gpt-6-luna"}
    judges = {"claude-sonnet-5-5": _ScriptedLLMJudge(), "decision:gpt-6-luna": _ScriptedDecisionJudge(OPENAI_RESPONSE)}

    (row,) = _run(str(tmp_path / "results.duckdb"), graders, judges, [definition(grading_method="llm_judge")])

    assert (row["accuracy_score"], row["accuracy_confidence"]) == (0.0, 0.32)
    failures = failing_rows([row])
    assert "q1: accuracy fail, 32% sure it's correct (min 0.8)" in "\n".join(failure_summary([row], failures))
    message = alert_message([row], failures)
    assert any(
        "Accuracy *fail*, 32% sure it's correct (min 0.8)" in b.get("text", {}).get("text", "")
        for b in message["blocks"]
    )


# -- config and CLI --------------------------------------------------------------------------

_KEYS = ("TYPESAFE_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "HONEST_AGENT_GRADING_MODEL")


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    for var in _KEYS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evals").mkdir()
    return tmp_path


def _config(text: str) -> None:
    Path("honest_agent_config.yml").write_text("model: claude-haiku-5-5\n" + text)


def _invoke(*args: str, env: dict | None = None):
    return CliRunner().invoke(main, ["run", "--evals-dir", "evals", "--mcp-command", "python s.py", *args], env=env)


def test_grading_model_can_name_one_model_per_method(project, fake_run):
    _config("grading_model:\n  extract_match: claude-opus-5-5\n  llm_judge: jev-1.14.0\n")

    result = _invoke(env={"TYPESAFE_API_KEY": "k"})

    assert result.exit_code == 0, result.output
    assert fake_run["graders"] == {"extract_match": "claude-opus-5-5", "llm_judge": "jev-1.14.0"}


def test_a_method_left_out_of_the_mapping_gets_the_default_grading_model(project, fake_run):
    _config("grading_model:\n  llm_judge: claude-opus-5-5\n")

    result = _invoke()

    assert result.exit_code == 0, result.output
    assert fake_run["graders"] == {"extract_match": "claude-sonnet-5-5", "llm_judge": "claude-opus-5-5"}


def test_the_flag_sets_both_methods_over_the_files_mapping(project, fake_run):
    _config("grading_model:\n  llm_judge: jev-1.14.0\n")

    result = _invoke("--grading-model", "claude-opus-5-5")

    assert result.exit_code == 0, result.output
    assert fake_run["graders"] == {"extract_match": "claude-opus-5-5", "llm_judge": "claude-opus-5-5"}


@pytest.mark.parametrize("setting", ["grading_model: jev-1.14.0\n", "grading_model:\n  extract_match: jev-1.14.0\n"])
def test_a_decision_model_cant_grade_extract_match(project, fake_run, setting):
    _config(setting)

    result = _invoke(env={"TYPESAFE_API_KEY": "k"})

    assert result.exit_code == 1
    assert "jev-1.14.0 is a decision model: it can't extract a value" in result.output
    assert "llm_judge: jev-1.14.0" in result.output  # the fix, ready to paste
    assert "graders" not in fake_run


def test_a_decision_model_cant_be_the_agent(project, fake_run):
    result = _invoke("--model", "jev-1.14.0")

    assert result.exit_code == 1
    assert "jev-1.14.0 is a decision model" in result.output


def test_a_decision_judge_needs_its_providers_key(project, fake_run):
    _config("grading_model:\n  llm_judge: gemini-decision-1\n")

    result = _invoke()

    assert result.exit_code == 1
    if sys.version_info >= (3, 11):
        assert "GEMINI_API_KEY (or GOOGLE_API_KEY) not set" in result.output
    else:  # Google's SDK isn't installed below 3.11, which run says first
        assert "gemini-decision-1 needs Python 3.11 or later" in result.output


def test_an_alias_as_judge_gets_a_warning_and_the_run_shows_each_grader(project, fake_run):
    _config("grading_model:\n  llm_judge: jev-latest\n")

    result = _invoke(env={"TYPESAFE_API_KEY": "k"})

    assert result.exit_code == 0, result.output
    assert "WARNING: The grading model jev-latest is an alias" in result.output


def test_config_refuses_an_unknown_method_or_a_non_name(tmp_path: Path):
    path = tmp_path / "honest_agent_config.yml"
    path.write_text("grading_model:\n  contains: claude-opus-5-5\n")
    with pytest.raises(ConfigError, match="Unknown setting"):
        load_config(path)
    path.write_text("grading_model:\n  llm_judge: [a, b]\n")
    with pytest.raises(ConfigError, match="must be a model name"):
        load_config(path)
    path.write_text("targets:\n  demo:\n    grading_model: 3\n")
    with pytest.raises(ConfigError, match="must be a model name, or one per method"):
        load_config(path)


def test_env_var_works_inside_the_mapping(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JUDGE", "jev-1.14.0")
    path = tmp_path / "honest_agent_config.yml"
    path.write_text("grading_model:\n  llm_judge: \"{{ env_var('JUDGE') }}\"\n")

    assert load_config(path).shared["grading_model"] == {"llm_judge": "jev-1.14.0"}
