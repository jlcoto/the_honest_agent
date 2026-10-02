"""Threshold pass/fail checks over already-graded result rows.

Kept as plain functions over dicts (the same shape storage.py writes/reads)
so they're testable without any I/O -- no dbt test framework needed for a
check this simple.
"""

from __future__ import annotations

from typing import Any


def check_row(row: dict[str, Any]) -> dict[str, bool]:
    """Which of a result row's two score dimensions passed their configured threshold."""
    return {
        "accuracy_pass": row["accuracy_score"] >= row["accuracy_min_score"],
        "provenance_pass": row["provenance_score"] >= row["provenance_min_score"],
    }


def failing_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows where accuracy and/or provenance fell below threshold, each augmented
    with its check result (accuracy_pass/provenance_pass) for the caller to report on.
    """
    failures = []
    for row in rows:
        checks = check_row(row)
        if not checks["accuracy_pass"] or not checks["provenance_pass"]:
            failures.append({**row, **checks})
    return failures
