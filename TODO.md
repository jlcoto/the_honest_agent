# Deferred work

Things intentionally not built yet, parked here so they don't get lost. Not a
backlog of everything imaginable -- only real, discussed decisions that are
waiting on information we don't have yet.

## High priority: security fixes (review of 2026-10-02)

Found by a security review of the CLI. No command injection, SQL injection,
unsafe YAML loading or XSS was found; these are trust-boundary issues.

Fix first:

1. **Every secret is passed to stdio MCP servers.** `mcp_agent_runner.py`
   builds the server process with `env=dict(os.environ)`, after `.env` has
   been loaded, so a third-party server (e.g. the unpinned
   `uvx mcp-server-motherduck` the docs recommend, resolved fresh each run)
   receives ANTHROPIC_API_KEY, OPENAI_API_KEY, AWS_*, SLACK_WEBHOOK_URL and
   MCP_BEARER_TOKEN. Pass the SDK's default environment plus variables the
   user names (e.g. `--mcp-env MOTHERDUCK_TOKEN`), and pin versions in the
   docs (`uvx mcp-server-motherduck==X.Y.Z`).
2. **`report --out` can delete files.** `report.py` runs
   `shutil.rmtree(out_dir / "assets", ignore_errors=True)` and overwrites
   `index.html` in whatever folder `--out` names (`--out .`, `--out docs`).
   Only clean folders honest-agent created, marked with a file it writes on
   first run; refuse non-empty unmarked folders.
3. **Prompt injection can change `llm_judge` scores.** `grading.py` pastes
   the agent's answer unescaped into the judge prompt and reads the score
   with a greedy `\{.*\}`, so warehouse text can make an answer contain
   `{"score": 1.0}`. Wrap the answer in tags and tell the judge it's data,
   use structured output instead of the regex, and recommend
   `--judge-model` in the docs. (`extract_match` is less exposed: its final
   comparison is done in code.)

Lower severity:

4. **`serve`** has no Host-header check (DNS rebinding can read
   `report.json`) and lists directories; `serve --out .` would expose
   `.env`. Check Host, disable listings, refuse folders without the report
   marker from item 2.
5. **`honest-agent logs`** prints `agent_answer` and tool payloads raw, so
   model/tool output can inject terminal escape sequences (OSC 52 clipboard
   writes, disguised links). Strip control characters before printing.
6. **CSV export** (`ui/src/data/derive.ts` `toCsv`) doesn't neutralise
   cells starting with `= + - @`, so an answer can run as a spreadsheet
   formula. Prefix those cells with `'`.
7. **Slack:** `notify.py` puts eval ids into the message unescaped, so a
   eval file can trigger `<!channel>` or disguise a link. Escape `< > &`.

## High priority: cleanup (review of 2026-10-02)

From a refactoring review; tests and lint were clean. All small unless noted.

- **Dead code:** `agent_backend` (always `"mcp"`, read by nothing; drop from
  `cli.py`, `storage.py`, `ui/src/data/types.ts`, tests). Grader and agent
  functions still default `model="claude-haiku-4-5-20251001"` and treat the
  judge as optional although `cli.py` always passes both; make them
  required and drop the dead branches. `storage.read_tool_calls(result_id=)`
  is used only by tests.
- **Stale docs and comments:** Claude-only wording in now provider-neutral
  code (`agent_runner.py` docstrings, `--max-tool-turns` help, `storage.py`
  token comment, `mcp_agent_runner.py` "MCP backend selected"); references
  to removed things (the eval YAML `tools:` key in `sql_capture.py`, the
  dbt `schema.yml` in `eval_loader.py`, the old `exact` method and a missing
  "module-level note" in `grading.py`, a memory file in `provenance.py`);
  `read_agent_logs` claims to return extracted SQL. The semantic-layer
  explanation is repeated four times; keep it in one place.
- **CLAUDE.md lowercase-SQL rule:** column types in `storage.py` and SQL in
  `test_provenance.py` / `test_sql_capture.py` are uppercase (keep
  `FCT_ORDERS` in `test_provenance.py`, which tests case-insensitivity).
- **Docs drift:** root `README.md` still says "static HTML report" and
  Claude-only.
- **Duplication:** failure-line formatting in `cli.py` and `notify.py`
  (move a `describe_failure` into `thresholds.py`); the turn-limit message
  and tool-result text join copied between the two agent runners (share in
  `agent_runner.py`; keep the loops separate); identical `_row()` test
  helpers in `test_cli.py` / `test_storage.py`; UI score bands hard-coded
  in `Overview.tsx` and `derive.ts` instead of `bucketOf`/`pct` from
  `ui/src/ds/components/data/scale.js`; `METRICS` and the empty-state card
  duplicated in `Overview.tsx` / `Compare.tsx`.
- **Fragile tests:** `_run_async` takes 11 positional arguments and tests
  read them by index (`a[4]`, `a[-1]`), so a reorder breaks them silently.
  Call it with keywords and share the fake-run helper in `tests/conftest.py`.
  While there, replace click's `CliRunner().isolated_filesystem()` (deprecated,
  removed in Click 9; tests now emit DeprecationWarnings) with `tmp_path`.
- **Naming (medium):** `mcp_agent_runner.MCPAgentClient` is the Claude one,
  next to `OpenAIMCPAgentClient`; rename to `anthropic_agent_runner` /
  `AnthropicMCPAgentClient`.

## Semantic-layer provenance checking

Today, `honest-agent` can only verify provenance (`expected_sources`) by
inspecting SQL text captured from tool calls (see
`cli/honest_agent/sql_capture.py`, `cli/honest_agent/provenance.py`). That
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
   input gets captured as a payload instead of honest-agent looking for a "sql"
   field that doesn't exist. Likely shape: a `provenance.semantic_tools` list
   in the eval YAML, alongside the existing `sql_fields`.
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

**Candidates to extend eval coverage to, once picked up:** SLayer
(https://github.com/MotleyAI/slayer) and the dbt Semantic Layer (MetricFlow).
Neither has been wired into `example_project` yet -- this is a pointer for
future work, not a confirmed schema to design against.

- **SLayer**: not the fully-structured-only case described above -- it
  actually generates real SQL under the hood, so `type="sql"` capture may
  already mostly work. But its `query` tool only includes the generated SQL
  in the response when the caller passes `show_sql=true` (opt-in per call,
  not guaranteed to happen unless the eval prompt or tool description nudges
  the agent to ask for it), and the exact response field name holding that
  SQL isn't documented -- needs confirming against a real response before
  assuming the existing `sql`/`query`/`statement` heuristic (or a
  `sql_fields` override) actually catches it.
- **dbt Semantic Layer / MetricFlow**: expected to be the fully-structured
  case this section was written for (`metrics`/`group_by` args, no SQL
  string) -- not yet verified against a real MCP tool schema.

## Migrate S3 export from plain Parquet to DuckLake

`honest-agent export` (`storage.py`'s `export_to_s3_parquet`) currently writes a
plain Parquet snapshot to S3 via `COPY (...) TO 's3://...' (FORMAT PARQUET)`.
The plan, discussed and spiked but never implemented, is to write a
**DuckLake** table instead (Parquet data files + a small catalog) so the
export becomes directly queryable by DuckDB-WASM in the browser -- the
foundation for an eventual interactive HTML report (`honest-agent report`
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

**Sequencing:** only relevant if the report frontend's query box goes with
DuckDB-WASM (option B in "Report frontend: querying and sharing" below). The
frontend itself is being built on JSON, not WASM, so there's no consumer for
DuckLake yet.

## Report frontend: querying and sharing

The report frontend (a React app in `ui/`, built output shipped inside the
Python package, like Inspect AI's log viewer) is being built first with
**pre-built views only**. `honest-agent report` writes the data as JSON files
and the React app reads them through one data-access module. No DuckDB runs in
the browser.

Deferred: a **query box** where users run their own SQL against `results`,
`agent_logs`, and `tool_calls`. Two ways to build it, and the choice depends
on one question: do reports need to be hosted/shared as static files (S3,
GitHub Pages, a shared folder) with querying still working, or only viewed
locally through `honest-agent serve`?

- **A. `honest-agent serve` runs the queries (local viewing only).** Add a
  `/api/query` endpoint to `serve` that runs SQL through Python's DuckDB on a
  read-only connection and returns rows as JSON. No engine download, works
  offline, and the file is always read by the same DuckDB version that wrote
  it. Needs: bind to 127.0.0.1 only, and `set enable_external_access = false`
  so a query can't read or write other files on disk (read-only mode alone
  doesn't block `copy ... to` or `read_csv('/any/path')`). Querying only works
  while `serve` is running.
- **B. DuckDB-WASM in the browser (static hosting).** The report stays pure
  static files and querying still works with no Python process. Costs:
  - The engine is one ~34 MB `.wasm` file (~8 MB compressed; only the `eh`
    variant is needed for current browsers) plus a ~0.7 MB worker. Either
    load it from jsDelivr at runtime, pinned to an exact version (small
    package, but needs internet), or ship it with the package (works
    offline; build it in CI rather than committing it, or every DuckDB-WASM
    upgrade adds ~34 MB to git history).
  - The storage-version coupling and Range/CORS issues from the DuckLake
    spike above apply here too: the bundled `duckdb-wasm` must be able to
    read files written by the CLI's `duckdb`, and plain `http.server`
    ignores Range requests.
  - DuckDB-WASM downloads some extensions from `extensions.duckdb.org` when
    a query first needs them. Check which ones queries actually hit before
    assuming it works offline.

Either way, only the data-access module should change. The views shouldn't
need to know whether rows came from JSON, the `serve` API, or WASM.

### Sharing reports

Two ways to share, snapshot vs. live:

1. **Snapshot (the default, being built now).** `honest-agent report` bakes
   the data into JSON at generation time. View it locally with `honest-agent
   serve`, or upload the folder as-is to any static host (S3 website
   hosting, GitHub Pages, an internal host). Showing new runs means
   regenerating and re-uploading, typically a CI step after each eval run.
2. **Live (later, opt-in).** Host the UI once. `honest-agent export` keeps
   pushing data to S3 (Parquet/DuckLake, see the section above), and the
   UI queries the latest data with DuckDB-WASM whenever it's opened. The
   query box comes with it. Needs: option B above, CORS/Range on the
   bucket, and `export` including `agent_logs`/`tool_calls` (today it
   exports `results` only, so live reports would have no traces or SQL).

Worth adding to the snapshot mode: a **single-file** output (data inlined
into `index.html`, like dbt's `docs generate --static`) so a report can be
shared as one attachment or one presigned S3 link. Presigned URLs are
per-object, so a multi-file folder doesn't work well with them.

**Access control is the user's decision, not honest-agent's.** Where reports
are hosted, which login sits in front of them, and who gets access depend on
each team's own infrastructure and policies, so honest-agent leaves it to
them. It also can't enforce access itself: anyone who can download the files
can read everything in them, so a password check in the report's JavaScript
would be fake. Don't build one. Our only job here is documentation: a
"Sharing reports" section in the README laying out the options below so
users can pick what fits their setup.

- **Snapshot:** only the report files need protecting. Keep the bucket
  private and serve it through CloudFront with signed cookies or SSO/OIDC at
  the edge (Cognito, Okta), or behind an existing auth proxy (an AWS load
  balancer with OIDC, Cloudflare Access, Google IAP, oauth2-proxy). Or share
  the single-file report through a channel that already has access control
  (Slack, Drive). Access is all-or-nothing, and downloaded copies can't be
  revoked.
- **Live:** the browser fetches Parquet from S3 directly, so the data needs
  protecting too, not just the UI. Simplest: serve the data through the same
  CloudFront distribution and auth as the UI. It's same-origin, which also
  avoids CORS, and CloudFront passes Range requests through. Alternatives
  (per-viewer temporary AWS credentials in the browser via a Cognito
  identity pool, or a backend that presigns each file) are more complex,
  and a presigning backend defeats the no-server point. Revoking access
  takes effect immediately, since no copy of the data is left behind.

## Move `sql_fields` into the config file's targets

Which tool argument holds SQL is a fact about the MCP server, not about an eval,
so `provenance.sql_fields` belongs with the target in
`honest_agent_config.yml` (next to `ignore_tools`), not in each eval file. Left
in the evals for now: no current server needs it, since honest-agent finds
`sql`/`query`/`statement` arguments by itself. Move it when a real server does.

## `honest-agent init`: starter files for a new project

Found during the first-time setup dry runs (2026-10-02): after `uv add`, a
new user starts from an empty folder and has to write
`honest_agent_config.yml` and a first eval from the docs. Copying the
example project's config instead breaks straight away (its `demo` target
needs a server that isn't there).

Package installers can't create files after installing, so this needs a
command, like `dbt init`:

- Creates `honest_agent_config.yml` (one commented target for the chosen
  server), `evals/example_eval.yml` (a commented example) and `.env` (the
  variable names it needs, empty values).
- Asks which MCP server (Snowflake, MotherDuck, local command, other URL),
  its URL or command, and a target name, with defaults. `--no-input` writes
  the template without asking.
- Never overwrites an existing file (skips it and says so), and never edits
  `.gitignore`: in a git repository where `.env` isn't ignored, it prints a
  warning with the line to add.
- The example eval has marked placeholders, since honest-agent can't know a
  user's tables. Exception: every MotherDuck account has a `sample_data`
  database, so the MotherDuck template could ship an eval that passes out of
  the box (pick the question and verify its answer first).
- "Getting started" in README.md then shrinks to install, `init`, fill in
  `.env`, run.

Open question for the user: prompts like `dbt init`, or flags only.
