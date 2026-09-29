from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Defaults match what the (now-removed) dbt schema.yml used to hardcode as
# the generic test's min_score for accuracy_score / provenance_score.
DEFAULT_ACCURACY_MIN_SCORE = 0.8
DEFAULT_PROVENANCE_MIN_SCORE = 0.7


@dataclass
class QuizDefinition:
    quiz_id: str
    prompt: str
    category: str
    expected_answer: str
    grading_method: str
    expected_sources: list[str]
    tags: list[str]
    # Optional -- tightens expected_sources to require the matched table
    # resolve to this database/schema (inline-qualified, or via a preceding
    # `use database`/`use schema` in the trace), not just any table with a
    # matching name. See provenance.py's score_provenance docstring.
    expected_database: str | None = None
    expected_schema: str | None = None
    accuracy_min_score: float = DEFAULT_ACCURACY_MIN_SCORE
    provenance_min_score: float = DEFAULT_PROVENANCE_MIN_SCORE
    # Only used by grading.method: extract_match -- let a numeric answer
    # differ from expected_answer instead of requiring an exact string
    # match. `tolerance` is an absolute delta; `tolerance_percent` is
    # relative to expected_answer's magnitude (0.01 = within 1%). Naming
    # mirrors dbt-expectations' expect_table_aggregation_to_equal_other_table.
    # None (default, both) keeps exact matching.
    tolerance: float | None = None
    tolerance_percent: float | None = None
    # Maps a tool name to the input field of its calls that holds SQL text,
    # e.g. {"query_warehouse": "sql"} -- declared per-quiz because the field
    # name is whatever that tool's author (local YAML author, or an MCP
    # server we don't control) chose to call it. See sql_capture.py.
    sql_fields: dict[str, str] = field(default_factory=dict)


def load_quizzes(quizzes_dir: Path) -> list[QuizDefinition]:
    definitions: list[QuizDefinition] = []
    seen_ids: set[str] = set()

    for yml_path in sorted(quizzes_dir.glob("*.yml")):
        doc = yaml.safe_load(yml_path.read_text()) or {}

        for item in doc.get("quizzes", []):
            quiz_id = item["id"]
            if quiz_id in seen_ids:
                raise ValueError(f"Duplicate quiz id {quiz_id!r} in {yml_path}")
            seen_ids.add(quiz_id)

            grading = item.get("grading", {})
            provenance = item.get("provenance", {})

            definitions.append(
                QuizDefinition(
                    quiz_id=quiz_id,
                    prompt=item["prompt"],
                    category=item.get("category", ""),
                    expected_answer=item.get("expected_answer", ""),
                    grading_method=grading.get("method", "contains"),
                    expected_sources=provenance.get("expected_sources", []),
                    tags=item.get("tags", []),
                    accuracy_min_score=grading.get("min_score", DEFAULT_ACCURACY_MIN_SCORE),
                    tolerance=grading.get("tolerance"),
                    tolerance_percent=grading.get("tolerance_percent"),
                    provenance_min_score=provenance.get("min_score", DEFAULT_PROVENANCE_MIN_SCORE),
                    sql_fields=provenance.get("sql_fields", {}),
                    expected_database=provenance.get("expected_database"),
                    expected_schema=provenance.get("expected_schema"),
                )
            )

    return definitions


def _parse_selector(selector: str) -> list[set[str]]:
    """Parse a dbt-style tag selector into OR-of-AND tag groups: space
    separates groups (union), comma separates tags within a group
    (intersection) -- mirrors dbt's `--select`/`--exclude` set-operator
    semantics (space=union, comma=intersection). A `tag:` prefix is
    accepted but optional, for parity with dbt's `method:value` grammar --
    it's currently the only method, since quizzes have no dependency graph
    to support path/fqn/graph-operator selectors.
    """
    groups: list[set[str]] = []
    for group in selector.split():
        tags = {tag[len("tag:") :] if tag.startswith("tag:") else tag for tag in group.split(",") if tag}
        if tags:
            groups.append(tags)
    return groups


def _matches_selector(definition_tags: list[str], groups: list[set[str]]) -> bool:
    tag_set = set(definition_tags)
    return any(group.issubset(tag_set) for group in groups)


def filter_by_tags(
    definitions: list[QuizDefinition],
    select: str | None = None,
    exclude: str | None = None,
) -> list[QuizDefinition]:
    """Filter quiz definitions by tag, dbt-`--select`/`--exclude`-style.
    `select` keeps only quizzes matching at least one OR-group (each group
    itself an AND of its comma-separated tags); `exclude` is then applied
    the same way, subtractively, on top of that result.
    """
    if select:
        select_groups = _parse_selector(select)
        definitions = [d for d in definitions if _matches_selector(d.tags, select_groups)]
    if exclude:
        exclude_groups = _parse_selector(exclude)
        definitions = [d for d in definitions if not _matches_selector(d.tags, exclude_groups)]
    return definitions
