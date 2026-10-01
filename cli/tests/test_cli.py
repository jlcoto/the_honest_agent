"""Covers `agent-quiz logs`'s formatting -- pure storage read/print logic,
no LLM or MCP dependency, so it's cheap to drive end to end through the real
`run` command's storage layer instead of mocking anything.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from agent_quiz_cli.cli import main
from agent_quiz_cli.storage import write_run_results


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
                    agent_answer="[agent_quiz error] Exceeded max_tool_turns=5 without a final answer -- "
                    "the agent was still requesting tools on the last turn. See agent_trace for detail.",
                    accuracy_score=0.0,
                )
            ],
        )

        result = CliRunner().invoke(main, ["logs", "--results-path", db_path])

        assert result.exit_code == 0, result.output
        assert "Answer: [agent_quiz error] Exceeded max_tool_turns=5" in result.output
        assert "Accuracy: 0.00 (min 0.80)" in result.output


def test_logs_reports_no_matching_logs():
    with CliRunner().isolated_filesystem():
        result = CliRunner().invoke(main, ["logs", "--results-path", "results.duckdb"])

        assert result.exit_code == 0, result.output
        assert "No matching logs found." in result.output


def test_agent_name_defaults_to_the_mcp_server_name():
    from types import SimpleNamespace

    from agent_quiz_cli.cli import _resolve_agent_name

    connected = SimpleNamespace(server_info=SimpleNamespace(name="mcp-server-motherduck"))
    assert _resolve_agent_name(None, connected) == "mcp-server-motherduck"
    assert _resolve_agent_name("motherduck", connected) == "motherduck"
