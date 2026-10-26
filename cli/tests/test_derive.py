"""derive.py builds results, traces and SQL calls from a raw record alone."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from recorded import (
    SETTINGS,
    claude_reply,
    definition,
    grading_call,
    mcp_result,
    model_call,
    record,
    text,
    tool_call,
    tool_use,
)

from honest_agent.derive import CUT_OFF_ANSWER, derive_result
from honest_agent.grading import CUT_OFF_REPLY
from honest_agent.storage import connect

SQL = "select sum(revenue) from agent_quiz_demo.public.lineitem"
CORTEX_SQL = "select * from semantic_view(agent_quiz_demo.public.tpch_semantic_view metrics total_revenue)"


def _derive(path: str, result_id: str = "r1") -> dict:
    con = connect(path)
    try:
        return derive_result(con, result_id).row
    finally:
        con.close()


def test_a_claude_run_derives_its_answer_trace_tokens_and_tools(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(
        path,
        [
            model_call(
                claude_reply(tool_use("t1", "query_warehouse", {"sql": SQL}), input_tokens=100, output_tokens=20)
            ),
            tool_call("t1", "query_warehouse", {"sql": SQL}, mcp_result("311928357.78")),
            model_call(claude_reply(text("It was 311928357.78."), input_tokens=150, output_tokens=10)),
        ],
        eval_definition=definition(expected_answer="311928357.78", expected_sources=["lineitem"]),
    )

    row = _derive(path)

    assert row["agent_answer"] == "It was 311928357.78."
    assert (row["agent_input_tokens"], row["agent_output_tokens"]) == (250, 30)
    assert row["tools_used"] == ["query_warehouse"]
    assert (row["accuracy_score"], row["provenance_score"]) == (1.0, 1.0)
    assert [c["sql"] for c in row["sql_calls"]] == [SQL]
    assert json.loads(row["agent_trace"]) == [
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": [tool_use("t1", "query_warehouse", {"sql": SQL})]},
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "311928357.78", "is_error": False}],
        },
        {"role": "assistant", "content": [text("It was 311928357.78.")]},
    ]
    assert isinstance(row["latency_ms"], int)
    assert (row["steps"], row["max_steps"], row["hit_step_limit"]) == (2, 5, False)
    details = json.loads(row["step_details"])
    assert [(s["input_tokens"], s["output_tokens"], s["stop_reason"]) for s in details["steps"]] == [
        (100, 20, "tool_use"),
        (150, 10, "end_turn"),
    ]
    assert list(details["tool_ms"]) == ["t1"]


def test_each_step_is_priced_at_the_price_the_run_saved_and_adds_up_to_the_agent_cost(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    prices = {"models": {"claude-test": {"input": 1.0, "output": 2.0, "cache_read": 0.1, "cache_write": 1.25}}}
    record(
        path,
        [
            model_call(
                claude_reply(tool_use("t1", "query_warehouse", {"sql": SQL}), input_tokens=100, output_tokens=20)
            ),
            tool_call("t1", "query_warehouse", {"sql": SQL}, mcp_result("4")),
            model_call(claude_reply(text("4"), input_tokens=150, output_tokens=10)),
        ],
        settings={**SETTINGS, "prices": prices},
    )

    row = _derive(path)

    costs = [s["cost_usd"] for s in json.loads(row["step_details"])["steps"]]
    assert costs == [pytest.approx((100 * 1.0 + 20 * 2.0) / 1e6), pytest.approx((150 * 1.0 + 10 * 2.0) / 1e6)]
    assert sum(costs) == pytest.approx(row["agent_cost_usd"])


def test_a_step_has_no_cost_when_the_run_saved_no_price(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(path, [model_call(claude_reply(text("4")))])

    (step,) = json.loads(_derive(path)["step_details"])["steps"]

    assert step["cost_usd"] is None  # unknown, not $0


def test_an_openai_run_is_converted_to_the_same_conversation_format(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "query_warehouse", "arguments": json.dumps({"sql": SQL})},
    }
    record(
        path,
        [
            model_call(
                {
                    "choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [call]}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20},
                },
                provider="openai",
            ),
            tool_call("c1", "query_warehouse", {"sql": SQL}, mcp_result("4")),
            model_call(
                {
                    "choices": [{"finish_reason": "stop", "message": {"content": "4", "tool_calls": None}}],
                    "usage": {"prompt_tokens": 150, "completion_tokens": 3},
                },
                provider="openai",
            ),
        ],
    )

    row = _derive(path)

    assert row["agent_answer"] == "4"
    # OpenAI's finish reasons read the same as Anthropic's stop reasons.
    assert [s["stop_reason"] for s in json.loads(row["step_details"])["steps"]] == ["tool_use", "end_turn"]
    assert (row["agent_input_tokens"], row["agent_output_tokens"]) == (250, 23)
    assert json.loads(row["agent_trace"])[1] == {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": "c1", "name": "query_warehouse", "input": {"sql": SQL}}],
    }


def test_a_last_reply_still_asking_for_tools_means_the_agent_ran_out_of_steps(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(path, [model_call(claude_reply(tool_use("t1", "query_warehouse", {"sql": SQL})))])

    row = _derive(path)

    assert row["agent_answer"].startswith("[honest-agent error] Exceeded max_tool_steps=5")
    assert row["accuracy_score"] == 0.0
    assert (row["steps"], row["max_steps"], row["hit_step_limit"]) == (1, 5, True)


def _cut_off(reply: dict) -> dict:
    return {**reply, "stop_reason": "max_tokens"}


def test_a_reply_cut_off_at_the_token_limit_is_reported_not_graded_as_an_answer(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    cut = (
        "model_call",
        "anthropic",
        {"model": "claude-test", "max_tokens": 8192, "messages": []},
        _cut_off(claude_reply(text("Revenue was 3"))),
    )
    record(path, [cut])

    row = _derive(path)

    assert row["agent_answer"].startswith(CUT_OFF_ANSWER + " (8192 tokens)")
    assert row["hit_step_limit"] is False
    assert row["accuracy_score"] == 0.0


def test_an_openai_reply_cut_off_at_its_length_limit_is_reported_too(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    reply = {"choices": [{"finish_reason": "length", "message": {"content": "Revenue"}}], "usage": {}}
    record(path, [model_call(reply, provider="openai")])

    assert _derive(path)["agent_answer"].startswith(CUT_OFF_ANSWER)


def test_a_grading_reply_cut_off_at_the_token_limit_says_so(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    cut = (
        "grading_call",
        "anthropic",
        {"model": "claude-judge", "max_tokens": 2048, "prompt": "..."},
        _cut_off(claude_reply(text('{"extracted_answ'))),
    )
    record(
        path,
        [model_call(claude_reply(text("It was 2297."))), cut],
        eval_definition=definition(grading_method="extract_match", expected_answer="2297"),
    )

    row = _derive(path)

    assert row["accuracy_score"] == 0.0
    assert row["accuracy_rationale"] == f"{CUT_OFF_REPLY} (2048 tokens)"


def test_a_tool_result_flagged_as_an_error_shows_as_one(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(
        path,
        [
            model_call(claude_reply(tool_use("t1", "query_warehouse", {"sql": SQL}))),
            tool_call("t1", "query_warehouse", {"sql": SQL}, mcp_result("SQL compilation error", is_error=True)),
            model_call(claude_reply(text("I couldn't get it."))),
        ],
        eval_definition=definition(expected_sources=["lineitem"]),
    )

    row = _derive(path)

    result = json.loads(row["agent_trace"])[2]["content"][0]
    assert (result["content"], result["is_error"]) == ("SQL compilation error", True)
    assert row["sql_calls"][0]["is_error"] is True
    assert row["provenance_score"] == 0.0  # a query that errored read nothing


def test_sql_a_tool_generated_counts_only_once_the_agent_runs_it(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    cortex = [
        model_call(claude_reply(tool_use("t1", "query_semantic_view", {"message": "Revenue in 1996?"}))),
        tool_call("t1", "query_semantic_view", {"message": "..."}, mcp_result(json.dumps([{"statement": CORTEX_SQL}]))),
    ]
    expects = definition(expected_sources=["agent_quiz_demo.public.tpch_semantic_view"])
    record(path, [*cortex, model_call(claude_reply(text("4")))], result_id="never_ran", eval_definition=expects)
    record(
        path,
        [
            *cortex,
            model_call(claude_reply(tool_use("t2", "query_warehouse", {"sql": CORTEX_SQL}))),
            tool_call("t2", "query_warehouse", {"sql": CORTEX_SQL}, mcp_result("4")),
            model_call(claude_reply(text("4"))),
        ],
        result_id="ran",
        eval_definition=expects,
    )

    assert _derive(path, "never_ran")["provenance_score"] == 0.0
    assert _derive(path, "ran")["provenance_score"] == 1.0


def test_an_eval_without_expected_sources_has_no_provenance_score(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(path, [model_call(claude_reply(text("4")))])

    row = _derive(path)

    assert (row["provenance_score"], row["provenance_min_score"]) == (None, None)


def test_grading_is_scored_from_the_recorded_reply(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(
        path,
        [
            model_call(claude_reply(text("About 311,928,357.78"))),
            grading_call('{"extracted_answer": "311928357.7805"}'),
        ],
        eval_definition=definition(grading_method="extract_match", expected_answer="311928357.78", tolerance=0.01),
    )

    row = _derive(path)

    assert (row["accuracy_score"], row["extracted_answer"]) == (1.0, "311928357.7805")
    assert row["grading_model"] == "claude-judge"
    assert (row["grading_input_tokens"], row["grading_output_tokens"]) == (10, 5)


def test_the_grading_call_is_kept_for_the_report(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    reply = claude_reply(text('{"extracted_answer": "2297"}'), input_tokens=741, output_tokens=60)
    reply["usage"]["output_tokens_details"] = {"thinking_tokens": 43}
    grading = ("grading_call", "anthropic", {"model": "claude-judge", "max_tokens": 2048, "prompt": "..."}, reply)
    record(
        path,
        [model_call(claude_reply(text("It was 2297."))), grading],
        eval_definition=definition(grading_method="extract_match", expected_answer="2297"),
    )

    details = json.loads(_derive(path)["grading_call"])

    assert details["model"] == "claude-judge"
    assert details["reply"] == '{"extracted_answer": "2297"}'
    assert (details["stop_reason"], details["max_tokens"]) == ("end_turn", 2048)
    assert (details["input_tokens"], details["output_tokens"], details["thinking_tokens"]) == (741, 60, 43)
    assert details["duration_ms"] is not None


def test_contains_keeps_no_grading_call(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(path, [model_call(claude_reply(text("It was 2297.")))], eval_definition=definition(expected_answer="2297"))

    assert _derive(path)["grading_call"] is None


def test_contains_needs_no_grading_model(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(path, [model_call(claude_reply(text("The answer is 4.")))])

    row = _derive(path)

    assert (row["accuracy_score"], row["grading_model"], row["grading_input_tokens"]) == (1.0, None, 0)


def test_rebuild_uses_the_settings_the_run_had(tmp_path: Path):
    """ignore_tools comes from the run's own record, not from today's config."""
    path = str(tmp_path / "results.duckdb")
    record(
        path,
        [
            model_call(claude_reply(tool_use("t1", "search_tables", {"query": "orders"}))),
            tool_call("t1", "search_tables", {"query": "orders"}, mcp_result("orders, lineitem")),
            model_call(claude_reply(text("4"))),
        ],
        settings={"max_tool_steps": 5, "max_tokens": 1024, "mcp": {}, "ignore_tools": ["search_tables"]},
    )

    assert _derive(path)["sql_calls"] == []


def test_an_eval_stopped_by_an_error_has_nothing_to_derive(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(path, [model_call(claude_reply(text("4")))])
    con = connect(path)
    try:
        from honest_agent.raw import EvalRecorder

        stopped = EvalRecorder(con, "r1")
        stopped._seq = 1
        stopped.eval_error(RuntimeError("judge unreachable"))
        with pytest.raises(ValueError, match="stopped with an error"):
            derive_result(con, "r1")
    finally:
        con.close()


def test_rebuild_locates_bare_names_with_the_defaults_the_run_had(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    sql = "select count(*) from orders"
    record(
        path,
        [
            model_call(claude_reply(tool_use("t1", "query_warehouse", {"sql": sql}))),
            tool_call("t1", "query_warehouse", {"sql": sql}, mcp_result("2297")),
            model_call(claude_reply(text("2297"))),
        ],
        eval_definition=definition(
            expected_answer="2297", expected_sources=["orders"], expected_database="warehouse", expected_schema="main"
        ),
        settings={"max_tool_steps": 5, "mcp": {}, "default_database": "warehouse", "default_schema": "main"},
    )

    row = _derive(path)

    assert row["provenance_score"] == 1.0
    assert [tuple(s.values()) for s in row["queried_sources"]] == [("warehouse", "main", "orders")]
