"""Writes the report: the prebuilt React UI (`report_ui/`, built from the
repo's `ui/` folder and shipped inside this package) plus `data/report.json`,
which holds every row of the `results`, `traces`, and `tool_calls` tables (the raw
layer stays in the results file).

The output is a folder of static files. Browsers won't fetch the JSON from a
`file://` page, so view it through `honest-agent serve` or any static host.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .storage import latest_run_timestamp, make_output_dir, read_all_results, read_tool_calls, read_traces

UI_DIR = Path(__file__).parent / "report_ui"
# Marks a folder as honest-agent's report, which `report` may clear and rewrite.
REPORT_MARKER = ".honest_agent_report"


class ReportFolderError(Exception):
    pass


# The report shows recent history only: the browser loads report.json whole, so
# a long history would make it slow. Older results stay in the results file.
DEFAULT_WINDOW_DAYS = 30


def window_start(latest_run: str | None, days: int) -> str | None:
    """The run_timestamp `days` days before the latest run (not before today, so a
    project that hasn't run for a while still shows its last month)."""
    if latest_run is None:
        return None
    start = datetime.fromisoformat(latest_run) - timedelta(days=days)
    return start.strftime("%Y-%m-%d %H:%M:%S")  # run_timestamp's own format (derive.py)


def build_report_data(results_path: str, days: int = DEFAULT_WINDOW_DAYS) -> dict:
    since = window_start(latest_run_timestamp(results_path), days)
    results = sorted(read_all_results(results_path, since), key=lambda r: (r["run_timestamp"], r["eval_id"]))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {"days": days, "since": since},
        "results": results,
        # `traces` rows, under the key the report UI reads (ui/src/data/types.ts).
        "agent_logs": read_traces(results_path, since=since),
        "tool_calls": read_tool_calls(results_path, since=since),
    }


def generate(results_path: str, out_dir: Path, days: int = DEFAULT_WINDOW_DAYS) -> None:
    if not (UI_DIR / "index.html").exists():
        raise FileNotFoundError(f"Report UI not found at {UI_DIR}. Build it first: `cd ui && npm ci && npm run build`.")

    _claim_report_dir(out_dir)
    # Asset filenames are content-hashed, so a previous report's bundles would
    # pile up. Only this folder is cleared -- out_dir itself may be user-chosen.
    shutil.rmtree(out_dir / "assets", ignore_errors=True)
    shutil.copytree(UI_DIR, out_dir, dirs_exist_ok=True)

    data_dir = out_dir / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "report.json").write_text(json.dumps(build_report_data(results_path, days)))


def _claim_report_dir(out_dir: Path) -> None:
    """`report` clears `assets/` and overwrites `index.html`, so it only writes into a new
    folder, an empty one, or one it wrote before -- never, say, `--out .` or `--out docs`
    with someone's files in it."""
    if not out_dir.exists():
        make_output_dir(out_dir)
    elif not (out_dir / REPORT_MARKER).exists() and any(out_dir.iterdir()):
        raise ReportFolderError(
            f"{out_dir} isn't empty and isn't an honest-agent report folder, so `report` won't write into it "
            "(it would delete and overwrite files there). Pick a new or empty folder with --out."
        )
    (out_dir / REPORT_MARKER).write_text("Written by `honest-agent report`, which may clear and rewrite this folder.\n")
