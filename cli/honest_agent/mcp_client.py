"""The connection to the MCP server whose tools the agent uses, the same for every
model: a local server started over stdio, or a remote one over HTTP.

Imports of `mcp` are kept inside functions so commands that don't need it
(`report`, `notify`, `export`, `logs`) don't pay its import cost.
"""

from __future__ import annotations

import os
import shlex

# Seconds an MCP request may take before it's stopped (`tool_timeout`).
DEFAULT_TOOL_TIMEOUT = 120


def build_mcp_client(
    command: str | None = None,
    url: str | None = None,
    bearer_token: str | None = None,
    cwd: str | None = None,
    env_names: list[str] | None = None,
    tool_timeout: float = DEFAULT_TOOL_TIMEOUT,
):
    """Builds an (unconnected) mcp.Client.

    Pass exactly one of:
      - `command`: a shell command launching a local MCP server over stdio,
        e.g. "python mcp_server/server.py", started in `cwd` if given. The server
        gets only the MCP SDK's minimal environment (PATH, HOME, ...) plus the
        variables named in `env_names` -- never the rest of .env, so a
        third-party server can't read the model API keys or other secrets.
      - `url`: a remote MCP server's streamable-HTTP endpoint, e.g.
        "https://mcp.internal.example.com/mcp". `bearer_token`, if given, is
        sent as an `Authorization: Bearer <token>` header on every request.

    Every request waits at most `tool_timeout` seconds for its answer; one that takes longer
    raises the SDK's REQUEST_TIMEOUT error and the connection stays open (sql_guard.py turns it
    into an error result the agent sees).

    Connect it with `async with build_mcp_client(...) as client: ...`.
    """
    if command and url:
        raise ValueError("Pass either --mcp-command (stdio) or --mcp-url (HTTP), not both.")
    if not command and not url:
        raise ValueError("MCP backend selected but neither --mcp-command nor --mcp-url was given.")
    if command and not shlex.split(command):
        raise ValueError("--mcp-command was empty.")

    # Validation above doesn't need `mcp` importable; only the actual client
    # construction does, so error messages stay clear even without the extra
    # installed, and this function's validation is unit-testable without it.
    from mcp import Client, StdioServerParameters

    if command:
        parts = shlex.split(command)
        from mcp.client.stdio import get_default_environment

        env = {**get_default_environment(), **{name: os.environ[name] for name in env_names or []}}
        server = StdioServerParameters(command=parts[0], args=parts[1:], env=env, cwd=cwd)
        return Client(server, read_timeout_seconds=tool_timeout)

    import httpx2
    from mcp.client.streamable_http import streamable_http_client

    # The MCP SDK's own timeouts (30s to connect, 300s between reads, for a server holding a
    # stream open), with the read one kept longer than `tool_timeout`: the HTTP client hitting
    # its limit first cancels the call and closes the connection, so every later call fails.
    # httpx2's default (5s) did that to any query slower than 5 seconds.
    timeout = httpx2.Timeout(30, read=max(300, tool_timeout + 30))
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else None
    http_client = httpx2.AsyncClient(headers=headers, timeout=timeout)
    return Client(streamable_http_client(url, http_client=http_client), read_timeout_seconds=tool_timeout)


def describe_connection_error(exc: BaseException) -> str:
    """MCP handshake failures typically arrive wrapped in nested
    (Base)ExceptionGroups (anyio task groups) -- unwrap them so the actual
    reason (e.g. an auth error from the server) is visible instead of just
    "unhandled errors in a TaskGroup". Duck-typed on `.exceptions` rather
    than `isinstance(exc, BaseExceptionGroup)` since that builtin doesn't
    exist before Python 3.11, one version above this package's own floor.
    """
    nested = getattr(exc, "exceptions", None)
    if nested:
        return "; ".join(describe_connection_error(e) for e in nested)
    return str(exc)
