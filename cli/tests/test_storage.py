import json
from pathlib import Path

import pytest

from honest_agent.storage import (
    export_to_s3_parquet,
    read_agent_logs,
    read_all_results,
    read_latest_run_results,
    read_tool_calls,
    write_run_results,
)


def _row(**overrides) -> dict:
    row = {
        "result_id": "r1",
        "run_id": "run_1",
        "run_timestamp": "2026-01-01 00:00:00",
        "eval_id": "q1",
        "prompt": "What is 2+2?",
        "category": "math",
        "tags": ["smoke"],
        "expected_answer": "4",
        "agent_answer": "4",
        "tools_used": [],
        "accuracy_score": 1.0,
        "accuracy_method": "contains",
        "accuracy_rationale": None,
        "accuracy_min_score": 0.8,
        "provenance_score": 1.0,
        "expected_sources": [],
        "provenance_min_score": 0.7,
        "model_name": "claude-sonnet-5",
        "agent_backend": "mcp",
        "latency_ms": 120,
        "agent_trace": json.dumps([{"role": "user", "content": "What is 2+2?"}]),
        "sql_calls": [],
    }
    row.update(overrides)
    return row


ROW_1 = _row()
ROW_2 = _row(
    result_id="r2",
    eval_id="q2",
    run_timestamp="2026-01-01 00:00:05",
    agent_answer="wrong",
    accuracy_score=0.0,
    tools_used=["calculator"],
    agent_backend="mcp",
    sql_calls=[
        {"tool_name": "query_warehouse", "sql": "SELECT 1"},
        {"tool_name": "query_warehouse", "sql": "SELECT 2"},
    ],
)
ROW_3_LATER_RUN = _row(
    result_id="r3",
    run_id="run_2",
    run_timestamp="2026-01-02 00:00:00",
)


def test_write_then_read_all_results_roundtrips(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [ROW_1, ROW_2])

    rows = read_all_results(db_path)

    assert len(rows) == 2
    by_id = {r["result_id"]: r for r in rows}
    assert by_id["r1"]["accuracy_score"] == 1.0
    assert by_id["r1"]["tags"] == ["smoke"]
    assert by_id["r2"]["tools_used"] == ["calculator"]
    assert by_id["r2"]["accuracy_rationale"] is None
    assert by_id["r2"]["agent_backend"] == "mcp"
    assert "agent_trace" not in by_id["r1"]  # lives in agent_logs, not results
    assert "sql_calls" not in by_id["r1"]


def test_write_then_read_agent_logs_roundtrips(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [ROW_1, ROW_2])

    logs = read_agent_logs(db_path)

    assert len(logs) == 2
    by_id = {r["result_id"]: r for r in logs}
    assert json.loads(by_id["r1"]["agent_trace"]) == [{"role": "user", "content": "What is 2+2?"}]
    assert "sql_calls" not in by_id["r1"]  # lives in tool_calls, not agent_logs
    assert by_id["r1"]["run_id"] == "run_1"
    assert by_id["r1"]["eval_id"] == "q1"


def test_write_then_read_tool_calls_roundtrips_and_expands_per_call(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [ROW_1, ROW_2])

    calls = read_tool_calls(db_path)

    assert len(calls) == 2  # ROW_1 had no sql_calls, ROW_2 had two
    assert all(c["result_id"] == "r2" for c in calls)
    assert all(c["run_id"] == "run_1" and c["eval_id"] == "q2" for c in calls)
    by_index = {c["call_index"]: c for c in calls}
    assert by_index[0] == {
        "result_id": "r2",
        "run_id": "run_1",
        "eval_id": "q2",
        "call_index": 0,
        "tool_name": "query_warehouse",
        "type": "sql",
        "payload": json.dumps({"sql": "SELECT 1"}),
    }
    assert json.loads(by_index[1]["payload"]) == {"sql": "SELECT 2"}


def test_read_tool_calls_filters_by_result_id(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [ROW_1, ROW_2])

    calls = read_tool_calls(db_path, result_id="r2")

    assert len(calls) == 2
    assert all(c["result_id"] == "r2" for c in calls)
    assert read_tool_calls(db_path, result_id="r1") == []


def test_read_tool_calls_filters_by_run_and_eval_id(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [ROW_1, ROW_2])
    write_run_results(db_path, "run_2", [ROW_3_LATER_RUN])

    assert read_tool_calls(db_path, run_id="run_2") == []  # ROW_3 has no sql_calls
    assert {c["result_id"] for c in read_tool_calls(db_path, eval_id="q2")} == {"r2"}


def test_read_tool_calls_on_missing_path_returns_empty(tmp_path: Path):
    assert read_tool_calls(str(tmp_path / "does_not_exist.duckdb")) == []


def test_read_agent_logs_filters_by_run_id(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [ROW_1, ROW_2])
    write_run_results(db_path, "run_2", [ROW_3_LATER_RUN])

    logs = read_agent_logs(db_path, run_id="run_2")

    assert {r["result_id"] for r in logs} == {"r3"}


def test_read_agent_logs_filters_by_eval_id(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [ROW_1, ROW_2])

    logs = read_agent_logs(db_path, eval_id="q2")

    assert {r["result_id"] for r in logs} == {"r2"}


def test_read_agent_logs_on_missing_path_returns_empty(tmp_path: Path):
    assert read_agent_logs(str(tmp_path / "does_not_exist.duckdb")) == []


def test_read_all_results_concatenates_multiple_runs(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [ROW_1, ROW_2])
    write_run_results(db_path, "run_2", [ROW_3_LATER_RUN])

    rows = read_all_results(db_path)

    assert {r["result_id"] for r in rows} == {"r1", "r2", "r3"}


def test_read_all_results_on_missing_path_returns_empty(tmp_path: Path):
    assert read_all_results(str(tmp_path / "does_not_exist.duckdb")) == []


def test_read_latest_run_results_only_returns_most_recent_run(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [ROW_1, ROW_2])
    write_run_results(db_path, "run_2", [ROW_3_LATER_RUN])

    latest = read_latest_run_results(db_path)

    assert {r["result_id"] for r in latest} == {"r3"}


def test_read_latest_run_results_on_empty_store_returns_empty(tmp_path: Path):
    assert read_latest_run_results(str(tmp_path / "does_not_exist.duckdb")) == []


def test_export_to_parquet_on_missing_db_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        export_to_s3_parquet(str(tmp_path / "does_not_exist.duckdb"), str(tmp_path / "out.parquet"))


def test_export_to_parquet_writes_readable_file(tmp_path: Path):
    """Proxy for a true s3:// round trip, which needs real AWS credentials/a
    bucket this environment doesn't have. `COPY ... TO '<path>' (FORMAT
    PARQUET)` behaves identically for a local path and an s3:// one -- this
    exercises the same query/escaping logic export_to_s3_parquet uses,
    without exercising the httpfs/S3 network path itself.
    """
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [ROW_1, ROW_2])
    write_run_results(db_path, "run_2", [ROW_3_LATER_RUN])
    out_path = tmp_path / "export.parquet"

    export_to_s3_parquet(db_path, str(out_path))

    import duckdb

    rows = duckdb.connect().execute(f"SELECT result_id FROM read_parquet('{out_path}')").fetchall()
    assert {r[0] for r in rows} == {"r1", "r2", "r3"}


def test_export_to_parquet_filters_by_run_id(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [ROW_1, ROW_2])
    write_run_results(db_path, "run_2", [ROW_3_LATER_RUN])
    out_path = tmp_path / "export.parquet"

    export_to_s3_parquet(db_path, str(out_path), run_id="run_2")

    import duckdb

    rows = duckdb.connect().execute(f"SELECT result_id FROM read_parquet('{out_path}')").fetchall()
    assert {r[0] for r in rows} == {"r3"}


def test_agent_name_column_is_added_to_an_existing_results_table(tmp_path: Path):
    import duckdb

    db_path = str(tmp_path / "results.duckdb")
    con = duckdb.connect(db_path)
    con.execute("create table results (result_id varchar, run_id varchar, run_timestamp varchar)")
    con.execute("insert into results values ('old', 'run_0', '2025-12-31 00:00:00')")
    con.close()

    write_run_results(db_path, "run_1", [_row(agent_name="snowflake")])

    by_id = {r["result_id"]: r for r in read_all_results(db_path)}
    assert by_id["old"]["agent_name"] is None
    assert by_id["r1"]["agent_name"] == "snowflake"


def test_grading_model_roundtrips(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [_row(grading_model="claude-haiku-4-5"), _row(result_id="r2")])

    by_id = {r["result_id"]: r for r in read_all_results(db_path)}

    assert by_id["r1"]["grading_model"] == "claude-haiku-4-5"
    assert by_id["r2"]["grading_model"] is None


def test_a_results_folder_honest_agent_creates_ignores_itself_in_git(tmp_path: Path):
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    write_run_results(str(tmp_path / "honest_agent_results" / "results.duckdb"), "run_1", [_row()])

    assert (tmp_path / "honest_agent_results" / ".gitignore").read_text().endswith("*\n")
    status = subprocess.run(["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert status.stdout == ""


def test_an_existing_folder_never_gets_the_ignore_marker(tmp_path: Path):
    write_run_results(str(tmp_path / "results.duckdb"), "run_1", [_row()])

    assert not (tmp_path / ".gitignore").exists()


def test_a_results_file_from_before_the_eval_rename_is_migrated_on_open(tmp_path: Path):
    import duckdb

    db_path = str(tmp_path / "results.duckdb")
    con = duckdb.connect(db_path)
    con.execute("create table results (result_id varchar, quiz_id varchar, quiz_title varchar)")
    con.execute("insert into results values ('r1', 'q_old', 'Old title')")
    con.execute("create table agent_logs (result_id varchar, quiz_id varchar)")
    con.execute("create table tool_calls (result_id varchar, quiz_id varchar)")
    con.close()

    (row,) = read_all_results(db_path)

    assert (row["eval_id"], row["eval_title"]) == ("q_old", "Old title")
    con = duckdb.connect(db_path)
    for table in ("agent_logs", "tool_calls"):
        columns = {r[0] for r in con.execute(f"describe {table}").fetchall()}
        assert "eval_id" in columns and "quiz_id" not in columns
