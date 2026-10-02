"""Covers `honest-agent logs`'s formatting -- pure storage read/print logic,
no LLM or MCP dependency, so it's cheap to drive end to end through the real
`run` command's storage layer instead of mocking anything.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from honest_agent.cli import main
from honest_agent.storage import write_run_results


def _row(**overrides) -> dict:
    row = {
        "result_id": "r1",
        "run_id": "run_1",
        "run_timestamp": "2026-01-01 00:00:00",
        "quiz_id": "q1",
        "prompt": "What is 2+2?",
        "category": "math",
        "tags": ["smoke"],
        "expected_answer": "4",
        "agent_answer": "4",
        "tools_used": [],
        "accuracy_score": 1.0,
        "accuracy_method": "contains",
        "accuracy_rationale": None,
        "accuracy_min_score": 0.8,
        "provenance_score": 1.0,
        "expected_sources": [],
        "provenance_min_score": 0.7,
        "model_name": "claude-test",
        "agent_backend": "mcp",
        "latency_ms": 100,
        "agent_trace": '[{"role": "user", "content": "What is 2+2?"}]',
        "sql_calls": [],
    }
    row.update(overrides)
    return row


def test_logs_prints_answer_and_scores(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [_row()])

    result = CliRunner().invoke(main, ["logs", "--results-path", db_path])

    assert result.exit_code == 0, result.output
    assert "Answer: 4" in result.output
    assert "Accuracy: 1.00 (min 0.80)" in result.output
    assert "Provenance: 1.00 (min 0.70)" in result.output


def test_logs_surfaces_turn_limit_error_message():
    """Regression test for the gap found in review: `logs` used to print only
    the trace and tool calls, so a quiz that hit MCPAgentClient's
    max_tool_turns limit (see mcp_agent_runner.py) had its diagnostic
    `agent_answer` -- already stored in `results` -- invisible here, even
    though this command's whole job is explaining *why* a quiz came out the
    way it did.
    """
    with CliRunner().isolated_filesystem():
        db_path = "results.duckdb"
        write_run_results(
            db_path,
            "run_1",
            [
                _row(
                    agent_answer="[honest-agent error] Exceeded max_tool_turns=5 without a final answer -- "
                    "the agent was still requesting tools on the last turn. See agent_trace for detail.",
                    accuracy_score=0.0,
                )
            ],
        )

        result = CliRunner().invoke(main, ["logs", "--results-path", db_path])

        assert result.exit_code == 0, result.output
        assert "Answer: [honest-agent error] Exceeded max_tool_turns=5" in result.output
        assert "Accuracy: 0.00 (min 0.80)" in result.output


def test_logs_reports_no_matching_logs():
    with CliRunner().isolated_filesystem():
        result = CliRunner().invoke(main, ["logs", "--results-path", "results.duckdb"])

        assert result.exit_code == 0, result.output
        assert "No matching logs found." in result.output


def test_agent_name_defaults_to_the_mcp_server_name():
    from types import SimpleNamespace

    from honest_agent.cli import _resolve_agent_name

    connected = SimpleNamespace(server_info=SimpleNamespace(name="mcp-server-motherduck"))
    assert _resolve_agent_name(None, connected) == "mcp-server-motherduck"
    assert _resolve_agent_name("motherduck", connected) == "motherduck"


def _run_capturing_mcp_target(monkeypatch, args: list[str], env: dict[str, str]):
    import honest_agent.cli as cli_mod

    captured = {}

    async def fake_run_async(*a):
        captured["mcp_command"], captured["mcp_url"] = a[4], a[5]

    monkeypatch.setattr(cli_mod, "_run_async", fake_run_async)
    with CliRunner().isolated_filesystem():
        Path("quizzes").mkdir()
        result = CliRunner().invoke(
            main, ["run", "--quizzes-dir", "quizzes", *args], env={"ANTHROPIC_API_KEY": "test", **env}
        )
    return result, captured


def test_explicit_mcp_command_overrides_mcp_url_from_env(monkeypatch):
    result, target = _run_capturing_mcp_target(
        monkeypatch, ["--mcp-command", "uvx mcp-server-motherduck"], {"MCP_URL": "https://remote/mcp"}
    )

    assert result.exit_code == 0, result.output
    assert target == {"mcp_command": "uvx mcp-server-motherduck", "mcp_url": None}


def test_explicit_mcp_url_overrides_mcp_command_from_env(monkeypatch):
    result, target = _run_capturing_mcp_target(
        monkeypatch, ["--mcp-url", "https://remote/mcp"], {"MCP_COMMAND": "python server.py"}
    )

    assert result.exit_code == 0, result.output
    assert target == {"mcp_command": None, "mcp_url": "https://remote/mcp"}


def test_both_mcp_flags_given_explicitly_is_an_error(monkeypatch):
    result, _ = _run_capturing_mcp_target(
        monkeypatch, ["--mcp-command", "python server.py", "--mcp-url", "https://remote/mcp"], {}
    )

    assert result.exit_code != 0
    assert "not both" in result.output


def test_both_mcp_targets_only_in_env_is_an_error(monkeypatch):
    result, _ = _run_capturing_mcp_target(
        monkeypatch, [], {"MCP_COMMAND": "python server.py", "MCP_URL": "https://remote/mcp"}
    )

    assert result.exit_code != 0
    assert "Pass --mcp-command or --mcp-url to choose one" in result.output


def test_duplicate_quiz_id_is_a_clean_cli_error():
    with CliRunner().isolated_filesystem():
        Path("quizzes").mkdir()
        Path("quizzes/a.yml").write_text("quizzes:\n  - id: q_dup\n    prompt: one\n  - id: q_dup\n    prompt: two\n")
        result = CliRunner().invoke(
            main,
            ["run", "--quizzes-dir", "quizzes", "--mcp-command", "python server.py"],
            env={"ANTHROPIC_API_KEY": "test"},
        )

    assert result.exit_code == 1
    assert "Error: Duplicate quiz id 'q_dup' in a.yml (lines 2 and 4)" in result.output
    assert "Traceback" not in result.output


def test_grading_model_is_recorded_only_for_llm_graded_methods():
    from honest_agent.cli import _grading_model

    assert _grading_model("extract_match", "claude-haiku-4-5") == "claude-haiku-4-5"
    assert _grading_model("llm_judge", "claude-haiku-4-5") == "claude-haiku-4-5"
    assert _grading_model("contains", "claude-haiku-4-5") is None


def _run_capturing_models(monkeypatch, args: list[str]):
    import honest_agent.cli as cli_mod

    captured = {}

    async def fake_run_async(*a):
        captured["model"], captured["judge_model"] = a[2], a[-1]

    monkeypatch.setattr(cli_mod, "_run_async", fake_run_async)
    with CliRunner().isolated_filesystem():
        Path("quizzes").mkdir()
        result = CliRunner().invoke(
            main,
            ["run", "--quizzes-dir", "quizzes", "--mcp-command", "python server.py", *args],
            env={"ANTHROPIC_API_KEY": "test", "HONEST_AGENT_JUDGE_MODEL": ""},
        )
    assert result.exit_code == 0, result.output
    return captured


def test_judge_model_defaults_to_the_agent_model(monkeypatch):
    assert _run_capturing_models(monkeypatch, ["--model", "claude-sonnet-5"]) == {
        "model": "claude-sonnet-5",
        "judge_model": "claude-sonnet-5",
    }


def test_judge_model_can_differ_from_the_agent_model(monkeypatch):
    models = _run_capturing_models(monkeypatch, ["--model", "claude-sonnet-5", "--judge-model", "claude-haiku-4-5"])

    assert models == {"model": "claude-sonnet-5", "judge_model": "claude-haiku-4-5"}
