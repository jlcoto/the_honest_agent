"""What `run` prints per eval, and the progress bar it draws in a terminal."""

from __future__ import annotations

import asyncio

from honest_agent.progress import Progress, duration, eval_line


def _row(eval_id="revenue_q4", accuracy=1.0, provenance=1.0):
    return {
        "eval_id": eval_id,
        "accuracy_score": accuracy,
        "provenance_score": provenance,
        "accuracy_min_score": 0.8,
        "provenance_min_score": 0.7,
    }


def test_each_line_has_the_position_outcome_scores_and_time():
    assert eval_line(2, 16, "revenue_q4", 12, _row(accuracy=0.0), 14.94) == (
        "[ 2/16] revenue_q4 ..... \x1b[31mFAIL\x1b[0m  accuracy 0.00 · provenance 1.00  [14.9s]"
    )
    assert "PASS\x1b[0m  accuracy 1.00 · provenance —     [" in eval_line(1, 1, "q", 1, _row(provenance=None), 3)


def test_times_over_a_minute_show_minutes():
    assert (duration(8.21), duration(65), duration(600)) == ("8.2s", "1m 05s", "10m 00s")


async def _two_evals(progress: Progress):
    async with progress:
        progress.start("revenue_q4")
        progress.finish(_row(), ["revenue_q4 hit the step limit without a final answer."])
        progress.start("top_segment")
        progress.fail([])


def test_without_a_terminal_only_the_lines_print_with_warnings_under_their_eval(capsys):
    asyncio.run(_two_evals(Progress(["revenue_q4", "top_segment"], live=False)))

    out, err = capsys.readouterr()
    lines = out.splitlines()
    assert lines[0].startswith("[1/2] revenue_q4 .... PASS")
    assert lines[1] == "    WARNING: revenue_q4 hit the step limit without a final answer."
    assert lines[2].startswith("[2/2] top_segment ... ERROR")
    assert err == ""


def test_in_a_terminal_the_bar_names_the_running_eval_on_stderr(capsys, monkeypatch):
    monkeypatch.setattr("shutil.get_terminal_size", lambda: __import__("os").terminal_size((100, 24)))
    asyncio.run(_two_evals(Progress(["revenue_q4", "top_segment"], live=True)))

    out, err = capsys.readouterr()
    assert "running revenue_q4 (0s)" in err
    assert "1/2 · 0:00 · running top_segment" in err
    assert err.endswith("\r\x1b[2K")  # cleared when the run ends
    assert "running" not in out


def test_a_narrow_terminal_gets_the_status_without_the_bar_and_never_wraps(capsys, monkeypatch):
    monkeypatch.setattr("shutil.get_terminal_size", lambda: __import__("os").terminal_size((30, 24)))
    progress = Progress(["a_long_eval_name_here"], live=True)
    progress.start("a_long_eval_name_here")

    drawn = capsys.readouterr().err.removeprefix("\r\x1b[2K")
    assert drawn == "0/1 · 0:00 · running a_long_e"
    assert len(drawn) == 29
