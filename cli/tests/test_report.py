from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agent_quiz_cli.cli import main
from agent_quiz_cli.storage import write_run_results


def _row() -> dict:
    return {
        "result_id": "r1",
        "run_id": "run_1",
        "run_timestamp": "2026-01-01 00:00:00",
        "quiz_id": "q1",
        "prompt": "What is 2+2?",
        "expected_answer": "4",
        "agent_answer": "<b>4</b>",
        "accuracy_score": 1.0,
        "provenance_score": 0.5,
        "model_name": "claude-test",
        "agent_trace": '[{"role": "user", "content": "What is 2+2?"}]',
        "sql_calls": [{"tool_name": "query", "sql": "select 2+2"}],
    }


def test_report_writes_ui_and_all_three_tables(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [_row()])
    out = tmp_path / "report"
    (out / "assets").mkdir(parents=True)
    (out / "assets" / "stale-old-bundle.js").write_text("")

    result = CliRunner().invoke(main, ["report", "--results-path", db_path, "--out", str(out)])

    assert result.exit_code == 0, result.output
    assert (out / "index.html").exists()
    assert not (out / "assets" / "stale-old-bundle.js").exists()
    data = json.loads((out / "data" / "report.json").read_text())
    assert [r["agent_answer"] for r in data["results"]] == ["<b>4</b>"]
    assert [log["result_id"] for log in data["agent_logs"]] == ["r1"]
    assert [json.loads(c["payload"]) for c in data["tool_calls"]] == [{"sql": "select 2+2"}]


def test_report_with_no_results_yet(tmp_path: Path):
    out = tmp_path / "report"

    result = CliRunner().invoke(main, ["report", "--results-path", str(tmp_path / "none.duckdb"), "--out", str(out)])

    assert result.exit_code == 0, result.output
    data = json.loads((out / "data" / "report.json").read_text())
    assert data["results"] == data["agent_logs"] == data["tool_calls"] == []
