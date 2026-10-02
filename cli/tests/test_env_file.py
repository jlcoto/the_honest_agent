"""Where .env is loaded from: the current directory by default, or --env-file /
HONEST_AGENT_ENV_FILE. Each test runs in an empty temp directory, and monkeypatch
restores any variables load_dotenv sets."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

import honest_agent.cli as cli_mod
from honest_agent.cli import main

_VARS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "HONEST_AGENT_MODEL",
    "HONEST_AGENT_JUDGE_MODEL",
    "HONEST_AGENT_ENV_FILE",
]


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    for var in _VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "quizzes").mkdir()
    return tmp_path


def _run(monkeypatch, *args: str):
    captured = {}

    async def fake_run_async(*a):
        captured["model"] = a[2]

    monkeypatch.setattr(cli_mod, "_run_async", fake_run_async)
    result = CliRunner().invoke(main, [*args, "run", "--quizzes-dir", "quizzes", "--mcp-command", "python server.py"])
    return result, captured


def test_dotenv_in_the_current_directory_is_loaded(project, monkeypatch):
    (project / ".env").write_text("OPENAI_API_KEY=from-project\n")

    result, captured = _run(monkeypatch)

    assert result.exit_code == 0, result.output
    assert os.environ["OPENAI_API_KEY"] == "from-project"
    assert captured["model"] == "gpt-5.4-mini"


def test_env_file_option_loads_the_named_file(project, monkeypatch, tmp_path_factory):
    env_file = tmp_path_factory.mktemp("secrets") / ".env.motherduck"
    env_file.write_text("OPENAI_API_KEY=from-env-file\n")

    result, _ = _run(monkeypatch, "--env-file", str(env_file))

    assert result.exit_code == 0, result.output
    assert os.environ["OPENAI_API_KEY"] == "from-env-file"


def test_honest_agent_env_file_variable_works_like_the_option(project, monkeypatch, tmp_path_factory):
    env_file = tmp_path_factory.mktemp("secrets") / "ci.env"
    env_file.write_text("OPENAI_API_KEY=from-variable\n")
    monkeypatch.setenv("HONEST_AGENT_ENV_FILE", str(env_file))

    result, _ = _run(monkeypatch)

    assert result.exit_code == 0, result.output
    assert os.environ["OPENAI_API_KEY"] == "from-variable"


def test_a_missing_env_file_is_an_error(project, monkeypatch):
    result, _ = _run(monkeypatch, "--env-file", "nope.env")

    assert result.exit_code == 2
    assert "does not exist" in result.output


def test_variables_already_set_in_the_shell_win_over_the_file(project, monkeypatch):
    (project / ".env").write_text("OPENAI_API_KEY=from-file\n")
    monkeypatch.setenv("OPENAI_API_KEY", "from-shell")

    result, _ = _run(monkeypatch)

    assert result.exit_code == 0, result.output
    assert os.environ["OPENAI_API_KEY"] == "from-shell"
