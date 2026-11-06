"""Threshold pass/fail checks over already-graded result rows.

Kept as plain functions over dicts (the same shape storage.py writes/reads)
so they're testable without any I/O -- no dbt test framework needed for a
check this simple.
"""

from __future__ import annotations

from typing import Any

# The rationale derive.py gives an eval that stopped with an error, before the reason.
EVAL_ERROR = "[honest-agent error] The eval stopped: "


def is_error(row: dict[str, Any]) -> bool:
    """Whether the eval stopped with an error: it has no scores, and counts as failing."""
    return row.get("status") == "error"


def error_reason(row: dict[str, Any]) -> str:
    """Why an errored eval stopped, as the run recorded it."""
    return (row["accuracy_rationale"] or "").removeprefix(EVAL_ERROR)


def check_row(row: dict[str, Any]) -> dict[str, bool]:
    """Which of a result row's two score dimensions passed their configured threshold.
    Provenance that wasn't checked (no expected sources, score None) can't fail; an eval
    that stopped with an error fails both."""
    if is_error(row):
        return {"accuracy_pass": False, "provenance_pass": False}
    provenance = row["provenance_score"]
    return {
        "accuracy_pass": row["accuracy_score"] >= row["accuracy_min_score"],
        "provenance_pass": provenance is None or provenance >= row["provenance_min_score"],
    }


def failing_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows where accuracy and/or provenance fell below threshold, or that stopped with
    an error (`is_error`), each augmented with its check result (accuracy_pass/
    provenance_pass) for the caller to report on.
    """
    failures = []
    for row in rows:
        checks = check_row(row)
        if not checks["accuracy_pass"] or not checks["provenance_pass"]:
            failures.append({**row, **checks})
    return failures
