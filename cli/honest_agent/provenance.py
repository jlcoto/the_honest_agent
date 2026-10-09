"""Scores provenance: did the SQL the agent ran read the sources an eval
expects (e.g. an aggregated mart or a semantic view, not raw tables the
agent stitched together by hand)?

The SQL is parsed with sqlglot rather than searched as text, so only real
table references count: not a name in a comment, a string, a column or a
CTE the query defines itself. Each reference comes with its database and
schema, as written, as set by earlier `use database`/`use schema`
statements, or else the session's defaults when the target declares them
(`default_database`/`default_schema`). That's also what the report shows as
"what the agent queried".

Only statements that read data (`select`, including `with ... select` and
`union`) count. `describe`, `show` and the like are exploration: an agent
that describes the right table but queries another one hasn't used it. The
same goes for a `select` on a system catalog (`information_schema`,
`pg_catalog`, DuckDB's `duckdb_*` views, Snowflake's `snowflake` database):
it reads metadata, not data an answer comes from, unless the eval expects one.
The caller (see cli.py) leaves out calls that returned an error, since a
query that failed read nothing, and SQL a tool generated in its response
(e.g. Cortex Analyst's `statement`), since generating SQL isn't running it:
the agent has to run it itself for it to count.
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


# Where warehouses keep metadata about their own tables. Reading these is exploration.
_SYSTEM_SCHEMAS = {"information_schema", "pg_catalog"}
# Snowflake's own database: account metadata (account_usage, organization_usage, ...).
_SYSTEM_DATABASES = {"snowflake"}
# DuckDB's internal views, readable by bare name (`select * from duckdb_tables`). The
# `duckdb_tables()` function form is no table reference, so it never counts anyway.
_DUCKDB_CATALOG_VIEWS = {
    *("duckdb_columns", "duckdb_constraints", "duckdb_databases", "duckdb_indexes", "duckdb_logs"),
    *("duckdb_schemas", "duckdb_tables", "duckdb_types", "duckdb_views", "pragma_database_list"),
    *("sqlite_master", "sqlite_schema", "sqlite_temp_master", "sqlite_temp_schema"),
    *("pg_am", "pg_attrdef", "pg_attribute", "pg_class", "pg_collation", "pg_constraint"),
    *("pg_database", "pg_depend", "pg_description", "pg_enum", "pg_index", "pg_indexes"),
    *("pg_namespace", "pg_prepared_statements", "pg_proc", "pg_sequence", "pg_sequences"),
    *("pg_settings", "pg_tables", "pg_tablespace", "pg_type", "pg_views"),
}


def _is_system_catalog(database: str | None, schema: str | None, name: str) -> bool:
    """Whether a table reference, as written, names a system catalog."""
    if (schema or "").lower() in _SYSTEM_SCHEMAS or (database or "").lower() in _SYSTEM_DATABASES:
        return True
    return not database and not schema and name.lower() in _DUCKDB_CATALOG_VIEWS


class Source(NamedTuple):
    """A table, view or semantic view. `database`/`schema` are None when
    neither the SQL nor an earlier `use` statement said which."""

    database: str | None
    schema: str | None
    name: str


class Provenance(NamedTuple):
    # None when the eval expects no sources: nothing was checked, which isn't a pass.
    score: float | None
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


def _sources_read(
    statement: exp.Query,
    database: str | None,
    schema: str | None,
    defaults: tuple[str | None, str | None],
    include_catalogs: bool,
) -> list[Source]:
    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    default_database, default_schema = defaults
    sources = []
    for table in statement.find_all(exp.Table):
        if not table.name:
            continue  # a table function, e.g. semantic_view(...) itself
        if not table.catalog and not table.db and table.name.lower() in cte_names:
            continue
        if not include_catalogs and _is_system_catalog(table.catalog, table.db, table.name):
            continue
        if not table.catalog and _names_default_database(table.db, default_database, default_schema):
            # DuckDB reads `warehouse.orders` as database.table when there's no schema
            # `warehouse`: the database's default schema.
            sources.append(Source(table.db, default_schema, table.name))
            continue
        # A single qualifier (`x.table`) is the schema, as warehouses read it.
        sources.append(Source(table.catalog or database, table.db or schema, table.name))
    return sources


def _names_default_database(qualifier: str, default_database: str | None, default_schema: str | None) -> bool:
    """Whether a single qualifier (`x` in `x.table`) is the declared default database rather
    than a schema: it equals `default_database` and isn't also the declared schema."""
    if not qualifier or not default_database or qualifier.lower() != default_database.lower():
        return False
    return default_schema is None or qualifier.lower() != default_schema.lower()


def queried_sources(
    sql_statements: list[str],
    default_database: str | None = None,
    default_schema: str | None = None,
    include_catalogs: bool = False,
) -> tuple[list[Source], list[str]]:
    """Walks the SQL in the order it ran, tracking `use` statements as session
    state (they carry across tool calls), and returns the sources every read
    statement referenced, plus the SQL that couldn't be parsed. The session
    starts in the declared defaults, if any: where a bare table name runs when
    the SQL doesn't say. System catalogs are left out unless `include_catalogs`."""
    database: str | None = default_database
    schema: str | None = default_schema
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
                defaults = (default_database, default_schema)
                for source in _sources_read(statement, database, schema, defaults, include_catalogs):
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
    default_database: str | None = None,
    default_schema: str | None = None,
) -> Provenance:
    """Recall over `expected_sources`: the share of them some read statement
    referenced, in the expected database/schema where one is given. An eval
    with no `expected_sources` isn't checked: its score is None, not 1.0, so
    "not checked" never looks like "passed". The sources read are still
    returned, as a record of what the agent queried.

    An entry can carry its own location (`snowflake_sample_data.tpch_sf1.customer`,
    `staging.customer_flags`); `expected_database`/`expected_schema` apply to
    the parts an entry leaves out. Without either, any database/schema counts.
    A reference whose database or schema is unknown (a bare name with no
    earlier `use` and no declared default) doesn't match an expected one.
    `default_database`/`default_schema` are the session's defaults as the
    target declares them; they must match the server's connection, since a
    wrong one attributes tables to the wrong place without any warning.

    Caveat: this only sees SQL captured by sql_capture.py. An agent that
    reaches a semantic layer through structured, non-SQL tool arguments
    (e.g. {"metric": "revenue"}) isn't detected -- see TODO.md's
    "Semantic-layer provenance checking".
    """
    expected = [_expected(entry, expected_database, expected_schema) for entry in expected_sources or []]
    # An eval about the metadata itself ("how many tables are there?") expects a catalog.
    include_catalogs = any(_is_system_catalog(*source) for source in expected)
    queried, unparsed = queried_sources(sql_statements or [], default_database, default_schema, include_catalogs)
    if not expected:
        return Provenance(None, queried, unparsed)
    hits = sum(1 for want in expected if any(_matches(got, want) for got in queried))
    return Provenance(hits / len(expected), queried, unparsed)
