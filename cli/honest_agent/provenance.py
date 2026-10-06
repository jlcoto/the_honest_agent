"""Scores provenance: did the SQL the agent ran read the sources an eval
expects (e.g. an aggregated mart or a semantic view, not raw tables the
agent stitched together by hand)?

The SQL is parsed with sqlglot rather than searched as text, so only real
table references count: not a name in a comment, a string, a column or a
CTE the query defines itself. Each reference comes with its database and
schema, as written or as set by earlier `use database`/`use schema`
statements, which is also what the report shows as "what the agent queried".

Only statements that read data (`select`, including `with ... select` and
`union`) count. `describe`, `show` and the like are exploration: an agent
that describes the right table but queries another one hasn't used it.
Calls that returned an error are left out by the caller (see cli.py), since
a query that failed read nothing.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import sqlglot
from sqlglot import exp

# sqlglot logs a warning for each statement it can only keep as raw text (e.g.
# Snowflake's `show semantic views`); those are never reads, so the noise isn't useful.
logging.getLogger("sqlglot").setLevel(logging.ERROR)

# Tried in order. Snowflake's dialect also reads the DuckDB/MotherDuck SQL seen so far.
_DIALECTS = ("snowflake", "duckdb")


class Source(NamedTuple):
    """A table, view or semantic view. `database`/`schema` are None when
    neither the SQL nor an earlier `use` statement said which."""

    database: str | None
    schema: str | None
    name: str


class Provenance(NamedTuple):
    score: float
    # Every source the counted statements read, in first-seen order, without repeats.
    queried_sources: list[Source]
    # SQL that couldn't be parsed, so it contributed no sources.
    unparsed: list[str]


def _parse(sql: str) -> list[exp.Expression] | None:
    for dialect in _DIALECTS:
        try:
            return [tree for tree in sqlglot.parse(sql, read=dialect) if tree is not None]
        except sqlglot.errors.SqlglotError:
            continue
    return None


def _apply_use(statement: exp.Use, database: str | None, schema: str | None) -> tuple[str | None, str | None]:
    """`use database x`, `use schema [x.]y`, or Snowflake's bare `use x[.y]`."""
    target = statement.this
    if not isinstance(target, exp.Table) or not target.name:
        return database, schema
    kind = statement.args.get("kind")
    kind = kind.sql().lower() if kind is not None else None
    if kind == "database":
        return target.name, None
    if kind == "schema":
        return target.db or database, target.name
    if kind is None:
        return (target.db, target.name) if target.db else (target.name, None)
    return database, schema  # use warehouse / use role


def _sources_read(statement: exp.Query, database: str | None, schema: str | None) -> list[Source]:
    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    sources = []
    for table in statement.find_all(exp.Table):
        if not table.name:
            continue  # a table function, e.g. semantic_view(...) itself
        if not table.catalog and not table.db and table.name.lower() in cte_names:
            continue
        # A single qualifier (`x.table`) is the schema, as warehouses read it.
        sources.append(Source(table.catalog or database, table.db or schema, table.name))
    return sources


def queried_sources(sql_statements: list[str]) -> tuple[list[Source], list[str]]:
    """Walks the SQL in the order it ran, tracking `use` statements as session
    state (they carry across tool calls), and returns the sources every read
    statement referenced, plus the SQL that couldn't be parsed."""
    database: str | None = None
    schema: str | None = None
    seen: dict[tuple, Source] = {}
    unparsed: list[str] = []
    for sql in sql_statements:
        statements = _parse(sql)
        if statements is None:
            unparsed.append(sql)
            continue
        for statement in statements:
            if isinstance(statement, exp.Use):
                database, schema = _apply_use(statement, database, schema)
            elif isinstance(statement, exp.Query):
                for source in _sources_read(statement, database, schema):
                    key = tuple((part or "").lower() for part in source)
                    seen.setdefault(key, source)
    return list(seen.values()), unparsed


def _matches(queried: Source, expected: Source) -> bool:
    """Name always; database/schema only where the expectation names one."""
    return all(want is None or (got or "").lower() == want.lower() for got, want in zip(queried, expected, strict=True))


def _expected(entry: str, expected_database: str | None, expected_schema: str | None) -> Source:
    """An `expected_sources` entry, read like a table name in SQL: `table`,
    `schema.table` or `database.schema.table`. Parts it leaves out fall back
    to the eval's `expected_database`/`expected_schema`."""
    table = exp.to_table(entry, dialect="snowflake")
    return Source(table.catalog or expected_database, table.db or expected_schema, table.name)


def check_provenance(
    sql_statements: list[str] | None = None,
    expected_sources: list[str] | None = None,
    expected_database: str | None = None,
    expected_schema: str | None = None,
) -> Provenance:
    """Recall over `expected_sources`: the share of them some read statement
    referenced, in the expected database/schema where one is given. An eval
    with no `expected_sources` is trivially satisfied (1.0).

    An entry can carry its own location (`snowflake_sample_data.tpch_sf1.customer`,
    `staging.customer_flags`); `expected_database`/`expected_schema` apply to
    the parts an entry leaves out. Without either, any database/schema counts.
    A reference whose database or schema is unknown (a bare name with no
    earlier `use`) doesn't match an expected one.

    Caveat: this only sees SQL captured by sql_capture.py. An agent that
    reaches a semantic layer through structured, non-SQL tool arguments
    (e.g. {"metric": "revenue"}) isn't detected -- see TODO.md's
    "Semantic-layer provenance checking".
    """
    queried, unparsed = queried_sources(sql_statements or [])
    expected = [_expected(entry, expected_database, expected_schema) for entry in expected_sources or []]
    if not expected:
        return Provenance(1.0, queried, unparsed)
    hits = sum(1 for want in expected if any(_matches(got, want) for got in queried))
    return Provenance(hits / len(expected), queried, unparsed)
