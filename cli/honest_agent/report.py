"""Writes the report: the prebuilt React UI (`report_ui/`, built from the
repo's `ui/` folder and shipped inside this package) plus `data/report.json`,
which holds every row of the `results`, `agent_logs`, and `tool_calls` tables.

The output is a folder of static files. Browsers won't fetch the JSON from a
`file://` page, so view it through `honest-agent serve` or any static host.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .storage import make_output_dir, read_agent_logs, read_all_results, read_tool_calls

UI_DIR = Path(__file__).parent / "report_ui"


def build_report_data(results_path: str) -> dict:
    results = sorted(read_all_results(results_path), key=lambda r: (r["run_timestamp"], r["eval_id"]))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "results": results,
        "agent_logs": read_agent_logs(results_path),
        "tool_calls": read_tool_calls(results_path),
    }


def generate(results_path: str, out_dir: Path) -> None:
    if not (UI_DIR / "index.html").exists():
        raise FileNotFoundError(f"Report UI not found at {UI_DIR}. Build it first: `cd ui && npm ci && npm run build`.")

    make_output_dir(out_dir)
    # Asset filenames are content-hashed, so a previous report's bundles would
    # pile up. Only this folder is cleared -- out_dir itself may be user-chosen.
    shutil.rmtree(out_dir / "assets", ignore_errors=True)
    shutil.copytree(UI_DIR, out_dir, dirs_exist_ok=True)

    data_dir = out_dir / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "report.json").write_text(json.dumps(build_report_data(results_path)))
