from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from honest_agent.cli import main
from honest_agent.report import build_report_data
from honest_agent.storage import write_run_results


def _row() -> dict:
    return {
        "result_id": "r1",
        "run_id": "run_1",
        "run_timestamp": "2026-01-01 00:00:00",
        "eval_id": "q1",
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
    out = tmp_path / "report"  # a previous report, with an old bundle to clear
    (out / "assets").mkdir(parents=True)
    (out / "assets" / "stale-old-bundle.js").write_text("")
    (out / ".honest_agent_report").write_text("")

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


def test_a_report_folder_honest_agent_creates_ignores_itself_but_an_existing_one_is_left_alone(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [_row()])
    existing = tmp_path / "site"
    existing.mkdir()

    CliRunner().invoke(main, ["report", "--results-path", db_path, "--out", str(tmp_path / "new_report")])
    CliRunner().invoke(main, ["report", "--results-path", db_path, "--out", str(existing)])

    assert (tmp_path / "new_report" / ".gitignore").read_text().endswith("*\n")
    assert (tmp_path / "new_report" / "index.html").exists()
    assert not (existing / ".gitignore").exists()


def test_report_refuses_a_folder_with_someone_elses_files(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [_row()])
    docs = tmp_path / "docs"
    (docs / "assets").mkdir(parents=True)
    (docs / "assets" / "logo.png").write_text("not ours")

    result = CliRunner().invoke(main, ["report", "--results-path", db_path, "--out", str(docs)])

    assert result.exit_code != 0
    assert "isn't an honest-agent report folder" in result.output
    assert (docs / "assets" / "logo.png").read_text() == "not ours"


def test_report_rewrites_its_own_folder_and_accepts_an_empty_one(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    write_run_results(db_path, "run_1", [_row()])
    empty = tmp_path / "empty"
    empty.mkdir()

    for out in (tmp_path / "new", tmp_path / "new", empty):
        result = CliRunner().invoke(main, ["report", "--results-path", db_path, "--out", str(out)])
        assert result.exit_code == 0, result.output

    for out in (tmp_path / "new", empty):
        assert (out / ".honest_agent_report").exists()


def _write_runs(db_path: str) -> None:
    """Runs on Jan 1, Feb 20 and Mar 1: the last two are within 30 days of the latest."""
    for run, day in (("old", "2026-01-01"), ("recent", "2026-02-20"), ("latest", "2026-03-01")):
        row = {**_row(), "result_id": f"r_{run}", "run_id": run, "run_timestamp": f"{day} 09:00:00"}
        write_run_results(db_path, run, [row])


def test_report_shows_the_30_days_before_the_latest_run(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    _write_runs(db_path)

    data = build_report_data(db_path)

    assert data["window"] == {"days": 30, "since": "2026-01-30 09:00:00"}
    for table in ("results", "agent_logs", "tool_calls"):
        assert {r["result_id"] for r in data[table]} == {"r_recent", "r_latest"}, table


def test_report_days_widens_the_window(tmp_path: Path):
    db_path = str(tmp_path / "results.duckdb")
    _write_runs(db_path)
    out = tmp_path / "report"

    result = CliRunner().invoke(main, ["report", "--results-path", db_path, "--out", str(out), "--days", "90"])

    assert result.exit_code == 0, result.output
    data = json.loads((out / "data" / "report.json").read_text())
    assert {r["result_id"] for r in data["results"]} == {"r_old", "r_recent", "r_latest"}
