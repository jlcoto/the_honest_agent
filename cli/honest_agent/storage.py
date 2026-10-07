"""Reads and writes eval results in a local DuckDB file, with an optional
Parquet export to S3 built on DuckDB's own `httpfs` extension.

The file has two layers. The raw layer (`raw.runs`, `raw.evals`, `raw.events`,
see raw.py) records what each run sent and received and is never rewritten.
The three tables below are derived from it by derive.py, so `honest-agent
rebuild` can re-derive them for past runs; runs recorded before the raw layer
existed have derived rows only.

Three derived tables, kept deliberately separate:

- `results`: one row per graded eval, the cheap-to-scan summary everything
  else (report/notify/thresholds) reads day to day -- whether the agent got
  it right, scores, thresholds, timing.
- `traces`: one row per graded eval, joined to `results` by `result_id`: the
  agent's conversation in one format for every provider, as the report shows
  it. The exchange as it actually happened is in the raw layer (`honest-agent
  logs`).
- `tool_calls`: **today, this only ever contains SQL calls** -- despite the
  name, a tool call that doesn't produce a SQL string anywhere (no field
  matching `provenance.sql_fields`/the `sql`/`query`/`statement` heuristic --
  see sql_capture.py) leaves zero rows here, even though it's still recorded
  in `results.tools_used` and the full `traces.agent_trace`. One row per
  *SQL* call that produced something worth auditing (an eval can produce
  zero, one, or many), normalized so it's directly queryable -- "which
  evals touched `fct_orders`", "how many calls did run X issue" -- without
  unnesting a list column or parsing `traces.agent_trace`'s JSON. The
  `type` column exists for a future `"semantic"` call kind (structured
  semantic-layer calls like `{"metric": "revenue", "grain": "daily"}` that
  never produce a SQL string at all -- see sql_capture.py's module
  docstring and TODO.md's "Semantic-layer provenance checking"), but no code
  path writes anything besides `"sql"` yet -- that's deliberately not built
  until a real semantic-layer tool is actually in scope, not an oversight.
  `payload` is JSON for both, so the column doesn't need reshaping once that
  lands: `{"sql": "..."}` today, `{"metric": ..., "grain": ...}` later.
  Carries `run_id`/`eval_id` alongside `result_id` (denormalized on purpose,
  same reasoning as `traces`: convenience filtering without a join).

The local .duckdb file is always the live, queryable store -- DuckDB (like
SQLite) allows only one writer process at a time against a given file, so
this is a good fit for `honest-agent run`'s occasional, sequential writes, but
it is NOT a shared, concurrently-writable store on its own. For "a team
wants to constantly analyze this together", `export_to_s3_parquet()` is the
intended path: it writes a Parquet snapshot to S3 (via DuckDB's own httpfs
extension -- no separate S3 SDK dependency needed), which Snowflake/
BigQuery/Athena/another DuckDB can all read as an external table. Nothing
calls that automatically; it's an explicit, optional step (`honest-agent
export`). It exports `results` only -- `traces`/`tool_calls` and the raw layer can be
large and are meant for local/ad-hoc exploration, not the shared dashboard.

There's no separate "eval definitions" table: every result row carries its
own copy of the eval fields it was graded against (prompt, expected_answer,
thresholds, ...), since there's no live warehouse to join against and the
data volume here is trivial.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# One row per graded eval result. List-valued fields use DuckDB's native
# LIST type (VARCHAR[]) rather than JSON-encoded strings, since DuckDB's
# Python API accepts/returns Python lists for those columns directly.
_RESULTS_COLUMNS: list[tuple[str, str]] = [
    ("result_id", "varchar"),
    ("run_id", "varchar"),
    ("run_timestamp", "varchar"),
    ("eval_id", "varchar"),
    ("eval_title", "varchar"),  # optional `title:` from the eval YAML; NULL when not set
    ("prompt", "varchar"),
    ("category", "varchar"),
    ("tags", "varchar[]"),
    ("expected_answer", "varchar"),
    ("agent_answer", "varchar"),
    ("tools_used", "varchar[]"),
    ("accuracy_score", "double"),
    ("accuracy_method", "varchar"),
    # Model that graded the answer (extract_match/llm_judge); NULL for contains, which uses none.
    ("grading_model", "varchar"),
    ("accuracy_rationale", "varchar"),  # the judge's reason (llm_judge only)
    # The value extract_match pulled from the answer and compared with expected_answer.
    ("extracted_answer", "varchar"),
    # The eval's extract_match tolerances, so a report can show the allowed difference.
    ("accuracy_tolerance", "double"),
    ("accuracy_tolerance_percent", "double"),
    ("accuracy_min_score", "double"),
    ("provenance_score", "double"),
    ("expected_sources", "varchar[]"),
    ("expected_database", "varchar"),
    ("expected_schema", "varchar"),
    ("provenance_min_score", "double"),
    # Every table/view the agent's read statements referenced, with the
    # database/schema each resolved to (NULL where neither the SQL nor a `use`
    # statement said) -- see provenance.queried_sources.
    ("queried_sources", "struct(database varchar, schema varchar, name varchar)[]"),
    ("model_name", "varchar"),
    ("agent_backend", "varchar"),  # always "mcp" today; kept for a possible future backend
    # Which agent was evaluated: `run --agent-name`, else the name the MCP server
    # reports at connect time. NULL for rows written before this column existed.
    ("agent_name", "varchar"),
    ("latency_ms", "integer"),
    # Steps the agent took (one model call each, with the tool calls it asked
    # for), the run's max_tool_steps, and whether it used them all without
    # answering. NULL for rows from before the raw layer that weren't backfilled.
    ("steps", "integer"),
    ("max_steps", "integer"),
    ("hit_step_limit", "boolean"),
    # Two cost centers, kept separate rather than one combined total: the
    # agent's own tool-use loop (one or more `messages.create` calls) vs. the
    # grading call (extract_match/llm_judge; zero for contains, which makes
    # no LLM call) -- conflating them would hide whether an eval is expensive
    # because the agent is chatty/looping or because grading itself is.
    # Input/output are split too since Anthropic prices them differently.
    ("agent_input_tokens", "integer"),
    ("agent_output_tokens", "integer"),
    ("grading_input_tokens", "integer"),
    ("grading_output_tokens", "integer"),
    # When the eval's last recorded call ended (run_timestamp is when it started).
    ("finished_at", "varchar"),
    # When derive.py built this row, and the honest-agent version that did; a
    # `rebuild` updates both. NULL for rows from before the raw layer.
    ("derived_at", "varchar"),
    ("honest_agent_version", "varchar"),
]
_RESULTS_COLUMN_NAMES = [name for name, _ in _RESULTS_COLUMNS]

# The conversation behind one `results` row (same result_id).
_TRACES_COLUMNS: list[tuple[str, str]] = [
    ("result_id", "varchar"),
    ("run_id", "varchar"),
    ("eval_id", "varchar"),
    # JSON: the prompt, each model reply (text, tool_use) and each batch of
    # tool_result blocks, in the shared format derive.conversation builds.
    ("agent_trace", "varchar"),
]
_TRACES_COLUMN_NAMES = [name for name, _ in _TRACES_COLUMNS]

# One row per auditable SQL call captured from the trace (see
# sql_capture.py) -- despite the table name, only `type="sql"` is ever
# written today; a tool call with no SQL-shaped field anywhere contributes
# zero rows here. A single graded eval can contribute zero, one, or many
# rows. `payload` is JSON, shaped according to `type` -- e.g. {"sql": "..."}
# for type="sql" -- so a future type="semantic" for structured
# semantic-layer args (not built yet -- see module docstring) won't need a
# schema change, just a new payload shape.
_TOOL_CALLS_COLUMNS: list[tuple[str, str]] = [
    ("result_id", "varchar"),
    ("run_id", "varchar"),
    ("eval_id", "varchar"),
    ("call_index", "integer"),  # 0-based order the calls happened in, within this eval
    ("tool_name", "varchar"),
    ("type", "varchar"),  # "sql" today; "semantic" once that capture exists
    ("payload", "varchar"),  # JSON, shape depends on `type`
    ("is_error", "boolean"),  # the tool returned an error, e.g. a SQL compilation error
    # The SQL came from the tool's response (written by the tool, e.g. Cortex
    # Analyst, not necessarily run), not from what the agent sent.
    ("generated", "boolean"),
]
_TOOL_CALLS_COLUMN_NAMES = [name for name, _ in _TOOL_CALLS_COLUMNS]


def make_output_dir(path: Path) -> None:
    """Creates a folder for honest-agent's generated files that git ignores by itself
    (like pytest's and ruff's caches), so results and reports stay out of commits
    without the user editing their own .gitignore. Only a folder created here gets
    the marker: an existing one (e.g. `--results-path ./results.duckdb` puts results
    in the project root) is left alone, or `*` would hide the whole project."""
    if path.exists():
        return
    path.mkdir(parents=True)
    (path / ".gitignore").write_text("# Created by honest-agent: keeps these generated files out of git.\n*\n")


def _connect(results_path: str):
    import duckdb

    make_output_dir(Path(results_path).parent)
    return duckdb.connect(results_path)


def connect(results_path: str):
    """An open connection to the results file with both layers' tables in place, for
    `run` and `rebuild`, which keep it open while they write. The caller closes it."""
    from .raw import ensure_raw_schema

    con = _connect(results_path)
    _ensure_schema(con)
    ensure_raw_schema(con)
    return con


def _ensure_schema(con) -> None:
    results_cols_sql = ", ".join(f"{name} {type_}" for name, type_ in _RESULTS_COLUMNS)
    con.execute(f"create table if not exists results ({results_cols_sql})")
    # Backfills columns added to _RESULTS_COLUMNS after a results.duckdb file
    # already existed on disk (e.g. the token columns) -- `create table if
    # not exists` only handles a brand-new file, so an existing `results`
    # table needs its own migration path or every insert into it would fail.
    for name, type_ in _RESULTS_COLUMNS:
        con.execute(f"alter table results add column if not exists {name} {type_}")
    traces_cols_sql = ", ".join(f"{name} {type_}" for name, type_ in _TRACES_COLUMNS)
    con.execute(f"create table if not exists traces ({traces_cols_sql})")
    tool_calls_cols_sql = ", ".join(f"{name} {type_}" for name, type_ in _TOOL_CALLS_COLUMNS)
    con.execute(f"create table if not exists tool_calls ({tool_calls_cols_sql})")
    for name, type_ in _TOOL_CALLS_COLUMNS:
        con.execute(f"alter table tool_calls add column if not exists {name} {type_}")


def _table_exists(con, table_name: str) -> bool:
    row = con.execute("select count(*) from information_schema.tables where table_name = ?", [table_name]).fetchone()
    return bool(row and row[0] > 0)


def write_derived(con, rows: list[dict[str, Any]]) -> None:
    """Writes derived rows (from derive.derive_result), replacing any rows those results
    already have, in one transaction -- so a rebuild never leaves a result half-written.

    Each row carries the union of `results` and `traces` fields (result_id, scores, ...,
    agent_trace), plus `sql_calls` -- a list of `{"tool_name", "sql", "is_error",
    "generated"}` dicts (see sql_capture.extract_sql_calls) that becomes zero or more
    `tool_calls` rows (each `type="sql"`, `payload={"sql": ...}` JSON-encoded).
    """
    if not rows:
        return
    ids = [[row["result_id"]] for row in rows]
    con.execute("begin transaction")
    try:
        for table in ("results", "traces", "tool_calls"):
            con.executemany(f"delete from {table} where result_id = ?", ids)
        results_placeholders = ", ".join(["?"] * len(_RESULTS_COLUMN_NAMES))
        con.executemany(
            f"insert into results ({', '.join(_RESULTS_COLUMN_NAMES)}) values ({results_placeholders})",
            [[row.get(name) for name in _RESULTS_COLUMN_NAMES] for row in rows],
        )
        traces_placeholders = ", ".join(["?"] * len(_TRACES_COLUMN_NAMES))
        con.executemany(
            f"insert into traces ({', '.join(_TRACES_COLUMN_NAMES)}) values ({traces_placeholders})",
            [[row.get(name) for name in _TRACES_COLUMN_NAMES] for row in rows],
        )
        tool_call_rows = [
            [
                row.get("result_id"),
                row.get("run_id"),
                row.get("eval_id"),
                call_index,
                call.get("tool_name"),
                "sql",
                json.dumps({"sql": call.get("sql")}),
                bool(call.get("is_error")),
                bool(call.get("generated")),
            ]
            for row in rows
            for call_index, call in enumerate(row.get("sql_calls") or [])
        ]
        if tool_call_rows:
            tool_calls_placeholders = ", ".join(["?"] * len(_TOOL_CALLS_COLUMN_NAMES))
            con.executemany(
                f"insert into tool_calls ({', '.join(_TOOL_CALLS_COLUMN_NAMES)}) values ({tool_calls_placeholders})",
                tool_call_rows,
            )
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise


def write_run_results(results_path: str, run_id: str, rows: list[dict[str, Any]]) -> str:
    """Writes derived rows to the results file (see `write_derived`), creating it if this
    is the first write. Returns `results_path`, for logging."""
    con = _connect(results_path)
    try:
        _ensure_schema(con)
        write_derived(con, rows)
    finally:
        con.close()
    return results_path


def read_all_results(results_path: str) -> list[dict[str, Any]]:
    """Reads every stored `results` row across every run. Returns [] if
    nothing's been written yet, rather than raising -- a fresh project that
    hasn't run an eval yet shouldn't error on `report`/`notify`.
    """
    if not Path(results_path).exists():
        return []

    con = _connect(results_path)
    try:
        if not _table_exists(con, "results"):
            return []
        cursor = con.execute("select * from results")
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        con.close()


def read_latest_run_results(results_path: str) -> list[dict[str, Any]]:
    """Reads only the most recent run's `results` rows (by max run_timestamp)."""
    all_rows = read_all_results(results_path)
    if not all_rows:
        return []
    latest_run_id = max(all_rows, key=lambda r: r["run_timestamp"])["run_id"]
    return [r for r in all_rows if r["run_id"] == latest_run_id]


def read_traces(results_path: str, run_id: str | None = None, eval_id: str | None = None) -> list[dict[str, Any]]:
    """Reads `traces` rows (the normalized conversation per result), optionally
    filtered to one run and/or one eval. Returns [] if nothing's been written yet.
    """
    if not Path(results_path).exists():
        return []

    con = _connect(results_path)
    try:
        if not _table_exists(con, "traces"):
            return []
        clauses, params = [], []
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if eval_id is not None:
            clauses.append("eval_id = ?")
            params.append(eval_id)
        where_sql = f" where {' and '.join(clauses)}" if clauses else ""
        cursor = con.execute(f"select * from traces{where_sql}", params)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        con.close()


def read_tool_calls(
    results_path: str,
    run_id: str | None = None,
    eval_id: str | None = None,
    result_id: str | None = None,
) -> list[dict[str, Any]]:
    """Reads `tool_calls` rows, optionally filtered by run/eval/result,
    ordered so each eval's calls come back in the order they happened.
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
        if eval_id is not None:
            clauses.append("eval_id = ?")
            params.append(eval_id)
        if result_id is not None:
            clauses.append("result_id = ?")
            params.append(result_id)
        where_sql = f" where {' and '.join(clauses)}" if clauses else ""
        cursor = con.execute(f"select * from tool_calls{where_sql} order by result_id, call_index", params)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        con.close()


def export_to_s3_parquet(results_path: str, s3_path: str, run_id: str | None = None) -> str:
    """Exports stored `results` (not `traces`, `tool_calls` or the raw layer) to a Parquet file in S3,
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
        raise FileNotFoundError(f"No results database at {results_path} -- run `honest-agent run` first.")

    con = _connect(results_path)
    try:
        if not _table_exists(con, "results"):
            raise RuntimeError(f"{results_path} has no results yet -- run `honest-agent run` first.")

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
