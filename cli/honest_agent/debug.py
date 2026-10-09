"""The checks behind `honest-agent debug` that touch something outside the project files:
the MCP server and the results store. Neither calls a model, runs a tool or writes
anything. The CLI resolves the settings (as `run` does) and prints one line per check.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import click

from .storage import RESULTS_TOKEN_ENV, is_motherduck, results_exist

MCP_TIMEOUT_SECONDS = 30

OK, FAILED, SKIPPED = "OK", "FAILED", "skipped"


class Report:
    """Prints each check's line as it finishes, so a slow server shows which check it is."""

    def __init__(self):
        self.statuses: list[str] = []

    def ok(self, check: str, detail: str) -> None:
        self._add(check, OK, detail)

    def failed(self, check: str, detail: str) -> None:
        self._add(check, FAILED, detail)

    def skipped(self, check: str, detail: str) -> None:
        self._add(check, SKIPPED, detail)

    def _add(self, check: str, status: str, detail: str) -> None:
        self.statuses.append(status)
        click.echo(f"{check:<15}{status:<9}{detail}")

    def summary(self) -> str:
        failed, skipped = self.statuses.count(FAILED), self.statuses.count(SKIPPED)
        if not failed and not skipped:
            return f"All {len(self.statuses)} checks passed."
        parts = [f"{failed} of {len(self.statuses)} checks failed"] + ([f"{skipped} skipped"] if skipped else [])
        return ", ".join(parts) + "."


def shown(path: str | Path) -> str:
    """`path` relative to the current folder when it's inside it, as the user would type it."""
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


async def mcp_server(
    command: str | None,
    url: str | None,
    bearer_token: str | None,
    cwd: str | None,
    env_names: list[str],
) -> tuple[str, int]:
    """Connects to the MCP server as `run` does and lists its tools, without calling one.
    Returns the name the server reports and its number of tools. Gives up after
    MCP_TIMEOUT_SECONDS, so a server that never answers can't hang `debug`."""
    timeout = MCP_TIMEOUT_SECONDS
    from .mcp_client import build_mcp_client

    async def connect() -> tuple[str, int]:
        client = build_mcp_client(command=command, url=url, bearer_token=bearer_token, cwd=cwd, env_names=env_names)
        async with client as connected:
            tools = (await connected.list_tools()).tools
            return connected.server_info.name, len(tools)

    try:
        return await asyncio.wait_for(connect(), timeout)
    except asyncio.TimeoutError:
        raise RuntimeError(f"No answer from the server within {timeout:g}s.") from None


def motherduck_reason(message: str) -> str:
    """MotherDuck's own words from a failed connection ("Your request is not authenticated.
    ..."), without the DuckDB extension wrapper and request details around them."""
    found = re.search(r"Request failed: (.*?)(?: \(|\"|$)", message)
    return found.group(1) if found else message


def results_store(results_path: str) -> str:
    """Checks that results can be stored at `results_path` without creating or changing
    anything: an existing local file opens read-only, a new one's folder is writable,
    and a MotherDuck database (md:<name>) opens with RESULTS_TOKEN_ENV."""
    if is_motherduck(results_path):
        # Connects and lists the account's databases; creates nothing.
        try:
            exists = results_exist(results_path)
        except Exception as exc:  # duckdb.Error, when MotherDuck refuses the connection
            raise ValueError(f"MotherDuck refused {RESULTS_TOKEN_ENV}: {motherduck_reason(str(exc))}") from exc
        if exists:
            return f"{results_path} (MotherDuck, opened with {RESULTS_TOKEN_ENV})"
        return f"{results_path} (MotherDuck, connected with {RESULTS_TOKEN_ENV}; created on the first run)"

    import duckdb

    path = Path(results_path)
    if path.is_dir():
        raise ValueError(f"{shown(path)} is a folder; results_path must name a DuckDB file.")
    if path.exists():
        duckdb.connect(str(path), read_only=True).close()
        return shown(path)
    folder = path.parent
    while not folder.exists():
        folder = folder.parent
    if not folder.is_dir():
        raise ValueError(f"Can't create {shown(path)}: {shown(folder)} is a file, not a folder.")
    if not os.access(folder, os.W_OK | os.X_OK):
        raise ValueError(f"Can't create {shown(path)}: no write permission in {shown(folder)}.")
    return f"{shown(path)} (created on the first run)"
