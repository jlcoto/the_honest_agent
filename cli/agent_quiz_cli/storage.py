"""Reads and writes quiz results in a local DuckDB file, with an optional
Parquet export to S3 built on DuckDB's own `httpfs` extension.

Three tables, kept deliberately separate:

- `results`: one row per graded quiz, the cheap-to-scan summary everything
  else (report/notify/thresholds) reads day to day -- whether the agent got
  it right, scores, thresholds, timing.
- `agent_logs`: one row per graded quiz, joined to `results` by `result_id`,
  for people who want to dig into *why* -- the agent's full turn-by-turn
  trace. Nothing reads this by default; it's there to be explored on demand
  (see `read_agent_logs` / `agent-quiz logs`).
- `tool_calls`: one row per tool call that produced something worth
  auditing (a quiz can produce zero, one, or many), normalized so it's
  directly queryable -- "which quizzes touched `fct_orders`", "how many
  calls did run X issue" -- without unnesting a list column or parsing
  `agent_logs.agent_trace`'s JSON. `type` says what kind of call it was
  (currently only `"sql"`; a future `"semantic"` for structured
  semantic-layer calls like `{"metric": "revenue", "grain": "daily"}` that
  never produce a SQL string at all -- see sql_capture.py's module
  docstring). `payload` is JSON for both, so the column doesn't need
  reshaping as new call types show up: `{"sql": "..."}` today,
  `{"metric": ..., "grain": ...}` whenever semantic capture is built.
  Carries `run_id`/`quiz_id` alongside `result_id` (denormalized on purpose,
  same reasoning as `agent_logs`: convenience filtering without a join).

The local .duckdb file is always the live, queryable store -- DuckDB (like
SQLite) allows only one writer process at a time against a given file, so
this is a good fit for `agent-quiz run`'s occasional, sequential writes, but
it is NOT a shared, concurrently-writable store on its own. For "a team
wants to constantly analyze this together", `export_to_s3_parquet()` is the
intended path: it writes a Parquet snapshot to S3 (via DuckDB's own httpfs
extension -- no separate S3 SDK dependency needed), which Snowflake/
BigQuery/Athena/another DuckDB can all read as an external table. Nothing
calls that automatically; it's an explicit, optional step (`agent-quiz
export`). It exports `results` only -- `agent_logs`/`tool_calls` can be
large and are meant for local/ad-hoc exploration, not the shared dashboard.

There's no separate "quiz definitions" table: every result row carries its
own copy of the quiz fields it was graded against (prompt, expected_answer,
thresholds, ...), since there's no live warehouse to join against and the
data volume here is trivial.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# One row per graded quiz result. List-valued fields use DuckDB's native
# LIST type (VARCHAR[]) rather than JSON-encoded strings, since DuckDB's
# Python API accepts/returns Python lists for those columns directly.
_RESULTS_COLUMNS: list[tuple[str, str]] = [
    ("result_id", "VARCHAR"),
    ("run_id", "VARCHAR"),
    ("run_timestamp", "VARCHAR"),
    ("quiz_id", "VARCHAR"),
    ("prompt", "VARCHAR"),
    ("category", "VARCHAR"),
    ("tags", "VARCHAR[]"),
    ("expected_answer", "VARCHAR"),
    ("agent_answer", "VARCHAR"),
    ("tools_used", "VARCHAR[]"),
    ("accuracy_score", "DOUBLE"),
    ("accuracy_method", "VARCHAR"),
    ("accuracy_rationale", "VARCHAR"),
    ("accuracy_min_score", "DOUBLE"),
    ("provenance_score", "DOUBLE"),
    ("expected_sources", "VARCHAR[]"),
    ("expected_database", "VARCHAR"),
    ("expected_schema", "VARCHAR"),
    ("provenance_min_score", "DOUBLE"),
    ("model_name", "VARCHAR"),
    ("agent_backend", "VARCHAR"),  # "claude" (direct API) or "mcp"
    ("latency_ms", "INTEGER"),
    # Two cost centers, kept separate rather than one combined total: the
    # agent's own tool-use loop (one or more `messages.create` calls) vs. the
    # grading call (extract_match/llm_judge; zero for contains, which makes
    # no LLM call) -- conflating them would hide whether a quiz is expensive
    # because the agent is chatty/looping or because grading itself is.
    # Input/output are split too since Anthropic prices them differently.
    ("agent_input_tokens", "INTEGER"),
    ("agent_output_tokens", "INTEGER"),
    ("grading_input_tokens", "INTEGER"),
    ("grading_output_tokens", "INTEGER"),
]
_RESULTS_COLUMN_NAMES = [name for name, _ in _RESULTS_COLUMNS]

# The deep-dive companion row for one `results` row (same result_id).
_AGENT_LOGS_COLUMNS: list[tuple[str, str]] = [
    ("result_id", "VARCHAR"),
    ("run_id", "VARCHAR"),
    ("quiz_id", "VARCHAR"),
    # JSON-encoded copy of the agent's full turn-by-turn trace (text output,
    # tool_use calls, tool_result responses) -- the closest thing to "the
    # agent's reasoning" we can capture without a hidden extended-thinking
    # channel. Query it with DuckDB's json_extract* functions, or hand the
    # raw string to a browser-side json.parse().
    ("agent_trace", "VARCHAR"),
]
_AGENT_LOGS_COLUMN_NAMES = [name for name, _ in _AGENT_LOGS_COLUMNS]

# One row per auditable tool call captured from the trace (see
# sql_capture.py). A single graded quiz can contribute zero, one, or many
# rows here. `payload` is JSON, shaped according to `type` -- e.g.
# {"sql": "..."} for type="sql" -- so new call types (e.g. a future
# type="semantic" for structured semantic-layer args) don't need a schema
# change, just a new payload shape.
_TOOL_CALLS_COLUMNS: list[tuple[str, str]] = [
    ("result_id", "VARCHAR"),
    ("run_id", "VARCHAR"),
    ("quiz_id", "VARCHAR"),
    ("call_index", "INTEGER"),  # 0-based order the calls happened in, within this quiz
    ("tool_name", "VARCHAR"),
    ("type", "VARCHAR"),  # "sql" today; "semantic" once that capture exists
    ("payload", "VARCHAR"),  # JSON, shape depends on `type`
]
_TOOL_CALLS_COLUMN_NAMES = [name for name, _ in _TOOL_CALLS_COLUMNS]


def _connect(results_path: str):
    import duckdb

    Path(results_path).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(results_path)


def _ensure_schema(con) -> None:
    results_cols_sql = ", ".join(f"{name} {type_}" for name, type_ in _RESULTS_COLUMNS)
    con.execute(f"create table if not exists results ({results_cols_sql})")
    # Backfills columns added to _RESULTS_COLUMNS after a results.duckdb file
    # already existed on disk (e.g. the token columns) -- `create table if
    # not exists` only handles a brand-new file, so an existing `results`
    # table needs its own migration path or every insert into it would fail.
    for name, type_ in _RESULTS_COLUMNS:
        con.execute(f"alter table results add column if not exists {name} {type_}")
    logs_cols_sql = ", ".join(f"{name} {type_}" for name, type_ in _AGENT_LOGS_COLUMNS)
    con.execute(f"create table if not exists agent_logs ({logs_cols_sql})")
    tool_calls_cols_sql = ", ".join(f"{name} {type_}" for name, type_ in _TOOL_CALLS_COLUMNS)
    con.execute(f"create table if not exists tool_calls ({tool_calls_cols_sql})")


def _table_exists(con, table_name: str) -> bool:
    row = con.execute("select count(*) from information_schema.tables where table_name = ?", [table_name]).fetchone()
    return bool(row and row[0] > 0)


def write_run_results(results_path: str, run_id: str, rows: list[dict[str, Any]]) -> str:
    """Writes every graded quiz result from one `agent-quiz run` invocation.

    Each row in `rows` is expected to carry the union of `results` and
    `agent_logs` fields (result_id, scores, ..., agent_trace), plus an
    optional `sql_calls` key -- a list of `{"tool_name", "sql"}` dicts (see
    sql_capture.extract_sql_calls) that gets expanded into zero or more
    `tool_calls` rows (each written as `type="sql"`, `payload={"sql": ...}`
    JSON-encoded). The CLI builds one flat dict per quiz; this function is
    the only place that knows how to split/expand it across all three
    tables. Creates the local DuckDB file (and its parent directory) if this
    is the first run. Returns `results_path`, for logging.
    """
    con = _connect(results_path)
    try:
        _ensure_schema(con)
        if rows:
            results_placeholders = ", ".join(["?"] * len(_RESULTS_COLUMN_NAMES))
            con.executemany(
                f"insert into results ({', '.join(_RESULTS_COLUMN_NAMES)}) values ({results_placeholders})",
                [[row.get(name) for name in _RESULTS_COLUMN_NAMES] for row in rows],
            )
            logs_placeholders = ", ".join(["?"] * len(_AGENT_LOGS_COLUMN_NAMES))
            con.executemany(
                f"insert into agent_logs ({', '.join(_AGENT_LOGS_COLUMN_NAMES)}) values ({logs_placeholders})",
                [[row.get(name) for name in _AGENT_LOGS_COLUMN_NAMES] for row in rows],
            )

            tool_call_rows = [
                [
                    row.get("result_id"),
                    row.get("run_id"),
                    row.get("quiz_id"),
                    call_index,
                    call.get("tool_name"),
                    "sql",
                    json.dumps({"sql": call.get("sql")}),
                ]
                for row in rows
                for call_index, call in enumerate(row.get("sql_calls") or [])
            ]
            if tool_call_rows:
                tool_calls_placeholders = ", ".join(["?"] * len(_TOOL_CALLS_COLUMN_NAMES))
                tool_calls_columns = ", ".join(_TOOL_CALLS_COLUMN_NAMES)
                con.executemany(
                    f"insert into tool_calls ({tool_calls_columns}) values ({tool_calls_placeholders})",
                    tool_call_rows,
                )
    finally:
        con.close()
    return results_path


def read_all_results(results_path: str) -> list[dict[str, Any]]:
    """Reads every stored `results` row across every run. Returns [] if
    nothing's been written yet, rather than raising -- a fresh project that
    hasn't run a quiz yet shouldn't error on `report`/`notify`.
    """
    if not Path(results_path).exists():
        return []

    con = _connect(results_path)
    try:
        if not _table_exists(con, "results"):
            return []
        cursor = con.execute("select * from results")
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        con.close()


def read_latest_run_results(results_path: str) -> list[dict[str, Any]]:
    """Reads only the most recent run's `results` rows (by max run_timestamp)."""
    all_rows = read_all_results(results_path)
    if not all_rows:
        return []
    latest_run_id = max(all_rows, key=lambda r: r["run_timestamp"])["run_id"]
    return [r for r in all_rows if r["run_id"] == latest_run_id]


def read_agent_logs(results_path: str, run_id: str | None = None, quiz_id: str | None = None) -> list[dict[str, Any]]:
    """Reads `agent_logs` rows (trace + extracted SQL) for exploration --
    optionally filtered to one run and/or one quiz. Returns [] if nothing's
    been written yet.
    """
    if not Path(results_path).exists():
        return []

    con = _connect(results_path)
    try:
        if not _table_exists(con, "agent_logs"):
            return []
        clauses, params = [], []
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if quiz_id is not None:
            clauses.append("quiz_id = ?")
            params.append(quiz_id)
        where_sql = f" where {' and '.join(clauses)}" if clauses else ""
        cursor = con.execute(f"select * from agent_logs{where_sql}", params)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        con.close()


def read_tool_calls(
    results_path: str,
    run_id: str | None = None,
    quiz_id: str | None = None,
    result_id: str | None = None,
) -> list[dict[str, Any]]:
    """Reads `tool_calls` rows, optionally filtered by run/quiz/result,
    ordered so each quiz's calls come back in the order they happened.
    Returns [] if nothing's been written yet.
    """
    if not Path(results_path).exists():
        return []

    con = _connect(results_path)
    try:
        if not _table_exists(con, "tool_calls"):
            return []
        clauses, params = [], []
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if quiz_id is not None:
            clauses.append("quiz_id = ?")
            params.append(quiz_id)
        if result_id is not None:
            clauses.append("result_id = ?")
            params.append(result_id)
        where_sql = f" where {' and '.join(clauses)}" if clauses else ""
        cursor = con.execute(f"select * from tool_calls{where_sql} order by result_id, call_index", params)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        con.close()


def export_to_s3_parquet(results_path: str, s3_path: str, run_id: str | None = None) -> str:
    """Exports stored `results` (not `agent_logs`) to a Parquet file in S3,
    via DuckDB's `httpfs` extension (installed/loaded at call time -- no
    separate S3 SDK needed).

    Exports every stored run by default; pass `run_id` to export just one.
    Relies entirely on DuckDB's own S3 credential resolution (the standard
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN /
    AWS_REGION env vars, a shared ~/.aws/credentials profile, or any other
    source DuckDB's credential_chain provider picks up) -- this module does
    no credential handling of its own.

    Returns `s3_path`, for logging.
    """
    if not Path(results_path).exists():
        raise FileNotFoundError(f"No results database at {results_path} -- run `agent-quiz run` first.")

    con = _connect(results_path)
    try:
        if not _table_exists(con, "results"):
            raise RuntimeError(f"{results_path} has no results yet -- run `agent-quiz run` first.")

        con.execute("install httpfs")
        con.execute("load httpfs")

        # run_id is always a CLI-generated uuid.uuid4() string (see cli.py), never
        # free-form user input, but it's escaped defensively regardless since
        # DuckDB's COPY target/source SQL is built as text, not bound parameters.
        s3_path_escaped = s3_path.replace("'", "''")
        if run_id is not None:
            run_id_escaped = run_id.replace("'", "''")
            select_sql = f"select * from results where run_id = '{run_id_escaped}'"
        else:
            select_sql = "select * from results"
        con.execute(f"copy ({select_sql}) to '{s3_path_escaped}' (format parquet)")
    finally:
        con.close()
    return s3_path
