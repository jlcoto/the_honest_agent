"""What `run` prints while its evals run: one line per eval as it finishes, like dbt's
`[2/16] ... PASS`, and, in a terminal, a progress bar on the bottom line that names the
eval running and ticks its time, so a long eval doesn't look stuck. The bar goes to
stderr and only when stderr is a terminal, so CI logs, pipes and files get the lines alone.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import time
from typing import Any

import click

from .thresholds import check_row

_BAR_WIDTH = 24
_MAX_ID_WIDTH = 40
_CLEAR = "\r\x1b[2K"


def duration(seconds: float) -> str:
    """8.2s under a minute, 1m 05s above."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes}m {rest:02d}s"


def _clock(seconds: float) -> str:
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes}:{rest:02d}"


def eval_line(position: int, total: int, eval_id: str, id_width: int, row: dict[str, Any], seconds: float) -> str:
    """`[2/16] revenue_q4 ...... FAIL  accuracy 0.00 · provenance 1.00  [14.9s]`, with the
    outcome from the eval's thresholds; provenance shows — when it wasn't checked."""
    checks = check_row(row)
    passed = checks["accuracy_pass"] and checks["provenance_pass"]
    outcome = click.style("PASS", fg="green") if passed else click.style("FAIL", fg="red")
    provenance = row["provenance_score"]
    scores = (
        f"accuracy {row['accuracy_score']:.2f} · provenance {'—   ' if provenance is None else f'{provenance:.2f}'}"
    )
    return f"{_lead(position, total, eval_id, id_width)} {outcome}  {scores}  [{duration(seconds)}]"


def error_line(position: int, total: int, eval_id: str, id_width: int, seconds: float) -> str:
    return f"{_lead(position, total, eval_id, id_width)} {click.style('ERROR', fg='red')}  [{duration(seconds)}]"


def _lead(position: int, total: int, eval_id: str, id_width: int) -> str:
    count = f"[{position:>{len(str(total))}}/{total}]"
    return f"{count} {eval_id} {'.' * max(3, id_width + 3 - len(eval_id))}"


def _bar_live() -> bool:
    return sys.stderr.isatty() and os.environ.get("TERM") != "dumb"


class Progress:
    """Tracks a run's evals and prints them. Use as `async with`, so the bar's ticker
    stops and the bar is cleared however the run ends."""

    def __init__(self, eval_ids: list[str], live: bool | None = None):
        self.total = len(eval_ids)
        self.done = 0
        self._id_width = min(_MAX_ID_WIDTH, max((len(i) for i in eval_ids), default=0))
        self._live = _bar_live() if live is None else live
        self._run_started = time.monotonic()
        self._current: str | None = None
        self._eval_started = self._run_started
        self._ticker: asyncio.Task | None = None
        encoding = (getattr(sys.stderr, "encoding", None) or "").lower()
        self._fill, self._empty = ("━", "─") if "utf" in encoding else ("#", "-")

    async def __aenter__(self) -> Progress:
        if self._live:
            self._ticker = asyncio.create_task(self._tick())
        return self

    async def __aexit__(self, *exc) -> None:
        if self._ticker is not None:
            self._ticker.cancel()
        self._clear()

    def start(self, eval_id: str) -> None:
        self._current, self._eval_started = eval_id, time.monotonic()
        self._draw()

    def finish(self, row: dict[str, Any], warnings: list[str]) -> None:
        """Prints the eval that just ended, then its warnings, under the line."""
        self.done += 1
        line = eval_line(self.done, self.total, row["eval_id"], self._id_width, row, self._elapsed())
        self._current = None  # no bar until the next eval starts, so it never names this one
        self.echo("\n".join([line, *(f"    WARNING: {w}" for w in warnings)]))

    def fail(self, warnings: list[str]) -> None:
        """Prints the eval that raised; the run stops after it."""
        line = error_line(self.done + 1, self.total, self._current or "?", self._id_width, self._elapsed())
        self.echo("\n".join([line, *(f"    WARNING: {w}" for w in warnings)]))

    def echo(self, text: str) -> None:
        """Prints `text` above the bar."""
        self._clear()
        click.echo(text)
        self._draw()

    def _elapsed(self) -> float:
        return time.monotonic() - self._eval_started

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(1)
            self._draw()

    def _draw(self) -> None:
        if not self._live or self._current is None or self.done >= self.total:
            return
        status = (
            f"{self.done}/{self.total} · {_clock(time.monotonic() - self._run_started)}"
            f" · running {self._current} ({int(self._elapsed())}s)"
        )
        columns = shutil.get_terminal_size().columns
        filled = round(_BAR_WIDTH * self.done / self.total) if self.total else 0
        bar = self._fill * filled + click.style(self._empty * (_BAR_WIDTH - filled), dim=True)
        # The bar only fits beside the status on a wide terminal; a line wider than the
        # terminal would wrap, and the carriage return could no longer clear it.
        text = f"{bar}  {status}" if columns >= _BAR_WIDTH + 2 + len(status) + 1 else status[: columns - 1]
        self._write(f"{_CLEAR}{text}")

    def _clear(self) -> None:
        if self._live:
            self._write(_CLEAR)

    @staticmethod
    def _write(text: str) -> None:
        # Straight to stderr: click.echo would strip the escape codes whenever it doubts
        # the stream is a terminal, and the bar is only drawn when it is one.
        sys.stderr.write(text)
        sys.stderr.flush()
