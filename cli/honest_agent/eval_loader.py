from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Defaults match what the (now-removed) dbt schema.yml used to hardcode as
# the generic test's min_score for accuracy_score / provenance_score.
DEFAULT_ACCURACY_MIN_SCORE = 0.8
DEFAULT_PROVENANCE_MIN_SCORE = 0.7


@dataclass
class EvalDefinition:
    eval_id: str
    prompt: str
    category: str
    expected_answer: str
    grading_method: str
    expected_sources: list[str]
    tags: list[str]
    # Optional human-readable name for reports; they fall back to eval_id.
    title: str | None = None
    # Optional -- tightens expected_sources to require the matched table
    # resolve to this database/schema (inline-qualified, or via a preceding
    # `use database`/`use schema` in the trace), not just any table with a
    # matching name. See provenance.py's check_provenance docstring.
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
    # e.g. {"query_warehouse": "sql"} -- declared per-eval because the field
    # name is whatever that tool's author (local YAML author, or an MCP
    # server we don't control) chose to call it. See sql_capture.py.
    sql_fields: dict[str, str] = field(default_factory=dict)


def load_evals(evals_dir: Path) -> list[EvalDefinition]:
    """Reads every *.yml in `evals_dir`. An `evals:` entry is either an eval or a
    group (a category with `tests:`) whose settings its evals inherit -- see _inherit.
    An eval's id is its explicit `id:`, else derived from its `title:` (see slugify)."""
    definitions: list[EvalDefinition] = []
    seen_in: dict[str, tuple[Path, str, str]] = {}

    for yml_path in sorted(evals_dir.glob("*.yml")):
        doc = yaml.safe_load(yml_path.read_text()) or {}

        for item in _eval_items(doc):
            title = item.get("title")
            if item.get("id"):
                eval_id, source = item["id"], ("id", item["id"])
            elif title:
                eval_id, source = slugify(title), ("title", title)
                if not eval_id:
                    raise ValueError(
                        f"Can't derive an eval id from the title {title!r} in {yml_path.name}. Add an id:."
                    )
            else:
                raise ValueError(f"An eval in {yml_path.name} has no title. Each eval needs a title (or an id).")

            if eval_id in seen_in:
                raise ValueError(_duplicate_id_message(eval_id, seen_in[eval_id], (yml_path, *source)))
            seen_in[eval_id] = (yml_path, *source)

            grading = item.get("grading", {})
            provenance = item.get("provenance", {})

            definitions.append(
                EvalDefinition(
                    eval_id=eval_id,
                    title=title,
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


def slugify(title: str) -> str:
    """Readable id from a title: "Revenue in 1996, via semantic view" -> "revenue_in_1996_via_semantic_view"."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_title.lower()).strip("_")


def _eval_items(doc: dict) -> Iterator[dict]:
    for item in doc.get("evals", []):
        if "tests" in item:
            for eval in item["tests"]:
                yield _inherit(item, eval)
        else:
            yield item


# Settings a group can't pass down: they identify one eval.
_NOT_INHERITED = {"tests", "id", "title"}


def _inherit(group: dict, eval: dict) -> dict:
    """Follows dbt's config precedence: the most specific value wins, so an eval's own
    setting overrides its group's. `grading`/`provenance` merge key by key (an eval can
    override just `min_score`), and `tags` add up instead of replacing."""
    merged = {key: value for key, value in group.items() if key not in _NOT_INHERITED}
    for key, value in eval.items():
        if key in ("grading", "provenance") and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        elif key == "tags":
            merged[key] = list(dict.fromkeys([*merged.get("tags", []), *value]))
        else:
            merged[key] = value
    return merged


def _lines(path: Path, field: str, value: str) -> list[int]:
    pattern = re.compile(rf"^\s*(?:-\s*)?{field}:\s*['\"]?{re.escape(value)}['\"]?\s*(?:#.*)?$")
    return [n for n, line in enumerate(path.read_text().splitlines(), start=1) if pattern.match(line)]


def _duplicate_id_message(eval_id: str, first: tuple[Path, str, str], second: tuple[Path, str, str]) -> str:
    """Names every place the id comes from, with line numbers when they can be found."""

    def where(path: Path, lines: list[int]) -> str:
        if not lines:
            return path.name
        return f"{path.name} (line{'s' if len(lines) > 1 else ''} {' and '.join(map(str, lines))})"

    (path1, field1, value1), (path2, field2, value2) = first, second
    if path1 == path2:
        places = where(path1, sorted(set(_lines(path1, field1, value1) + _lines(path2, field2, value2))))
    else:
        places = f"{where(path1, _lines(path1, field1, value1))} and {where(path2, _lines(path2, field2, value2))}"
    hint = ""
    if "title" in (field1, field2):
        hint = " Evals without an id: get one from their title, so change one title or give it an id:."
    return f"Duplicate eval id {eval_id!r} in {places}.{hint} Eval ids must be unique within an evals directory."


def _parse_selector(selector: str) -> list[set[str]]:
    """Parse a dbt-style tag selector into OR-of-AND tag groups: space
    separates groups (union), comma separates tags within a group
    (intersection) -- mirrors dbt's `--select`/`--exclude` set-operator
    semantics (space=union, comma=intersection). A `tag:` prefix is
    accepted but optional, for parity with dbt's `method:value` grammar --
    it's currently the only method, since evals have no dependency graph
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
    definitions: list[EvalDefinition],
    select: str | None = None,
    exclude: str | None = None,
) -> list[EvalDefinition]:
    """Filter eval definitions by tag, dbt-`--select`/`--exclude`-style.
    `select` keeps only evals matching at least one OR-group (each group
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
