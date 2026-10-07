"""The raw layer: what a run sent to and received from the models and the MCP
server, recorded as each call returns and never rewritten.

Everything else (`results`, `tool_calls`, `traces`) is derived from these
records by derive.py, so a scoring change can be applied to past runs with
`honest-agent rebuild` instead of a hand-written backfill. Three tables, in a
`raw` schema of the same results file:

- `raw.runs`: one row per run -- who and what was evaluated, the settings it
  ran with, and the MCP server's tool list as returned.
- `raw.evals`: one row per eval in a run -- the eval definition as loaded, so
  a rebuild scores against what the run used, not today's eval files.
- `raw.events`: one row per call made during an eval, in order: model calls,
  MCP tool calls, grading calls, and an `eval_error` row when an exception
  stopped the eval. `response` is the SDK object dumped as-is. A model call's
  `request` leaves out the conversation history earlier events already hold:
  each turn re-sends the whole conversation, so the full request is the
  `messages` of the events before it joined in order.

Bearer tokens travel in HTTP headers and API keys live in the SDK clients, so
neither is ever part of a request recorded here.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Awaitable
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .agent_runner import to_jsonable

_RAW_TABLES = {
    "runs": [
        ("run_id", "varchar"),
        ("started_at", "timestamp"),
        ("agent_name", "varchar"),
        ("target", "varchar"),
        ("model", "varchar"),
        ("judge_model", "varchar"),
        ("honest_agent_version", "varchar"),
        # JSON: max_tool_steps, max_tokens, the MCP server (URL or command, never a token), ignore_tools.
        ("settings", "varchar"),
        # JSON: the MCP server's tool list as returned by list_tools.
        ("tools_offered", "varchar"),
    ],
    "evals": [
        ("result_id", "varchar"),
        ("run_id", "varchar"),
        ("eval_id", "varchar"),
        ("definition", "varchar"),  # JSON: the EvalDefinition as loaded
        ("started_at", "timestamp"),
    ],
    "events": [
        ("event_id", "varchar"),
        ("result_id", "varchar"),
        ("seq", "integer"),  # 0-based order within the eval
        ("kind", "varchar"),  # model_call | tool_call | grading_call | eval_error
        ("provider", "varchar"),  # anthropic | openai | mcp; NULL for eval_error
        ("started_at", "timestamp"),
        ("duration_ms", "integer"),
        ("request", "varchar"),  # JSON as sent (a model call's without the earlier history)
        ("response", "varchar"),  # JSON as received; NULL when the call failed
        ("error", "varchar"),  # the call's exception, or for eval_error the one that stopped the eval
    ],
}


def ensure_raw_schema(con) -> None:
    con.execute("create schema if not exists raw")
    for table, columns in _RAW_TABLES.items():
        cols_sql = ", ".join(f"{name} {type_}" for name, type_ in columns)
        con.execute(f"create table if not exists raw.{table} ({cols_sql})")


def honest_agent_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("honest-agent")
    except PackageNotFoundError:
        return "unknown"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RunRecorder:
    """Records one run as it happens: its row in `raw.runs`, and each eval's row in
    `raw.evals`. `start_eval` hands back an EvalRecorder, which records that eval's calls."""

    def __init__(self, con):
        self._con = con
        ensure_raw_schema(con)

    def start_run(
        self,
        run_id: str,
        *,
        agent_name: str | None,
        target: str | None,
        model: str,
        judge_model: str,
        settings: dict,
        tools_offered: list,
    ) -> None:
        self._con.execute(
            "insert into raw.runs values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                _now(),
                agent_name,
                target,
                model,
                judge_model,
                honest_agent_version(),
                json.dumps(settings),
                json.dumps(to_jsonable(tools_offered)),
            ],
        )

    def start_eval(self, result_id: str, run_id: str, definition) -> EvalRecorder:
        self._con.execute(
            "insert into raw.evals values (?, ?, ?, ?, ?)",
            [result_id, run_id, definition.eval_id, json.dumps(asdict(definition)), _now()],
        )
        return EvalRecorder(self._con, result_id)


class EvalRecorder:
    """Records one eval's calls in `raw.events`, in order. Agent runners and grading go
    through `call`."""

    def __init__(self, con, result_id: str):
        self._con = con
        self.result_id = result_id
        self._seq = 0

    async def call(self, kind: str, provider: str, request: dict, pending: Awaitable[Any]) -> Any:
        """Awaits `pending` (an SDK call) and records it with its request, response and
        timing -- also when it raises, in which case the exception is re-raised."""
        started_at, start = _now(), time.monotonic()
        try:
            response = await pending
        except Exception as exc:
            self._write(kind, provider, started_at, start, request, None, repr(exc))
            raise
        self._write(kind, provider, started_at, start, request, to_jsonable(response), None)
        return response

    def eval_error(self, exc: BaseException) -> None:
        """Records the exception that stopped the eval."""
        self._write("eval_error", None, _now(), time.monotonic(), None, None, repr(exc))

    def _write(self, kind, provider, started_at, start, request, response, error) -> None:
        self._con.execute(
            "insert into raw.events values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                str(uuid.uuid4()),
                self.result_id,
                self._seq,
                kind,
                provider,
                started_at,
                int((time.monotonic() - start) * 1000),
                None if request is None else json.dumps(request),
                None if response is None else json.dumps(response),
                error,
            ],
        )
        self._seq += 1


def has_raw_layer(con) -> bool:
    row = con.execute("select count(*) from information_schema.tables where table_schema = 'raw'").fetchone()
    return bool(row and row[0] > 0)


def read_records(results_path: str, run_id: str | None = None, eval_id: str | None = None) -> list[dict]:
    """The raw records of matching evals, oldest first: each is `{"run", "eval", "events"}`
    with the rows as stored (request/response still JSON strings). [] when the file has
    no raw layer yet, or nothing matches."""
    from pathlib import Path

    import duckdb

    if not Path(results_path).exists():
        return []
    con = duckdb.connect(results_path, read_only=True)
    try:
        if not has_raw_layer(con):
            return []
        clauses, params = [], []
        if run_id is not None:
            clauses.append("e.run_id = ?")
            params.append(run_id)
        if eval_id is not None:
            clauses.append("e.eval_id = ?")
            params.append(eval_id)
        where_sql = f" where {' and '.join(clauses)}" if clauses else ""

        def rows(sql: str, args: list) -> list[dict]:
            cursor = con.execute(sql, args)
            names = [d[0] for d in cursor.description]
            return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

        records = []
        runs: dict[str, dict] = {}
        for evaluation in rows(f"select * from raw.evals e{where_sql} order by e.started_at", params):
            if evaluation["run_id"] not in runs:
                runs[evaluation["run_id"]] = rows("select * from raw.runs where run_id = ?", [evaluation["run_id"]])[0]
            events = rows("select * from raw.events where result_id = ? order by seq", [evaluation["result_id"]])
            records.append({"run": runs[evaluation["run_id"]], "eval": evaluation, "events": events})
        return records
    finally:
        con.close()
