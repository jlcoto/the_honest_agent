"""honest_agent_config.yml: targets, and the precedence flag > env var > file > default.
`_run_async` is replaced by a stub that records what `run` resolved, so nothing connects
to an MCP server or a model."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

import honest_agent.cli as cli_mod
from honest_agent.cli import main
from honest_agent.config_file import ConfigError, find_config_file, load_config

PROJECT_YML = """
results_path: ./out/results.duckdb
model: claude-haiku-4-5
default_target: demo
targets:
  demo:
    mcp_command: python mcp_server/server.py
    evals_dir: evals
  local_md:
    mcp_command: uvx mcp-server-motherduck
    mcp_env: [MOTHERDUCK_TOKEN]
  motherduck:
    mcp_url: https://api.motherduck.com/mcp
    bearer_token_env: MOTHERDUCK_TOKEN
    evals_dir: evals_motherduck
    max_tool_turns: 10
    ignore_tools: [list_shares]
"""

_ENV_VARS = [
    "MCP_COMMAND",
    "MCP_URL",
    "MCP_BEARER_TOKEN",
    "MOTHERDUCK_TOKEN",
    "HONEST_AGENT_MODEL",
    "HONEST_AGENT_JUDGE_MODEL",
    "HONEST_AGENT_AGENT_NAME",
    "HONEST_AGENT_CONFIG_FILE",
]


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "honest_agent_config.yml").write_text(PROJECT_YML)
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals_motherduck").mkdir()
    return tmp_path


def _run(fake_run, *args: str, env: dict[str, str] | None = None):
    result = CliRunner().invoke(main, ["run", *args], env=env or {})
    return result, fake_run


def test_the_default_target_runs_without_any_flags(project, monkeypatch, fake_run):
    result, run = _run(fake_run)

    assert result.exit_code == 0, result.output
    assert run["mcp_command"] == "python mcp_server/server.py"
    assert run["evals_dir"] == project / "evals"
    assert run["results_path"] == str(project / "out" / "results.duckdb")
    assert run["model"] == "claude-haiku-4-5"
    assert run["max_tool_turns"] == 5
    assert run["agent_name"] == "demo"


def test_a_named_target_brings_its_own_settings(project, monkeypatch, fake_run):
    monkeypatch.setenv("MOTHERDUCK_TOKEN", "md-token")

    result, run = _run(fake_run, "--target", "motherduck")

    assert result.exit_code == 0, result.output
    assert (run["mcp_command"], run["mcp_url"]) == (None, "https://api.motherduck.com/mcp")
    assert run["mcp_bearer_token"] == "md-token"
    assert run["evals_dir"] == project / "evals_motherduck"
    assert run["max_tool_turns"] == 10
    assert run["ignore_tools"] == ["list_shares"]
    assert run["agent_name"] == "motherduck"


def test_a_flag_beats_the_file(project, monkeypatch, fake_run):
    result, run = _run(fake_run, "--max-tool-turns", "3", "--agent-name", "mine", "--mcp-url", "https://x/mcp")

    assert result.exit_code == 0, result.output
    assert (run["max_tool_turns"], run["agent_name"]) == (3, "mine")
    assert (run["mcp_command"], run["mcp_url"]) == (None, "https://x/mcp")


def test_an_env_var_beats_the_file_with_a_note(project, monkeypatch, fake_run):
    result, run = _run(fake_run, env={"HONEST_AGENT_MODEL": "gpt-5.4-mini", "OPENAI_API_KEY": "test"})

    assert result.exit_code == 0, result.output
    assert run["model"] == "gpt-5.4-mini"
    assert "Note: HONEST_AGENT_MODEL from the environment overrides target 'demo'" in result.output


def test_a_leftover_mcp_url_overrides_the_target_with_a_note(project, monkeypatch, fake_run):
    result, run = _run(fake_run, "--target", "motherduck", env={"MCP_URL": "https://snowflake/mcp"})

    assert result.exit_code == 0, result.output
    assert run["mcp_url"] == "https://snowflake/mcp"
    assert "Note: MCP_URL from the environment overrides target 'motherduck'" in result.output


def test_mcp_bearer_token_is_never_sent_to_a_target_server(project, monkeypatch, fake_run):
    monkeypatch.setenv("MOTHERDUCK_TOKEN", "md-token")

    result, run = _run(fake_run, "--target", "motherduck", env={"MCP_BEARER_TOKEN": "snowflake-token"})

    assert result.exit_code == 0, result.output
    assert run["mcp_bearer_token"] == "md-token"


def test_a_missing_bearer_token_variable_is_named(project, monkeypatch, fake_run):
    result, _ = _run(fake_run, "--target", "motherduck")

    assert result.exit_code != 0
    assert "MOTHERDUCK_TOKEN is not set" in result.output


def test_an_unknown_target_lists_the_real_ones(project, monkeypatch, fake_run):
    result, _ = _run(fake_run, "--target", "snowflak")

    assert result.exit_code != 0
    assert "No target 'snowflak' in honest_agent_config.yml. Targets: demo, local_md, motherduck." in result.output


def test_target_without_a_config_file_is_an_error(tmp_path, monkeypatch, fake_run):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HONEST_AGENT_CONFIG_FILE", raising=False)

    result, _ = _run(fake_run, "--target", "demo", env={"ANTHROPIC_API_KEY": "test"})

    assert result.exit_code != 0
    assert "--target demo needs a honest_agent_config.yml" in result.output


def test_the_file_is_found_from_a_subfolder_and_its_paths_stay_relative_to_it(project, monkeypatch, fake_run):
    (project / "sub").mkdir()
    monkeypatch.chdir(project / "sub")

    result, run = _run(fake_run)

    assert result.exit_code == 0, result.output
    assert run["evals_dir"] == project / "evals"
    assert run["mcp_cwd"] == str(project)
    assert find_config_file(project / "sub") == project / "honest_agent_config.yml"


def test_other_commands_read_results_path_from_the_file(project, monkeypatch, fake_run):
    read_from = []
    monkeypatch.setattr(cli_mod, "read_agent_logs", lambda path, **_: read_from.append(path) or [])

    result = CliRunner().invoke(main, ["logs"])

    assert result.exit_code == 0, result.output
    assert read_from == [str(project / "out" / "results.duckdb")]


def test_typos_and_conflicting_servers_are_errors(tmp_path):
    path = tmp_path / "honest_agent_config.yml"

    path.write_text("targets:\n  demo:\n    mcp_comand: python server.py\n")
    with pytest.raises(ConfigError, match="Unknown setting.*mcp_comand"):
        load_config(path)

    path.write_text("targets:\n  demo:\n    mcp_command: python server.py\n    mcp_url: https://x/mcp\n")
    with pytest.raises(ConfigError, match="either mcp_command or mcp_url"):
        load_config(path)


def test_several_targets_need_a_default_or_a_flag(tmp_path):
    path = tmp_path / "honest_agent_config.yml"
    path.write_text("targets:\n  a: {mcp_command: x}\n  b: {mcp_command: y}\n")
    config = load_config(path)

    with pytest.raises(ConfigError, match="no default_target"):
        config.target(None)
    assert config.target("b").settings == {"mcp_command": "y"}


def test_a_local_server_gets_the_variables_its_target_lists(project, monkeypatch, fake_run):
    monkeypatch.setenv("MOTHERDUCK_TOKEN", "md-token")

    result, run = _run(fake_run, "--target", "local_md")

    assert result.exit_code == 0, result.output
    assert run["mcp_env"] == ["MOTHERDUCK_TOKEN"]


def test_a_listed_variable_that_is_not_set_is_an_error(project, monkeypatch, fake_run):
    result, _ = _run(fake_run, "--target", "local_md")

    assert result.exit_code != 0
    assert "MOTHERDUCK_TOKEN not set" in result.output


def test_mcp_env_flags_replace_the_targets_list(project, monkeypatch, fake_run):
    monkeypatch.setenv("OTHER_TOKEN", "x")

    result, run = _run(fake_run, "--target", "local_md", "--mcp-env", "OTHER_TOKEN")

    assert result.exit_code == 0, result.output
    assert run["mcp_env"] == ["OTHER_TOKEN"]
