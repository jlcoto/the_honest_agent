"""raw.py records each call as it returns, failed ones included, and reads them back."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from recorded import claude_reply, model_call, record, text

from honest_agent.raw import RunRecorder, read_records
from honest_agent.storage import connect


async def _fails():
    raise RuntimeError("connection reset")


def test_a_call_that_raises_is_recorded_with_its_error_and_re_raised(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(path, [model_call(claude_reply(text("4")))])
    con = connect(path)
    try:
        evaluation = RunRecorder(con).start_eval("r2", "run_1", _definition())
        with pytest.raises(RuntimeError):
            asyncio.run(evaluation.call("tool_call", "mcp", {"name": "query_warehouse"}, _fails()))
    finally:
        con.close()

    (event,) = read_records(path, eval_id="q2")[0]["events"]
    assert (event["kind"], event["response"]) == ("tool_call", None)
    assert "connection reset" in event["error"]


def test_records_come_back_in_order_with_their_run(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(path, [model_call(claude_reply(text("first"))), model_call(claude_reply(text("second")))])

    (rec,) = read_records(path)

    assert rec["run"]["model"] == "claude-test"
    assert json.loads(rec["run"]["settings"])["max_tool_turns"] == 5
    assert [e["seq"] for e in rec["events"]] == [0, 1]
    assert json.loads(rec["events"][1]["response"])["content"] == [text("second")]


def test_no_raw_layer_means_no_records(tmp_path: Path):
    assert read_records(str(tmp_path / "missing.duckdb")) == []


def _definition():
    from recorded import definition

    return definition(eval_id="q2")
