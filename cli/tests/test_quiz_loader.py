from pathlib import Path

from agent_quiz_cli.quiz_loader import (
    DEFAULT_ACCURACY_MIN_SCORE,
    DEFAULT_PROVENANCE_MIN_SCORE,
    QuizDefinition,
    filter_by_tags,
    load_quizzes,
)

QUIZ_YAML = """
version: 1
quizzes:
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


def test_load_quizzes_parses_yaml(tmp_path: Path):
    (tmp_path / "example_quiz.yml").write_text(QUIZ_YAML)

    definitions = load_quizzes(tmp_path)

    assert {d.quiz_id for d in definitions} == {"q_capital", "q_calc"}
    calc = next(d for d in definitions if d.quiz_id == "q_calc")
    assert calc.sql_fields == {"query_warehouse": "sql_text"}
    assert calc.expected_database == "agent_quiz_demo"
    assert calc.expected_schema == "public"


def test_load_quizzes_defaults_expected_database_and_schema_to_none(tmp_path: Path):
    (tmp_path / "example_quiz.yml").write_text(QUIZ_YAML)
    definitions = load_quizzes(tmp_path)

    capital = next(d for d in definitions if d.quiz_id == "q_capital")
    assert capital.expected_database is None
    assert capital.expected_schema is None


def test_load_quizzes_defaults_grading_method_to_contains(tmp_path: Path):
    (tmp_path / "example_quiz.yml").write_text(QUIZ_YAML)
    definitions = load_quizzes(tmp_path)

    capital = next(d for d in definitions if d.quiz_id == "q_capital")
    assert capital.grading_method == "contains"


def test_load_quizzes_defaults_sql_fields_to_empty_dict(tmp_path: Path):
    (tmp_path / "example_quiz.yml").write_text(QUIZ_YAML)
    definitions = load_quizzes(tmp_path)

    capital = next(d for d in definitions if d.quiz_id == "q_capital")
    assert capital.sql_fields == {}


def test_load_quizzes_uses_explicit_thresholds_when_given(tmp_path: Path):
    (tmp_path / "example_quiz.yml").write_text(QUIZ_YAML)
    definitions = load_quizzes(tmp_path)

    calc = next(d for d in definitions if d.quiz_id == "q_calc")
    assert calc.accuracy_min_score == 0.9
    assert calc.provenance_min_score == 0.6


def test_load_quizzes_defaults_thresholds_when_omitted(tmp_path: Path):
    (tmp_path / "example_quiz.yml").write_text(QUIZ_YAML)
    definitions = load_quizzes(tmp_path)

    capital = next(d for d in definitions if d.quiz_id == "q_capital")
    assert capital.accuracy_min_score == DEFAULT_ACCURACY_MIN_SCORE
    assert capital.provenance_min_score == DEFAULT_PROVENANCE_MIN_SCORE


def test_load_quizzes_parses_explicit_tolerance(tmp_path: Path):
    (tmp_path / "example_quiz.yml").write_text(QUIZ_YAML)
    definitions = load_quizzes(tmp_path)

    calc = next(d for d in definitions if d.quiz_id == "q_calc")
    assert calc.tolerance == 0.01
    assert calc.tolerance_percent == 0.02


def test_load_quizzes_defaults_tolerance_to_none(tmp_path: Path):
    (tmp_path / "example_quiz.yml").write_text(QUIZ_YAML)
    definitions = load_quizzes(tmp_path)

    capital = next(d for d in definitions if d.quiz_id == "q_capital")
    assert capital.tolerance is None
    assert capital.tolerance_percent is None


def test_duplicate_quiz_id_raises(tmp_path: Path):
    (tmp_path / "a.yml").write_text(QUIZ_YAML)
    (tmp_path / "b.yml").write_text(QUIZ_YAML)

    try:
        load_quizzes(tmp_path)
        raise AssertionError("expected ValueError for duplicate quiz id")
    except ValueError:
        pass


def _quiz(quiz_id: str, tags: list[str]) -> QuizDefinition:
    return QuizDefinition(
        quiz_id=quiz_id,
        prompt="p",
        category="c",
        expected_answer="a",
        grading_method="contains",
        expected_sources=[],
        tags=tags,
    )


_QUIZZES = [
    _quiz("q_smoke", ["smoke"]),
    _quiz("q_smoke_provenance", ["smoke", "provenance"]),
    _quiz("q_motherduck", ["motherduck"]),
    _quiz("q_untagged", []),
]


def test_filter_by_tags_no_selectors_returns_all():
    assert [d.quiz_id for d in filter_by_tags(_QUIZZES)] == [d.quiz_id for d in _QUIZZES]


def test_filter_by_tags_select_single_tag():
    result = filter_by_tags(_QUIZZES, select="motherduck")
    assert [d.quiz_id for d in result] == ["q_motherduck"]


def test_filter_by_tags_select_accepts_tag_prefix():
    result = filter_by_tags(_QUIZZES, select="tag:motherduck")
    assert [d.quiz_id for d in result] == ["q_motherduck"]


def test_filter_by_tags_select_space_is_union():
    result = filter_by_tags(_QUIZZES, select="motherduck provenance")
    assert {d.quiz_id for d in result} == {"q_motherduck", "q_smoke_provenance"}


def test_filter_by_tags_select_comma_is_intersection():
    result = filter_by_tags(_QUIZZES, select="smoke,provenance")
    assert [d.quiz_id for d in result] == ["q_smoke_provenance"]


def test_filter_by_tags_exclude_applied_after_select():
    result = filter_by_tags(_QUIZZES, select="smoke", exclude="provenance")
    assert [d.quiz_id for d in result] == ["q_smoke"]


def test_filter_by_tags_exclude_only():
    result = filter_by_tags(_QUIZZES, exclude="motherduck")
    assert "q_motherduck" not in {d.quiz_id for d in result}
    assert len(result) == 3


def test_load_quizzes_reads_optional_title(tmp_path: Path):
    (tmp_path / "titled.yml").write_text(
        "quizzes:\n"
        "  - id: q_titled\n"
        "    title: Total revenue in 1996\n"
        "    prompt: What was revenue in 1996?\n"
        "  - id: q_untitled\n"
        "    prompt: How many orders?\n"
    )

    titles = {d.quiz_id: d.title for d in load_quizzes(tmp_path)}

    assert titles == {"q_titled": "Total revenue in 1996", "q_untitled": None}
