from honest_agent.thresholds import check_row, failing_rows

PASSING_ROW = {
    "quiz_id": "q1",
    "accuracy_score": 0.9,
    "accuracy_min_score": 0.8,
    "provenance_score": 1.0,
    "provenance_min_score": 0.7,
}
FAILING_ACCURACY_ROW = {
    "quiz_id": "q2",
    "accuracy_score": 0.0,
    "accuracy_min_score": 0.8,
    "provenance_score": 1.0,
    "provenance_min_score": 0.7,
}
FAILING_PROVENANCE_ROW = {
    "quiz_id": "q3",
    "accuracy_score": 1.0,
    "accuracy_min_score": 0.8,
    "provenance_score": 0.0,
    "provenance_min_score": 0.7,
}


def test_check_row_passing():
    checks = check_row(PASSING_ROW)
    assert checks == {"accuracy_pass": True, "provenance_pass": True}


def test_check_row_failing_accuracy():
    checks = check_row(FAILING_ACCURACY_ROW)
    assert checks["accuracy_pass"] is False
    assert checks["provenance_pass"] is True


def test_check_row_exactly_at_threshold_passes():
    row = {**PASSING_ROW, "accuracy_score": 0.8}
    assert check_row(row)["accuracy_pass"] is True


def test_failing_rows_filters_and_augments():
    rows = [PASSING_ROW, FAILING_ACCURACY_ROW, FAILING_PROVENANCE_ROW]

    failures = failing_rows(rows)

    assert {f["quiz_id"] for f in failures} == {"q2", "q3"}
    q2 = next(f for f in failures if f["quiz_id"] == "q2")
    assert q2["accuracy_pass"] is False
