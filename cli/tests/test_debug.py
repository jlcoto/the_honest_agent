"""`honest-agent debug`: one line per check, against the real demo MCP server over stdio.
No model is called and no tool is run."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

import duckdb
import mcp.client.stdio  # noqa: F401 -- binds the server's stderr now, not to CliRunner's stream (no fileno)
import pytest
from click.testing import CliRunner

import honest_agent.debug as debug_mod
from honest_agent.cli import main

DEMO_COMMAND = f"{shlex.quote(sys.executable)} -m honest_agent.demo_server warehouse.duckdb"
# Variables from the shell that would change what `debug` resolves.
CLEAN_ENV = {
    name: None
    for name in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "HONEST_AGENT_MODEL",
        "HONEST_AGENT_JUDGE_MODEL",
        "MCP_COMMAND",
        "MCP_URL",
        "MCP_BEARER_TOKEN",
        "HONEST_AGENT_RESULTS_TOKEN",
    )
}


def _config(target: str) -> None:
    Path("honest_agent_config.yml").write_text(
        f"default_target: demo\nmodel: claude-haiku-4-5\ntargets:\n  demo:\n{target}"
    )


@pytest.fixture
def demo_project(in_tmp_dir) -> Path:
    """A project whose one target is the demo MCP server over a tiny warehouse, with one eval."""
    con = duckdb.connect("warehouse.duckdb")
    con.execute("create table orders as select 1 as id")
    con.close()
    Path("evals").mkdir()
    Path("evals/a.yml").write_text("evals:\n  - id: q1\n    prompt: How many orders?\n    expected_answer: '1'\n")
    _config(f"    mcp_command: {DEMO_COMMAND!r}\n    evals_dir: evals\n")
    return in_tmp_dir


def _debug(*args: str, **env: str | None):
    return CliRunner().invoke(main, ["debug", *args], env={**CLEAN_ENV, "ANTHROPIC_API_KEY": "test", **env})


def _lines(output: str) -> dict[str, str]:
    """Each check's line, by check name."""
    checks = ("Config", "Variables", "Evals", "MCP server", "Results store")
    return {line[:15].strip(): line[15:] for line in output.splitlines() if line[:15].strip() in checks}


def test_debug_passes_against_the_demo_server_and_creates_nothing(demo_project):
    result = _debug()

    assert result.exit_code == 0, result.output
    lines = _lines(result.output)
    assert lines["Config"].split() == ["OK", "honest_agent_config.yml,", "target", "demo"]
    assert lines["Variables"].startswith("OK       ANTHROPIC_API_KEY set; model claude-haiku-4-5")
    assert lines["Evals"] == "OK       1 eval in evals"
    assert lines["MCP server"] == "OK       honest_agent_demo over stdio, 1 tool"
    assert lines["Results store"] == "OK       honest_agent_results/results.duckdb (created on the first run)"
    assert result.output.splitlines()[-1] == "All 5 checks passed."
    assert not Path("honest_agent_results").exists()


def test_debug_opens_existing_results_read_only(demo_project):
    con = duckdb.connect("results.duckdb")
    con.execute("create table results (result_id varchar)")
    con.close()
    before = Path("results.duckdb").read_bytes()

    result = _debug("--results-path", "results.duckdb")

    assert result.exit_code == 0, result.output
    assert _lines(result.output)["Results store"] == "OK       results.duckdb"
    assert Path("results.duckdb").read_bytes() == before


def test_debug_names_a_target_that_isnt_there(demo_project):
    result = _debug("--target", "nope")

    assert result.exit_code == 1
    lines = _lines(result.output)
    assert lines["Config"].startswith("FAILED   No target 'nope' in honest_agent_config.yml. Targets: demo.")
    assert all(lines[check].startswith("skipped") for check in ("Variables", "Evals", "MCP server", "Results store"))
    assert result.output.splitlines()[-1] == "1 of 5 checks failed, 4 skipped."


def test_debug_target_without_a_config_file(in_tmp_dir):
    result = _debug("--target", "demo")

    assert result.exit_code == 1
    assert "--target demo needs a honest_agent_config.yml" in _lines(result.output)["Config"]


def test_debug_names_every_unset_env_var_in_the_config(demo_project):
    _config("    mcp_url: \"{{ env_var('AGENT_URL') }}\"\n    evals_dir: \"{{ env_var('EVALS', 'evals') }}\"\n")
    Path("honest_agent_config.yml").write_text(
        "results_path: \"{{ env_var('RESULTS_DIR') }}/r.duckdb\"\n" + Path("honest_agent_config.yml").read_text()
    )

    result = _debug()

    assert result.exit_code == 1
    lines = _lines(result.output)
    assert "RESULTS_DIR isn't set" in lines["Config"]
    # EVALS has a default, so it needn't be set.
    assert lines["Variables"] == "FAILED   not set: RESULTS_DIR, AGENT_URL (add to .env or export)"


def test_debug_names_an_unset_api_key_and_never_prints_values(demo_project):
    _config(
        f"    mcp_command: {DEMO_COMMAND!r}\n    evals_dir: evals\n    mcp_env: [WAREHOUSE_TOKEN]\n"
        "    default_database: \"{{ env_var('DB_NAME') }}\"\n"
    )

    result = _debug(ANTHROPIC_API_KEY=None, WAREHOUSE_TOKEN="s3cret-token", DB_NAME="hidden-db")

    assert result.exit_code == 1
    assert _lines(result.output)["Variables"] == "FAILED   not set: ANTHROPIC_API_KEY (add to .env or export)"
    assert "s3cret" not in result.output and "hidden-db" not in result.output

    result = _debug(ANTHROPIC_API_KEY="sk-ant-secret", WAREHOUSE_TOKEN="s3cret-token", DB_NAME="hidden-db")

    assert result.exit_code == 0, result.output
    assert _lines(result.output)["Variables"].startswith("OK       DB_NAME, ANTHROPIC_API_KEY, WAREHOUSE_TOKEN set")
    assert not any(value in result.output for value in ("s3cret", "hidden-db", "sk-ant"))


def test_debug_names_an_unset_bearer_token_and_skips_the_server(demo_project):
    _config("    mcp_url: http://127.0.0.1:9/mcp\n    bearer_token_env: AGENT_TOKEN\n    evals_dir: evals\n")

    lines = _lines(_debug().output)

    assert lines["Variables"] == "FAILED   not set: AGENT_TOKEN (add to .env or export)"
    assert lines["MCP server"] == "skipped  needs AGENT_TOKEN"


def test_debug_shows_the_eval_loaders_error(demo_project):
    Path("evals/b.yml").write_text("evals:\n  - prompt: no title\n    expected_answer: x\n")

    result = _debug()

    assert result.exit_code == 1
    assert _lines(result.output)["Evals"] == (
        "FAILED   An eval in b.yml has no title. Each eval needs a title (or an id)."
    )


def test_debug_reports_an_mcp_command_that_fails_to_start(demo_project):
    result = _debug("--mcp-command", "no-such-mcp-server-xyz --stdio")

    assert result.exit_code == 1
    line = _lines(result.output)["MCP server"]
    assert line.startswith("FAILED") and "no-such-mcp-server-xyz" in line


def test_debug_gives_up_on_a_server_that_never_answers(demo_project, monkeypatch):
    monkeypatch.setattr(debug_mod, "MCP_TIMEOUT_SECONDS", 1)
    hang = f"{shlex.quote(sys.executable)} -c 'import time; time.sleep(60)'"

    result = _debug("--mcp-command", hang)

    assert result.exit_code == 1
    assert _lines(result.output)["MCP server"] == "FAILED   No answer from the server within 1s."


def test_debug_needs_the_token_for_motherduck_results(demo_project):
    result = _debug("--results-path", "md:honest_results")

    assert result.exit_code == 1
    assert _lines(result.output)["Results store"].startswith("FAILED   HONEST_AGENT_RESULTS_TOKEN is not set.")


def test_a_refused_motherduck_token_shows_motherducks_reason():
    from honest_agent.debug import motherduck_reason

    raw = (
        'Invalid Input Error: Initialization function "motherduck_duckdb_cpp_init" from file '
        '"/x/motherduck.duckdb_extension" threw an exception: "Invalid Error: Request failed: Your request '
        "is not authenticated. Please check your MotherDuck token. (Jwt is not in the form of "
        "Header.Payload.Signature, request id: 'abc')\""
    )
    assert motherduck_reason(raw) == "Your request is not authenticated. Please check your MotherDuck token."
    assert motherduck_reason("something else") == "something else"
