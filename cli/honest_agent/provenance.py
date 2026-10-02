from __future__ import annotations

import re

_USE_DATABASE_RE = re.compile(r"\buse\s+database\s+\"?([\w$]+)\"?", re.IGNORECASE)
_USE_SCHEMA_RE = re.compile(r"\buse\s+schema\s+\"?([\w$]+)\"?", re.IGNORECASE)


def _track_session_context(sql_statements: list[str]) -> list[tuple[str, str | None, str | None]]:
    """Walks captured SQL in trace order (across every tool call, not just
    one), tracking `use database <x>` / `use schema <x>` as running session
    state -- a warehouse like Snowflake lets an agent fix its database/schema
    with a separate statement and then reference tables unqualified from
    then on, so a bare table name in one call can only be resolved correctly
    by knowing what a *previous* call's `use` statement set.

    Returns one `(sql, database, schema)` tuple per input statement: the
    database/schema tracked *as of* that statement (after applying any `use`
    found within it), for resolving that statement's own unqualified table
    references.
    """
    current_db: str | None = None
    current_schema: str | None = None
    resolved: list[tuple[str, str | None, str | None]] = []
    for sql in sql_statements:
        db_match = _USE_DATABASE_RE.search(sql)
        if db_match:
            current_db = db_match.group(1)
        schema_match = _USE_SCHEMA_RE.search(sql)
        if schema_match:
            current_schema = schema_match.group(1)
        resolved.append((sql, current_db, current_schema))
    return resolved


_TABLE_REF_PATTERN_CACHE: dict[str, re.Pattern] = {}


def _table_ref_pattern(table: str) -> re.Pattern:
    """Matches `table`, optionally preceded by one or two dotted
    identifiers (`schema.table` or `database.schema.table`) -- so a single
    scan can tell whether a given occurrence was qualified, and with what.
    """
    if table not in _TABLE_REF_PATTERN_CACHE:
        _TABLE_REF_PATTERN_CACHE[table] = re.compile(
            r"(?:\b([A-Za-z_][\w$]*)\.)?(?:\b([A-Za-z_][\w$]*)\.)?\b" + re.escape(table) + r"\b",
            re.IGNORECASE,
        )
    return _TABLE_REF_PATTERN_CACHE[table]


def _has_qualifying_occurrence(
    resolved_statements: list[tuple[str, str | None, str | None]],
    source: str,
    expected_database: str | None,
    expected_schema: str | None,
) -> bool:
    """True if some occurrence of `source` resolves -- via inline
    qualification, or via `use database`/`use schema` tracked up to that
    point -- to `expected_database`/`expected_schema` (whichever is given).
    """
    pattern = _table_ref_pattern(source)
    for sql, session_db, session_schema in resolved_statements:
        for match in pattern.finditer(sql):
            part1, part2 = match.group(1), match.group(2)
            if part1 and part2:
                database, schema = part1, part2
            elif part1:
                # a single qualifier before a table is conventionally its
                # schema (`schema.table`), not its database.
                database, schema = session_db, part1
            else:
                database, schema = session_db, session_schema

            if expected_database and (database or "").lower() != expected_database.lower():
                continue
            if expected_schema and (schema or "").lower() != expected_schema.lower():
                continue
            return True
    return False


def _source_recall(
    sql_statements: list[str],
    expected_sources: list[str],
    expected_database: str | None = None,
    expected_schema: str | None = None,
) -> float:
    combined_sql = "\n".join(sql_statements).lower()
    # Only pay for session-context tracking when an eval actually asks for
    # location checking -- otherwise this is the same bare word-boundary
    # check it's always been, so existing evals' scores can't shift.
    resolved = _track_session_context(sql_statements) if (expected_database or expected_schema) else None

    def is_hit(source: str) -> bool:
        if not re.search(r"\b" + re.escape(source.lower()) + r"\b", combined_sql):
            return False
        if resolved is None:
            return True
        return _has_qualifying_occurrence(resolved, source, expected_database, expected_schema)

    hits = sum(1 for source in expected_sources if is_hit(source))
    return hits / len(expected_sources)


def score_provenance(
    sql_statements: list[str] | None = None,
    expected_sources: list[str] | None = None,
    expected_database: str | None = None,
    expected_schema: str | None = None,
) -> float:
    """Recall over one provenance claim an eval can make: does the SQL the
    agent actually ran reference the tables/models we expected -- e.g. an
    aggregated mart or semantic-layer model, not the agent reconstructing
    the number by hand from raw tables. Checked against `sql_statements`
    (see sql_capture.py).

    `expected_database`/`expected_schema` optionally tighten this: a source
    only counts as found if some occurrence of it resolves (via inline
    qualification, or a preceding `use database`/`use schema` in the trace)
    to the given database/schema -- otherwise a query against a same-named
    table in the wrong database (e.g. Snowflake's built-in
    `snowflake_sample_data` instead of the real target) would still count as
    a hit. Neither is required; an eval that only cares *which table*, not
    *which database it lives in*, can leave both unset and get the old,
    looser behavior.

    An eval with no `expected_sources` declared at all is trivially satisfied
    (1.0).

    There used to be a second dimension here, `expected_tools` (did the
    agent call the tools we expected) -- deliberately removed. It was
    redundant with this one by construction whenever both were declared for
    the same SQL-producing tool: `expected_sources` can only score >0 if
    some real tool call actually happened and returned matching content, so
    it already implies tool use, more precisely than a bare tool-name check
    ever could. The only place `expected_tools` wasn't redundant was for
    tools that produce no checkable SQL/source content at all (e.g. a
    calculator) -- no eval in this project currently needs that, so it's
    not worth carrying the dead weight until one does. See
    memory/expected_tools_removed_from_provenance.md (or its successor) for
    the full reasoning if this needs revisiting once semantic-layer tool
    checks are better understood.

    Caveat: source checking only sees SQL text captured by sql_capture.py.
    An agent that reaches the right model through a non-SQL interface (e.g.
    a semantic-layer tool call with structured args like {"metric":
    "revenue"}, no SQL string anywhere) won't be detected here -- this
    checks *queries*, not arbitrary structured tool arguments.
    """
    sql_statements = sql_statements or []
    expected_sources = expected_sources or []

    if not expected_sources:
        return 1.0
    return _source_recall(sql_statements, expected_sources, expected_database, expected_schema)
