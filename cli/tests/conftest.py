from __future__ import annotations

from pathlib import Path

import pytest

import honest_agent.cli as cli_mod


@pytest.fixture
def fake_run(monkeypatch) -> dict:
    """Replaces `run`'s async part (MCP connection, model calls) with a stub. Returns a dict
    that fills with the settings `run` resolved, by name, e.g. fake_run["mcp_url"]."""
    captured: dict = {}

    async def fake_run_async(**settings):
        captured.update(settings)

    monkeypatch.setattr(cli_mod, "run_evals", fake_run_async)
    return captured


@pytest.fixture
def in_tmp_dir(tmp_path: Path, monkeypatch) -> Path:
    """Runs the test from an empty temporary folder."""
    monkeypatch.chdir(tmp_path)
    return tmp_path
