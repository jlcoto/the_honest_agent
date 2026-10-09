from pathlib import Path

import pytest

from honest_agent.eval_loader import (
    DEFAULT_ACCURACY_MIN_SCORE,
    DEFAULT_PROVENANCE_MIN_SCORE,
    EvalDefinition,
    filter_by_tags,
    load_evals,
)

EVAL_YAML = """
version: 1
evals:
  - id: q_capital
    prompt: "What is the capital of France?"
    category: geography
    expected_answer: "Paris"
    tags: [smoke]
  - id: q_calc
    prompt: "What is 123 * 456?"
    category: math
    expected_answer: "56088"
    grading:
      method: contains
      min_score: 0.9
      tolerance: 0.01
      tolerance_percent: 0.02
    provenance:
      min_score: 0.6
      sql_fields:
        query_warehouse: sql_text
      expected_database: agent_quiz_demo
      expected_schema: public
    tags: [smoke, provenance]
"""


def test_load_evals_parses_yaml(tmp_path: Path):
    (tmp_path / "example_eval.yml").write_text(EVAL_YAML)

    definitions = load_evals(tmp_path)

    assert {d.eval_id for d in definitions} == {"q_capital", "q_calc"}
    calc = next(d for d in definitions if d.eval_id == "q_calc")
    assert calc.sql_fields == {"query_warehouse": "sql_text"}
    assert calc.expected_database == "agent_quiz_demo"
    assert calc.expected_schema == "public"


def test_load_evals_defaults_expected_database_and_schema_to_none(tmp_path: Path):
    (tmp_path / "example_eval.yml").write_text(EVAL_YAML)
    definitions = load_evals(tmp_path)

    capital = next(d for d in definitions if d.eval_id == "q_capital")
    assert capital.expected_database is None
    assert capital.expected_schema is None


def test_load_evals_defaults_grading_method_to_contains(tmp_path: Path):
    (tmp_path / "example_eval.yml").write_text(EVAL_YAML)
    definitions = load_evals(tmp_path)

    capital = next(d for d in definitions if d.eval_id == "q_capital")
    assert capital.grading_method == "contains"


def test_load_evals_defaults_sql_fields_to_empty_dict(tmp_path: Path):
    (tmp_path / "example_eval.yml").write_text(EVAL_YAML)
    definitions = load_evals(tmp_path)

    capital = next(d for d in definitions if d.eval_id == "q_capital")
    assert capital.sql_fields == {}


def test_load_evals_uses_explicit_thresholds_when_given(tmp_path: Path):
    (tmp_path / "example_eval.yml").write_text(EVAL_YAML)
    definitions = load_evals(tmp_path)

    calc = next(d for d in definitions if d.eval_id == "q_calc")
    assert calc.accuracy_min_score == 0.9
    assert calc.provenance_min_score == 0.6


def test_load_evals_defaults_thresholds_when_omitted(tmp_path: Path):
    (tmp_path / "example_eval.yml").write_text(EVAL_YAML)
    definitions = load_evals(tmp_path)

    capital = next(d for d in definitions if d.eval_id == "q_capital")
    assert capital.accuracy_min_score == DEFAULT_ACCURACY_MIN_SCORE
    assert capital.provenance_min_score == DEFAULT_PROVENANCE_MIN_SCORE


def test_load_evals_parses_explicit_tolerance(tmp_path: Path):
    (tmp_path / "example_eval.yml").write_text(EVAL_YAML)
    definitions = load_evals(tmp_path)

    calc = next(d for d in definitions if d.eval_id == "q_calc")
    assert calc.tolerance == 0.01
    assert calc.tolerance_percent == 0.02


def test_load_evals_defaults_tolerance_to_none(tmp_path: Path):
    (tmp_path / "example_eval.yml").write_text(EVAL_YAML)
    definitions = load_evals(tmp_path)

    capital = next(d for d in definitions if d.eval_id == "q_capital")
    assert capital.tolerance is None
    assert capital.tolerance_percent is None


def test_duplicate_eval_id_across_files_names_both(tmp_path: Path):
    (tmp_path / "a.yml").write_text("evals:\n  - id: q_dup\n    prompt: one\n    expected_answer: '1'\n")
    (tmp_path / "b.yml").write_text(
        "evals:\n  - id: q_other\n    prompt: two\n    expected_answer: '2'\n"
        "  - id: q_dup\n    prompt: three\n    expected_answer: '3'\n"
    )

    with pytest.raises(ValueError) as exc:
        load_evals(tmp_path)

    assert "Duplicate eval id 'q_dup' in a.yml (line 2) and b.yml (line 5)" in str(exc.value)


def test_duplicate_eval_id_in_one_file_names_both_lines(tmp_path: Path):
    (tmp_path / "a.yml").write_text(
        "evals:\n  - id: q_dup\n    prompt: one\n    expected_answer: '1'\n"
        "  - id: 'q_dup'\n    prompt: two\n    expected_answer: '2'\n"
    )

    with pytest.raises(ValueError) as exc:
        load_evals(tmp_path)

    assert "Duplicate eval id 'q_dup' in a.yml (lines 2 and 5)" in str(exc.value)


def _eval(eval_id: str, tags: list[str]) -> EvalDefinition:
    return EvalDefinition(
        eval_id=eval_id,
        prompt="p",
        category="c",
        expected_answer="a",
        grading_method="contains",
        expected_sources=[],
        tags=tags,
    )


_EVALS = [
    _eval("q_smoke", ["smoke"]),
    _eval("q_smoke_provenance", ["smoke", "provenance"]),
    _eval("q_motherduck", ["motherduck"]),
    _eval("q_untagged", []),
]


def test_filter_by_tags_no_selectors_returns_all():
    assert [d.eval_id for d in filter_by_tags(_EVALS)] == [d.eval_id for d in _EVALS]


def test_filter_by_tags_select_single_tag():
    result = filter_by_tags(_EVALS, select="motherduck")
    assert [d.eval_id for d in result] == ["q_motherduck"]


def test_filter_by_tags_select_accepts_tag_prefix():
    result = filter_by_tags(_EVALS, select="tag:motherduck")
    assert [d.eval_id for d in result] == ["q_motherduck"]


def test_filter_by_tags_select_space_is_union():
    result = filter_by_tags(_EVALS, select="motherduck provenance")
    assert {d.eval_id for d in result} == {"q_motherduck", "q_smoke_provenance"}


def test_filter_by_tags_select_comma_is_intersection():
    result = filter_by_tags(_EVALS, select="smoke,provenance")
    assert [d.eval_id for d in result] == ["q_smoke_provenance"]


def test_filter_by_tags_exclude_applied_after_select():
    result = filter_by_tags(_EVALS, select="smoke", exclude="provenance")
    assert [d.eval_id for d in result] == ["q_smoke"]


def test_filter_by_tags_exclude_only():
    result = filter_by_tags(_EVALS, exclude="motherduck")
    assert "q_motherduck" not in {d.eval_id for d in result}
    assert len(result) == 3


def test_load_evals_reads_optional_title(tmp_path: Path):
    (tmp_path / "titled.yml").write_text(
        "evals:\n"
        "  - id: q_titled\n"
        "    title: Total revenue in 1996\n"
        "    prompt: What was revenue in 1996?\n"
        "    expected_answer: '311928357.78'\n"
        "  - id: q_untitled\n"
        "    prompt: How many orders?\n"
        "    expected_answer: '2297'\n"
    )

    titles = {d.eval_id: d.title for d in load_evals(tmp_path)}

    assert titles == {"q_titled": "Total revenue in 1996", "q_untitled": None}


GROUPED_YAML = """
evals:
  - category: finance
    grading: {method: extract_match, min_score: 0.8}
    provenance: {sql_fields: {execute_query: sql}, min_score: 0.7}
    tags: [motherduck]
    tests:
      - title: Total revenue in 1996
        prompt: What was revenue in 1996?
        expected_answer: "311928357.78"
        provenance: {expected_sources: [lineitem]}
        tags: [smoke]
      - title: Orders placed in 1996
        id: q_order_count_1996
        prompt: How many orders in 1996?
        expected_answer: "2297"
        grading: {min_score: 0.9}
  - title: Loose eval
    prompt: Not in a group
    expected_answer: "42"
"""


def test_group_settings_are_inherited_and_most_specific_wins(tmp_path: Path):
    (tmp_path / "grouped.yml").write_text(GROUPED_YAML)

    revenue, orders, loose = load_evals(tmp_path)

    assert (revenue.category, revenue.grading_method, revenue.accuracy_min_score) == ("finance", "extract_match", 0.8)
    assert revenue.sql_fields == {"execute_query": "sql"}
    assert revenue.provenance_min_score == 0.7
    assert revenue.expected_sources == ["lineitem"]
    assert revenue.tags == ["motherduck", "smoke"]
    assert (orders.grading_method, orders.accuracy_min_score) == ("extract_match", 0.9)
    assert orders.tags == ["motherduck"]
    assert loose.category == ""


def test_eval_id_comes_from_title_unless_id_is_given(tmp_path: Path):
    (tmp_path / "grouped.yml").write_text(GROUPED_YAML)

    ids = [d.eval_id for d in load_evals(tmp_path)]

    assert ids == ["total_revenue_in_1996", "q_order_count_1996", "loose_eval"]


def test_eval_without_title_or_id_is_an_error(tmp_path: Path):
    (tmp_path / "a.yml").write_text("evals:\n  - prompt: What is 2+2?\n")

    with pytest.raises(ValueError, match="has no title"):
        load_evals(tmp_path)


def test_titles_that_slug_to_the_same_id_are_a_duplicate(tmp_path: Path):
    (tmp_path / "a.yml").write_text(
        "evals:\n  - title: Revenue 1996\n    prompt: one\n    expected_answer: '1'\n"
        "  - title: 'Revenue: 1996'\n    prompt: two\n    expected_answer: '2'\n"
    )

    with pytest.raises(ValueError) as exc:
        load_evals(tmp_path)

    message = str(exc.value)
    assert "Duplicate eval id 'revenue_1996' in a.yml (lines 2 and 5)" in message
    assert "change one title or give it an id:" in message


@pytest.mark.parametrize("answer_line", ["", "    expected_answer: ''\n", "    expected_answer:\n"])
def test_an_eval_without_an_expected_answer_is_an_error(tmp_path: Path, answer_line: str):
    """Accuracy is always checked; without an answer, `contains` would test for
    the empty string and pass every time. Provenance stays optional."""
    (tmp_path / "a.yml").write_text(
        "evals:\n  - id: q_sources_only\n    prompt: Which table holds revenue?\n"
        + answer_line
        + "    provenance: {expected_sources: [lineitem]}\n"
    )

    with pytest.raises(ValueError, match="Eval 'q_sources_only' in a.yml has no expected_answer"):
        load_evals(tmp_path)


def test_a_numeric_expected_answer_is_read_as_text(tmp_path: Path):
    (tmp_path / "a.yml").write_text(
        "evals:\n  - id: q_orders\n    prompt: How many orders?\n    expected_answer: 2297\n"
    )

    (definition,) = load_evals(tmp_path)

    assert definition.expected_answer == "2297"
