from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .storage import read_all_results


def _accuracy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "run_id": r["run_id"],
            "run_timestamp": r["run_timestamp"],
            "quiz_id": r["quiz_id"],
            "category": r["category"],
            "prompt": r["prompt"],
            "expected_answer": r["expected_answer"],
            "agent_answer": r["agent_answer"],
            "accuracy_method": r["accuracy_method"],
            "accuracy_score": r["accuracy_score"],
            "accuracy_min_score": r["accuracy_min_score"],
            "accuracy_rationale": r["accuracy_rationale"],
            "model_name": r["model_name"],
            "latency_ms": r["latency_ms"],
        }
        for r in rows
    ]


def _provenance_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "run_id": r["run_id"],
            "run_timestamp": r["run_timestamp"],
            "quiz_id": r["quiz_id"],
            "category": r["category"],
            "tools_used": r["tools_used"],
            "expected_sources": r["expected_sources"],
            "expected_database": r["expected_database"],
            "expected_schema": r["expected_schema"],
            "provenance_score": r["provenance_score"],
            "provenance_min_score": r["provenance_min_score"],
            "model_name": r["model_name"],
        }
        for r in rows
    ]


def _summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_run[r["run_id"]].append(r)

    summaries = []
    for run_id, run_rows in by_run.items():
        accuracy_scores = [r["accuracy_score"] for r in run_rows]
        provenance_scores = [r["provenance_score"] for r in run_rows]
        timestamps = [r["run_timestamp"] for r in run_rows]
        summaries.append(
            {
                "run_id": run_id,
                "run_started_at": min(timestamps),
                "run_finished_at": max(timestamps),
                "quiz_count": len(run_rows),
                "avg_accuracy_score": sum(accuracy_scores) / len(accuracy_scores),
                "min_accuracy_score": min(accuracy_scores),
                "avg_provenance_score": sum(provenance_scores) / len(provenance_scores),
                "min_provenance_score": min(provenance_scores),
            }
        )
    summaries.sort(key=lambda s: s["run_started_at"])
    return summaries


def _table_html(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p><em>No data yet.</em></p>"
    headers = list(rows[0].keys())
    head_html = "".join(f"<th>{h}</th>" for h in headers)
    body_html = "".join("<tr>" + "".join(f"<td>{row.get(h, '')}</td>" for h in headers) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>"


def _render_html(summary_rows: list[dict], accuracy_rows: list[dict], provenance_rows: list[dict]) -> str:
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Agent Quiz Report</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 2rem; color: #1a1a1a; }}
  h2 {{ margin-top: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 0.5rem; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; font-size: 0.9rem; }}
  th {{ background: #f5f5f5; }}
</style>
</head>
<body>
  <h1>Agent Quiz Report</h1>
  <h2>Run summary</h2>
  {_table_html(summary_rows)}
  <h2>Accuracy scores</h2>
  {_table_html(accuracy_rows)}
  <h2>Provenance scores</h2>
  {_table_html(provenance_rows)}
</body>
</html>
"""


def generate(results_path: str, out_path: Path) -> None:
    rows = read_all_results(results_path)
    html = _render_html(_summary_rows(rows), _accuracy_rows(rows), _provenance_rows(rows))
    out_path.write_text(html)
