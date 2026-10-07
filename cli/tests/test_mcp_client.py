"""The MCP connection: argument checks, which run before `mcp` is imported, and what a
local server is given."""

from __future__ import annotations

import pytest

from honest_agent.mcp_client import build_mcp_client, describe_connection_error


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

    monkeypatch.setattr(mcp, "Client", lambda params: params)
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
