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

            # Accuracy is always checked, so an eval must say what the right answer is.
            # (Without one, `contains` would test for the empty string and always pass.)
            # Provenance stays optional: no expected_sources means it isn't checked.
            expected_answer = item.get("expected_answer")
            if expected_answer is None or not str(expected_answer).strip():
                raise ValueError(
                    f"Eval {eval_id!r} in {yml_path.name} has no expected_answer. Every eval needs one; "
                    "provenance checks (expected_sources) are optional."
                )

            grading = item.get("grading", {})
            provenance = item.get("provenance", {})

            definitions.append(
                EvalDefinition(
                    eval_id=eval_id,
                    title=title,
                    prompt=item["prompt"],
                    category=item.get("category", ""),
                    # YAML reads `expected_answer: 2297` as a number; grading compares text.
                    expected_answer=str(expected_answer),
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


class SelectorError(ValueError):
    """A --select/--exclude part that names no eval, tag or category: likely a typo."""


# dbt-style `method:value`; a bare value is an eval id, the way dbt's is a model name.
_SELECTOR_METHODS = ("tag", "category")


def _parse_selector(selector: str) -> list[list[tuple[str, str]]]:
    """A dbt-style selector as OR-groups of AND-ed parts: spaces separate groups (union),
    commas join parts within a group (intersection), as dbt's `--select` does. Each part
    is `(method, value)`: `tag:smoke`, `category:sales`, or a bare eval id (method "id")."""
    groups = []
    for group in selector.split():
        parts = []
        for part in group.split(","):
            if not part:
                continue
            method, sep, value = part.partition(":")
            if not sep:
                method, value = "id", part
            elif method not in _SELECTOR_METHODS or not value:
                raise SelectorError(f"Unknown selector {part!r}. Use an eval id, tag:<tag> or category:<category>.")
            parts.append((method, value))
        if parts:
            groups.append(parts)
    return groups


def _value_of(definition: EvalDefinition, method: str) -> set[str]:
    if method == "tag":
        return set(definition.tags)
    return {definition.category if method == "category" else definition.eval_id}


def _check_known(groups: list[list[tuple[str, str]]], definitions: list[EvalDefinition]) -> None:
    """Every part must name something that exists, so a typo is an error, not an empty run."""
    for group in groups:
        for method, value in group:
            if not any(value in _value_of(d, method) for d in definitions):
                what = {"id": "No eval has id", "tag": "No eval is tagged", "category": "No eval is in category"}
                raise SelectorError(f"{what[method]} {value!r}. `honest-agent ls` lists the evals.")


def _matches(definition: EvalDefinition, groups: list[list[tuple[str, str]]]) -> bool:
    return any(all(value in _value_of(definition, method) for method, value in group) for group in groups)


def select_evals(
    definitions: list[EvalDefinition],
    select: str | None = None,
    exclude: str | None = None,
) -> list[EvalDefinition]:
    """The evals `select` picks, minus those `exclude` picks, dbt-`--select`/`--exclude`
    style (see _parse_selector). No `select` means every eval. Raises SelectorError for a
    malformed part or one that matches no eval at all."""
    everything = definitions
    if select:
        groups = _parse_selector(select)
        _check_known(groups, everything)
        definitions = [d for d in definitions if _matches(d, groups)]
    if exclude:
        groups = _parse_selector(exclude)
        _check_known(groups, everything)  # not just what --select kept: excluding nothing is fine
        definitions = [d for d in definitions if not _matches(d, groups)]
    return definitions


def nothing_selected(select: str | None, exclude: str | None) -> str:
    """The message when every part matches some eval but together they pick none."""
    picked = f"--select {select!r}" if select else "every eval"
    return f"No eval is left by {picked}" + (f" minus --exclude {exclude!r}" if exclude else "") + "."
