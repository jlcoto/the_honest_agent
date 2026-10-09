"""A minimal demo MCP server, so `honest-agent run` has a real agent to evaluate without a
company MCP endpoint: one `query_warehouse` tool that runs SQL against a DuckDB file.

Demo only, not for real data: it runs any read-only SQL the model sends, with no
authentication and no limits besides a row cap, against the whole file. honest-agent
evaluates your agent through your agent's own MCP server; this one only exists to try
honest-agent end to end.

The server knows nothing about the data: the database file is an argument, and the tool's
description doesn't list tables, so the agent finds them itself, as it would with a real
server. A failed query raises, so the MCP result is flagged as an error (honest-agent then
doesn't count it toward provenance) and the agent still sees the message.

    python -m honest_agent.demo_server warehouse.duckdb      (stdio transport)

It ships inside honest-agent (which already depends on `duckdb` and `mcp`), so honest-agent's
own Python runs it: `honest-agent init --example` and the repo's example_project both do.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

MAX_ROWS = 200  # a naive `select *` on a large table would flood the agent's context

DESCRIPTION = (
    "Run a read-only SQL query (DuckDB dialect) against the database and return the result rows, "
    f"at most {MAX_ROWS}. Explore what's there with `show tables`, `describe <table>` or "
    "information_schema; aggregate in SQL rather than pulling raw rows."
)

server = MCPServer("honest_agent_demo")
database: Path | None = None  # set from the command line below


def run_query(database: Path | None, sql: str) -> str:
    """Runs `sql` read-only against `database` and returns CSV-like rows, capped at MAX_ROWS.
    Any failure raises ToolError, which MCP reports as an error result."""
    if database is None or not database.exists():
        raise ToolError(f"Database file not found: {database}. Start the server with the path to a DuckDB file.")
    try:
        con = duckdb.connect(str(database), read_only=True)
    except duckdb.Error as exc:
        raise ToolError(f"error opening {database}: {exc}") from exc
    try:
        rows = con.execute(sql).fetchall()
        columns = [d[0] for d in con.description]
    except duckdb.Error as exc:
        raise ToolError(f"error running query: {exc}") from exc
    finally:
        con.close()

    truncated = len(rows) > MAX_ROWS
    lines = [",".join(columns)] + [",".join(str(v) for v in row) for row in rows[:MAX_ROWS]]
    if truncated:
        lines.append(f"... truncated to {MAX_ROWS} rows, aggregate in SQL instead of relying on raw rows")
    return "\n".join(lines)


@server.tool(description=DESCRIPTION)
def query_warehouse(sql: str) -> str:
    return run_query(database, sql)


if __name__ == "__main__":
    database = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    server.run()
