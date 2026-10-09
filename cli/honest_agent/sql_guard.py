"""Refuses tool calls whose SQL could change something, before they reach the MCP server.

An agent reads warehouse data, and text in that data can carry instructions ("now run
`delete from orders`"). Read-only credentials are the real protection; this is a second
layer, always on: honest-agent sits between the model and the MCP server, so it sees
each tool call first. A call whose SQL isn't a read is answered with an error result
instead of being sent, and recorded like any failed call (the agent sees the reason, and
`logs` and the result page show it).

A read is `select` (with `with`, `union` and the like), `show`, `describe` or `use`.
Anything else is refused: writes, DDL, `grant`, `copy`, `call`, `execute immediate`,
`explain` (`explain analyze` runs the statement), `select ... into` (it creates a table),
SQL that can't be parsed, and a batch with any of those in it.

Limits: it only sees SQL, found the way provenance finds it (sql_capture.sent_sql). A
tool that changes data through other arguments (`delete_customer(id=5)`) isn't checked.
There's no switch to allow writes: an agent being evaluated shouldn't change the
warehouse, temp tables included.
"""

from __future__ import annotations

from typing import Any

from sqlglot import exp

from .provenance import parse_statements
from .sql_capture import sent_sql

# Inside a query, any of these makes it more than a read (e.g. Postgres's
# `with d as (delete ...) select`, or `select ... into new_table`).
_WRITES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Copy,
    exp.Into,
    exp.Command,
)
# What sqlglot keeps as raw text (exp.Command) but is still only a look around.
_READ_COMMANDS = {"show", "describe", "desc"}


def _not_a_read(statement: exp.Expression) -> str | None:
    """None for a read, else the kind of statement (e.g. "DELETE"), for the message."""
    if isinstance(statement, (exp.Use, exp.Show, exp.Describe)):
        return None
    if isinstance(statement, exp.Command):
        keyword = str(statement.this).lower()
        return None if keyword in _READ_COMMANDS else keyword.upper()
    if isinstance(statement, exp.Query):
        write = statement.find(*_WRITES)
        if write is None:
            return None
        return "SELECT ... INTO" if isinstance(write, exp.Into) else _kind(write)
    return _kind(statement)


def _kind(node: exp.Expression) -> str:
    if isinstance(node, exp.Command):
        return str(node.this).upper()
    return {"truncatetable": "TRUNCATE"}.get(node.key, node.key.upper())


def refusal(sql: str) -> str | None:
    """Why `sql` won't be run, or None when every statement in it only reads."""
    statements = parse_statements(sql)
    if statements is None:
        return "honest-agent didn't run this SQL: it couldn't be parsed, so it can't be checked as read-only."
    for statement in statements:
        kind = _not_a_read(statement)
        if kind is not None:
            return (
                f"honest-agent didn't run this SQL: it contains a {kind} statement, and only reads "
                "(select, show, describe, use) are allowed."
            )
    return None


class ReadOnlySQL:
    """Stands in for the connected MCP client in the agent loops: SQL that only reads goes
    through to the server, anything else comes back as an error result without running."""

    def __init__(self, client: Any, sql_fields: dict[str, str], ignore_tools: list[str]):
        self._client = client
        self._sql_fields = sql_fields
        self._ignore_tools = ignore_tools

    async def call_tool(self, name: str, arguments: dict) -> Any:
        sql = sent_sql(name, arguments, self._sql_fields, self._ignore_tools)
        reason = refusal(sql) if sql else None
        if reason is None:
            return await self._client.call_tool(name, arguments)
        from mcp.types import CallToolResult, TextContent

        return CallToolResult(content=[TextContent(type="text", text=reason)], is_error=True)
