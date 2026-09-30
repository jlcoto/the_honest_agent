# Deferred work

Things intentionally not built yet, parked here so they don't get lost. Not a
backlog of everything imaginable -- only real, discussed decisions that are
waiting on information we don't have yet.

## Semantic-layer provenance checking

Today, `agent_quiz` can only verify provenance (`expected_sources`) by
inspecting SQL text captured from tool calls (see
`cli/agent_quiz_cli/sql_capture.py`, `cli/agent_quiz_cli/provenance.py`). That
only works when a tool call actually contains a SQL string somewhere in its
input.

Some semantic-layer tools instead take fully structured, non-SQL arguments --
e.g. `{"metric": "revenue", "grain": "daily"}` for something like a MetricFlow
(dbt Semantic Layer) style tool, or `{"measures": [...], "dimensions": [...]}`
for Cube -- with no SQL string anywhere in the call. Whether a given tool is
SQL-shaped or structured-shaped depends entirely on how that specific tool was
built, not on which semantic layer it wraps: the same underlying semantic
layer (e.g. Snowflake Cortex Analyst) can be exposed either way depending on
the integration.

For that structured case, source-checking needs a parallel path (currently
only `type="sql"` rows exist in the `tool_calls` table -- see `storage.py` --
the schema already anticipates a future `type="semantic"`). Building it needs
two separate config surfaces, both necessarily declared per-deployment since
they describe someone else's tool contract, not ours:

1. **Which tool names are semantic-layer calls** -- so their whole structured
   input gets captured as a payload instead of agent_quiz looking for a "sql"
   field that doesn't exist. Likely shape: a `provenance.semantic_tools` list
   in the quiz YAML, alongside the existing `sql_fields`.
2. **Which field inside that structured input names the model/metric being
   hit** -- so `score_provenance`'s source-checking has something to compare
   `expected_sources` against. This varies by vendor (MetricFlow's
   `metrics`/`group_by` vs. Cube's `measures`/`dimensions`), so it can't be
   hardcoded.

**Design constraint for when this gets built: no per-vendor "used the
semantic layer" boolean.** The temptation once a second/third provider is in
scope is to add a dedicated flag (e.g. `used_semantic_view`) to `results` so
it's easy to see whether the semantic layer actually got used. Don't --
`expected_sources` + `provenance_score` already answer that generically for
any SQL-producing semantic layer (a named view/model that shows up in
captured SQL, e.g. Snowflake's `tpch_semantic_view`), and once `type="semantic"`
exists, the *same* recall mechanism should extend to structured payloads too
(matching `expected_sources` against the declared model/metric field) rather
than a separate flag per vendor. Keeping "is the semantic layer working" as a
recall score against `expected_sources` -- not a boolean -- is what lets one
mechanism cover every provider, SQL-shaped or structured-shaped, without the
column list growing one flag per vendor integrated.

**Not worth building speculatively.** Do this once a real semantic-layer tool
and its actual schema are in scope -- right now there's nothing concrete to
design against.

**Candidates to extend quiz coverage to, once picked up:** SLayer
(https://github.com/MotleyAI/slayer) and the dbt Semantic Layer (MetricFlow).
Neither has been wired into `example_project` yet -- this is a pointer for
future work, not a confirmed schema to design against.

- **SLayer**: not the fully-structured-only case described above -- it
  actually generates real SQL under the hood, so `type="sql"` capture may
  already mostly work. But its `query` tool only includes the generated SQL
  in the response when the caller passes `show_sql=true` (opt-in per call,
  not guaranteed to happen unless the quiz prompt or tool description nudges
  the agent to ask for it), and the exact response field name holding that
  SQL isn't documented -- needs confirming against a real response before
  assuming the existing `sql`/`query`/`statement` heuristic (or a
  `sql_fields` override) actually catches it.
- **dbt Semantic Layer / MetricFlow**: expected to be the fully-structured
  case this section was written for (`metrics`/`group_by` args, no SQL
  string) -- not yet verified against a real MCP tool schema.

## Migrate S3 export from plain Parquet to DuckLake

`agent-quiz export` (`storage.py`'s `export_to_s3_parquet`) currently writes a
plain Parquet snapshot to S3 via `COPY (...) TO 's3://...' (FORMAT PARQUET)`.
The plan, discussed and spiked but never implemented, is to write a
**DuckLake** table instead (Parquet data files + a small catalog) so the
export becomes directly queryable by DuckDB-WASM in the browser -- the
foundation for an eventual interactive HTML report (`agent-quiz report`
running live SQL client-side against S3 data, instead of today's static
pre-rendered tables).

A throwaway spike already confirmed this is technically feasible: DuckDB-WASM
(`@duckdb/duckdb-wasm@1.32.0`+, bundling DuckDB core v1.4.3+) can genuinely
`ATTACH` a DuckLake catalog served over plain HTTP and run real queries
against it. Three real gotchas the spike surfaced, which the actual
implementation needs to account for:

1. **Storage-version coupling.** The catalog is a DuckDB-format file, versioned
   to whatever DuckDB wrote it. A catalog written by a newer `duckdb` (the
   CLI's own pinned version) can fail to open under an older bundled
   `duckdb-wasm` version ("database file with version number X, but we can
   only read versions between Y and Z"). The CLI's `duckdb` version and the
   report's pinned `duckdb-wasm` version need to be kept deliberately
   compatible, not an afterthought.
2. **`DATA_PATH` is baked into the catalog at creation time.** Either write
   the catalog with its final S3 URL as `DATA_PATH` from the start, or always
   `ATTACH` with `OVERRIDE_DATA_PATH true` from the report page.
3. **CORS + HTTP Range support are both required** on whatever serves the
   catalog/Parquet files. Plain `python -m http.server` fails silently here
   (returns 200 instead of 206, ignoring Range) -- real S3 hosting needs CORS
   configured, and any local-dev serving needs a real range-aware server.

Not yet spiked: a real S3 bucket (only local-HTTP was tested, with CORS/range
headers set explicitly to simulate it) and concurrent-writer DuckLake catalog
behavior.

**Sequencing:** this becomes relevant once frontend/report work starts --
no reason to migrate the export format before there's an actual consumer
(the interactive report) that needs DuckLake instead of plain Parquet.
