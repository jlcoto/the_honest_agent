"""Pulls SQL text out of an agent's tool calls, for the `tool_calls` table
(written there as `type="sql"` rows -- see storage.py).

Tool input schemas aren't something honest-agent controls: a locally-defined
tool's schema is whatever the eval YAML's author wrote, and an MCP tool's
schema is whatever that MCP server's author wrote -- there's no field name
guaranteed to hold SQL in either case. So extraction is two-tier: an eval can
declare exactly which field to read per tool name (`provenance.sql_fields` in
the eval YAML, loaded into `EvalDefinition.sql_fields`), and any tool call
not covered by that falls back to a best-effort scan for common field names.
Tools whose matching field holds something else (a search term, say) are
skipped: a built-in list (`_NON_SQL_TOOLS`) plus any the config file's target
names in `ignore_tools` (see config_file.py).

Some tools put the SQL on the *response* side instead: e.g. Snowflake's
Cortex Analyst (`CORTEX_ANALYST_MESSAGE`) takes a natural-language `message`
as input -- no SQL there at all -- and returns the SQL it generated inside
its result (as a `statement` field, JSON-encoded into a text block). So every
tool call is checked on both sides: the declared/heuristic field is looked
for in the call's input first, then, if not found there, in its matching
tool_result's content (parsed as JSON if it's a JSON-encoded string). Same
field names, same `sql_fields` override, on either side -- deliberately not
a second config surface, since the one real example of this seen so far
(Cortex Analyst's `statement`) is already covered by the existing heuristic
list, and there's no second real example yet to generalize a dedicated
"which field, on which side" config from. SQL found on the response side is
marked `generated`: the tool wrote it but may not have run it (Cortex Analyst
doesn't), so it's recorded but doesn't count toward provenance.

This only ever produces `type="sql"` rows. A tool that reaches a semantic
layer through fully structured args on *both* sides -- no SQL string
anywhere, request or response (e.g. `{"metric": "revenue", "grain":
"daily"}` in, a plain number back) -- still isn't captured here; that would
need a parallel `type="semantic"` extraction path (its own declared per-tool
config, analogous to `sql_fields`), which doesn't exist yet.

TODO(semantic-layer provenance): build that `type="semantic"` path once a
real semantic-layer tool that never produces a SQL string on either side is
actually in scope. Two separate config surfaces would be needed, both
necessarily declared per-deployment since they describe someone else's tool
contract, not ours -- there's no way to auto-detect either:
  1. Which tool names are semantic-layer calls (so their whole structured
     input/output gets captured as a payload, instead of honest-agent looking
     for a "sql"/"query"/"statement" field that doesn't exist) -- e.g. a
     `provenance.semantic_tools` list in the eval YAML, alongside
     `sql_fields`.
  2. Which field inside that structured input/output actually names the
     model/metric being hit, so `check_provenance`'s source-checking has
     something to compare `expected_sources` against -- this varies by
     vendor (MetricFlow's `metrics`/`group_by` vs. Cube's
     `measures`/`dimensions`), so it can't be hardcoded either.
Not worth building speculatively -- do this once a second real case shows
what's actually common between it and the first, rather than guessing at a
general shape from one example.
"""

from __future__ import annotations

import json
import re
from typing import Any

_HEURISTIC_FIELD_NAMES = ("sql", "query", "statement")

# Tools known to have a field from `_HEURISTIC_FIELD_NAMES` that isn't SQL, so the
# fallback scan would record it as a SQL call. Add a tool here once a real run shows
# it; a project can exclude more per target with `ignore_tools` (config_file.py).
_NON_SQL_TOOLS = frozenset(
    {
        # MotherDuck's hosted MCP server: `query` is a search term, e.g. "orders".
        "search_catalog",
    }
)


def _find_field(data: Any, field: str | None) -> str | None:
    """Looks for `field` (or, if `field` is None, any of
    `_HEURISTIC_FIELD_NAMES`) in `data` -- a dict, or a list of dicts (some
    tools' responses are a JSON array of parts rather than one flat object,
    e.g. Cortex Analyst's `[{"text": ...}, {"statement": ..., ...}]`).
    Returns the first matching non-empty string value, or None.
    """
    candidates = (field,) if field is not None else _HEURISTIC_FIELD_NAMES
    items = data if isinstance(data, list) else [data]
    for item in items:
        if not isinstance(item, dict):
            continue
        for name in candidates:
            value = item.get(name)
            if isinstance(value, str) and value.strip():
                return value
    return None


def _text(content: Any) -> str:
    """A tool result's content as text: a string as is, a list of content blocks joined."""
    if isinstance(content, list):
        return "\n".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in content)
    return content if isinstance(content, str) else json.dumps(content)


_ERROR_PREFIXES = (
    r"MCP error calling tool \S+:\s*",
    r"MCP Server tool error:\s*",
    r"Error calling tool '\S+':\s*",
    r"Agent error \(code \d+\):\s*",
    r"SQL compilation error:\s*",
)


def error_message(text: str) -> str:
    """The readable part of a failed tool call's result: the MCP wrapper's prefixes,
    request ids and a bare "SQL compilation error:" header dropped."""
    quoted = re.search(r'^error:\s*"(.*)"\s*$', text, re.MULTILINE)  # MotherDuck: `error: "..."`
    if quoted:
        return quoted.group(1).replace('\\"', '"')
    lines = []
    for line in text.splitlines():
        line = line.strip()
        for prefix in _ERROR_PREFIXES:
            line = re.sub("^" + prefix, "", line)
        if line and not line.lower().startswith("request-id"):
            lines.append(line)
    return " ".join(lines)


def single_value(text: str) -> tuple[str, str] | None:
    """(column, value) when a query's result is exactly one row and one column, in any
    of the formats the servers seen so far return; None otherwise."""
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict):
        if isinstance(data.get("result_set"), dict):  # Snowflake
            result_set = data["result_set"]
            columns = [c.get("name") for c in result_set.get("resultSetMetaData", {}).get("rowType", [])]
            rows = result_set.get("data") or []
        else:  # MotherDuck's local server
            columns, rows = data.get("columns") or [], data.get("rows") or []
        if len(columns) == 1 and len(rows) == 1 and isinstance(rows[0], list) and len(rows[0]) == 1:
            return str(columns[0]), str(rows[0][0])
        return None
    # MotherDuck's hosted server: `columns[1]: name` ... `rows[1]:` then `- [1]: value`.
    toon = re.search(
        r"^columns\[1\]:[ \t]*([^\n]+)$.*^rows\[1\]:[ \t]*\n[ \t]*- \[1\]:[ \t]*([^\n]+)$",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if toon:
        return toon.group(1).strip(), toon.group(2).strip().strip('"')
    # A header line and a value line, as the demo server returns.
    lines = [line.strip() for line in text.strip().splitlines()]
    if len(lines) == 2 and all(line and "," not in line and ":" not in line for line in lines):
        return lines[0], lines[1]
    return None


def extract_sql_calls(
    trace: list[dict[str, Any]],
    sql_fields: dict[str, str] | None = None,
    ignore_tools: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Scans a message trace (as produced by agent_runner.plain_content) for
    tool_use blocks and pulls out SQL calls, in the order they happened.
    Each returned item is `{"tool_name": ..., "sql": ..., "is_error": ...,
    "generated": ..., "step": ..., "error": ..., "result_column": ...,
    "result_value": ...}`. `step` is the 1-based model call that made it.
    `error` is the readable error message when the call failed;
    `result_column`/`result_value` hold the result when it is exactly one row and
    one column (bigger results stay out of the report). `is_error` is True when the tool's result was an error
    (e.g. a SQL compilation error). `generated` is True when the SQL came from
    the tool's response rather than its input: the tool wrote it (e.g. Cortex
    Analyst) but didn't necessarily run it. Provenance counts neither, since
    neither shows the agent read anything.

    For a tool named in `sql_fields`, reads exactly that field -- checked
    first against the call's input, then (if not found there) against its
    matching tool_result's content. For any other tool, the same two-sided
    check runs against `_HEURISTIC_FIELD_NAMES` instead. Silently skips
    calls where nothing matches on either side, or the matched value isn't a
    non-empty string.

    Tools in `_NON_SQL_TOOLS` or `ignore_tools` are skipped, unless `sql_fields`
    names them: declaring a tool's SQL field is more specific than either list.
    """
    sql_fields = sql_fields or {}
    skipped = _NON_SQL_TOOLS.union(ignore_tools or [])

    tool_uses: list[tuple[Any, str, dict, int]] = []
    results_by_id: dict[Any, Any] = {}
    texts_by_id: dict[Any, str] = {}
    errored_ids: set[Any] = set()

    step = 0
    for message in trace:
        if message.get("role") == "assistant":
            step += 1
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "tool_use":
                tool_uses.append((block.get("id"), block.get("name"), block.get("input") or {}, step))
            elif block_type == "tool_result":
                result_content = block.get("content")
                texts_by_id[block.get("tool_use_id")] = _text(result_content)
                if isinstance(result_content, str):
                    try:
                        result_content = json.loads(result_content)
                    except ValueError:
                        pass  # not JSON -- leave as the raw string; _find_field finds nothing in it
                results_by_id[block.get("tool_use_id")] = result_content
                if block.get("is_error"):
                    errored_ids.add(block.get("tool_use_id"))

    calls: list[dict[str, Any]] = []
    for tool_use_id, tool_name, tool_input, step in tool_uses:
        if tool_name in skipped and tool_name not in sql_fields:
            continue
        field = sql_fields.get(tool_name)
        sent = _find_field(tool_input, field)
        value = sent or _find_field(results_by_id.get(tool_use_id), field)
        if value:
            text = texts_by_id.get(tool_use_id, "")
            # A generated statement's response is the SQL itself, not a query result.
            value_ = single_value(text) if sent is not None and tool_use_id not in errored_ids else None
            calls.append(
                {
                    "tool_name": tool_name,
                    "sql": value,
                    "is_error": tool_use_id in errored_ids,
                    "generated": sent is None,
                    "step": step,
                    "error": error_message(text) if tool_use_id in errored_ids else None,
                    "result_column": value_[0] if value_ else None,
                    "result_value": value_[1] if value_ else None,
                }
            )

    return calls
