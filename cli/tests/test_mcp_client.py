"""The MCP connection: argument checks, which run before `mcp` is imported, what a
local server is given, and how long a tool call may take (against real, slow servers)."""

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from honest_agent.mcp_client import build_mcp_client, describe_connection_error
from honest_agent.sql_guard import ReadOnlySQL


def test_build_mcp_client_rejects_both_command_and_url():
    with pytest.raises(ValueError, match="not both"):
        build_mcp_client(command="python server.py", url="https://example.com/mcp")


def test_build_mcp_client_requires_one_of_command_or_url():
    with pytest.raises(ValueError, match="neither"):
        build_mcp_client()


def test_build_mcp_client_rejects_empty_command():
    with pytest.raises(ValueError, match="empty"):
        build_mcp_client(command="   ")


def test_a_local_server_gets_only_the_variables_it_is_given(monkeypatch):
    import mcp

    monkeypatch.setattr(mcp, "Client", lambda params, **_: params)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("MOTHERDUCK_TOKEN", "md-token")

    params = build_mcp_client(command="uvx mcp-server-motherduck", env_names=["MOTHERDUCK_TOKEN"])

    assert params.env["MOTHERDUCK_TOKEN"] == "md-token"
    assert "ANTHROPIC_API_KEY" not in params.env
    assert "PATH" in params.env


class _Group(Exception):
    """Like anyio's exception groups (and ExceptionGroup, which Python 3.10 lacks): errors under `.exceptions`."""

    def __init__(self, *exceptions):
        super().__init__("unhandled errors in a TaskGroup")
        self.exceptions = exceptions


def test_a_connection_error_names_the_reasons_inside_exception_groups():
    nested = _Group(ValueError("401 Unauthorized"), _Group(OSError("connection refused")))

    assert describe_connection_error(nested) == "401 Unauthorized; connection refused"


# An MCP server whose one tool answers after the seconds it's asked to wait.
_SLOW_SERVER = """
import asyncio, sys
from mcp.server.mcpserver import MCPServer

app = MCPServer("slow")

@app.tool()
async def wait(seconds: float) -> str:
    await asyncio.sleep(seconds)
    return f"waited {seconds}s"

if len(sys.argv) > 1:
    app.run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[1]))
else:
    app.run()
"""


async def _calls(client, tool_timeout: float, waits: list[float]) -> list[tuple[bool, str]]:
    """Each wait as the agent would see it: (is_error, text)."""
    async with client as connected:
        guard = ReadOnlySQL(connected, {}, [], tool_timeout)
        results = [await guard.call_tool("wait", {"seconds": s}) for s in waits]
    return [(r.is_error, r.content[0].text) for r in results]


@pytest.fixture
def slow_server(tmp_path: Path) -> Path:
    script = tmp_path / "slow_server.py"
    script.write_text(_SLOW_SERVER)
    return script


def test_a_call_over_the_timeout_comes_back_as_an_error_and_the_next_one_works(slow_server: Path):
    client = build_mcp_client(command=f"{sys.executable} {slow_server}", tool_timeout=1)

    (late, late_text), (on_time, on_time_text) = asyncio.run(_calls(client, 1, [5, 0]))

    assert late and "took longer than 1s" in late_text
    assert not on_time and on_time_text == "waited 0.0s"


def _listening(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture
def slow_http_server(slow_server: Path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, str(slow_server), str(port)], stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 20
        while not _listening(port):
            assert time.monotonic() < deadline, "the slow HTTP server didn't start"
            time.sleep(0.1)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.terminate()
        server.wait()


def test_a_remote_server_with_a_token_gets_more_than_five_seconds(slow_http_server: str):
    # httpx2's default 5s limit used to cancel a 6s call and close the connection.
    client = build_mcp_client(url=slow_http_server, bearer_token="token", tool_timeout=8)

    results = asyncio.run(_calls(client, 8, [6, 10, 0]))

    assert results[0] == (False, "waited 6.0s")
    assert results[1][0] and "took longer than 8s" in results[1][1]
    assert results[2] == (False, "waited 0.0s")
