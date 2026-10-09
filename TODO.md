# Deferred work

Things intentionally not built yet, parked here so they don't get lost. Not a
backlog of everything imaginable -- only real, discussed decisions that are
waiting on information we don't have yet.

## Next: structured output for grading

Found on 2026-10-09 while trying the `init --example` evals with Claude Haiku:
an `llm_judge` reply came back as `{"score": 0.0, "rationale": "...instead).""}`
(a stray quote), and the whole `run` stopped with a JSONDecodeError. The
grading prompts only *ask* for JSON, and `grading.py` (`_reply_json`) grabs
`\{.*\}` with a regex and `json.loads` it.

Stopgap since then: a reply that can't be read scores that eval 0, with
"Not graded: the grading model's reply wasn't the JSON it was asked for (...)"
as its rationale and a warning in the output; the run continues.

The fix: **structured output**, so the model API constrains the reply to a
schema and invalid JSON can't happen.

- Claude: tool use with one forced tool whose input schema is the reply
  (`{"score": number, "rationale": string}` for `llm_judge`,
  `{"extracted_answer": string}` for `extract_match`), or the API's
  structured-output option if the models we use support it. OpenAI:
  `response_format` with a JSON schema.
- Both judges, Claude and OpenAI; keep the stopgap for anything that still
  fails (a refusal, a cut-off reply).
- Check that grades don't shift: re-grade the example project's stored runs
  with `honest-agent rebuild` before and after and compare.
- Closes the open half of security item 3 below.

## Next: declared session defaults for provenance

Found on 2026-10-09 while trying the `init --example` evals: provenance learns a
table's database and schema only from the SQL (`db.schema.table`, or an earlier
`use`). A bare `from orders` runs in the connection's default database and
schema, which the SQL doesn't show, so its location is "unknown" and never
matches `expected_database`/`expected_schema`. In the DuckDB demo nobody
qualifies names, so a location check can never pass there. Not DuckDB-only:
any server whose connection has a default (Snowflake, MotherDuck) has the same
gap.

Decided: a target can declare the session's defaults, both optional:

```yaml
targets:
  demo:
    default_database: warehouse
    default_schema: main
```

- The SQL always wins: a default only fills in the part a name leaves out.
- Store the defaults with each run's settings (like `ignore_tools`), so
  `rebuild` reproduces past provenance even if the config changes later.
- `init --example` fills them in for the demo.
- **DuckDB two-part names:** DuckDB reads `a.b` as schema.table, and if there
  is no schema `a`, as database.table (`warehouse.orders` works in the demo).
  honest-agent's parser always reads it as schema.table, so `warehouse.orders`
  is recorded with schema `warehouse`. Rule: when a two-part name's first part
  equals the declared `default_database` and not `default_schema`, read it as
  database.table. Still a guess when a schema and a database share a name.
- Document: a wrong declared default fails silently (the real risk); with a
  server that opens a new connection per call (the demo does), a `use` doesn't
  carry over between calls on the server, though provenance assumes it does;
  with a search path of several schemas, the default is the first.
- Later, opt-in: detect the defaults by running `select current_database(),
  current_schema()` through the agent's SQL tool (not every dialect has them).

## From the first-time setup walkthrough (2026-10-08)

The user installed honest-agent from scratch in an empty folder, following
only the README, then set up hosting and CI (recipe: `docs/hosting.md`).
README fixes done 2026-10-08 (example eval, `--target`, sharing via
`docs/hosting.md`, `export` auth); `init` built 2026-10-09. Left:

1. **`honest-agent run` always exits 0**, even when evals fall below
   threshold, so a CI job never fails on a regression (only `notify`
   alerts). Decide whether to add an option that sets a failing exit code.
2. **Ship the AWS setup as code**, after the recipe settles: a
   CloudFormation template with a "Launch stack" link (bucket, minimal
   policy, GitHub OIDC role), a Terraform module when a team asks. It must
   cope with an existing GitHub OIDC provider (one per account).
3. **Turn the tested recipe into a Claude Code skill** that asks for
   storage, host, CI and warehouse and generates the workflow, config and
   commands, pointing to `docs/hosting.md`. Never asks for tokens in chat,
   never suggests public hosting, confirms before creating resources.

## First tester release (v0.1.0): versions and migrations

Discussed 2026-10-07. The repo is already public and `cli/pyproject.toml` says
0.1.0, but there are no tags or changelog, and old results files are updated
by hand. Once testers have real history, that has to change. Do all of this
when tagging v0.1.0, not before.

**Releases:**

- Call it **alpha**: an "Alpha: expect breaking changes between versions"
  notice at the top of the README. Not beta: storage and the report format
  are still changing.
- **0.x semantic versions**: the minor version (0.1 -> 0.2) for breaking
  changes, the patch version for fixes. No `0.1.0a1`-style suffix: pip and uv
  skip pre-releases without `--pre`, which only adds friction for testers.
  1.0 is when results files are promised to keep working.
- An annotated **git tag** per release (`git tag -a v0.1.0`) and a **GitHub
  Release** with short notes, breaking changes first. Testers install the tag:
  `uv tool install "git+https://github.com/jlcoto/the_honest_agent@v0.1.0#subdirectory=cli"`.
- A short **`CHANGELOG.md`**.
- Later, **PyPI** via trusted publishing from a tag workflow (no stored
  token). Check that `honest-agent` is free on PyPI before announcing.

**Migrations (no Alembic):**

- A `meta` table with `schema_version`, starting at 1 = the schema at release.
- An ordered list of small Python migration functions (a few lowercase SQL
  statements each), applied when the CLI opens a results store, each in a
  transaction. Back up a local file first (`results.duckdb.bak-v<N>`).
- Refuse a store whose version is newer than the CLI knows ("written by a
  newer honest-agent; upgrade"), so an old CLI can't corrupt it.
- What needs a migration:

  | Change | Needed |
  |---|---|
  | New column in a derived table | Nothing (`_ensure_schema` adds it) |
  | Different scoring or derivation | Nothing; release notes say to run `rebuild` |
  | Rename or removal in a derived table | Recreate it, then `rebuild` |
  | Any change to the raw layer | A numbered migration: it can't be regenerated |
  | Report format | Nothing; `report` regenerates it |

- Fix the gap first: `_ensure_schema` adds missing columns to `results` and
  `tool_calls` but not to `traces`.
- `honest_agent_config.yml` and eval YAML: a renamed key keeps working under
  its old name for one minor version, with a warning, then goes.
- Keep a `duckdb` version range in `pyproject.toml`: a newer DuckDB can write
  files an older one can't read. Mention DuckDB upgrades in release notes.

## High priority: security fixes (review of 2026-10-02)

Found by a security review of the CLI. No command injection, SQL injection,
unsafe YAML loading or XSS was found; these are trust-boundary issues.

Items 1 and 2 were fixed on 2026-10-03: local MCP servers get only the
variables in their target's `mcp_env`, and `report` only writes into a new or
empty folder or one it wrote before (`.honest_agent_report` marker).

Lower severity:

3. **Prompt injection can change `llm_judge` scores.** Half fixed on
   2026-10-03: the agent's answer now goes into the judge and extraction
   prompts inside `<answer>` tags, with a note that it's data, not
   instructions. Still open: `grading.py` reads the judge's score with a
   greedy `\{.*\}` regex; use structured output instead: now planned in
   "Next: structured output for grading" above. Low priority unless an
   agent answers from free text written by outsiders (support tickets,
   reviews, CRM notes); `extract_match` compares in code and is less exposed.
4. **`serve`** has no Host-header check (DNS rebinding can read
   `report.json`) and lists directories; `serve --out .` would expose
   `.env`. Check Host, disable listings, refuse folders without the report
   marker (`.honest_agent_report`, see `report.py`).
5. **`honest-agent logs`** prints `agent_answer` and tool payloads raw, so
   model/tool output can inject terminal escape sequences (OSC 52 clipboard
   writes, disguised links). Strip control characters before printing.

## Cleanup (review of 2026-10-02)

Done on 2026-10-03: `_run_async` takes named arguments and tests share one
fake-run fixture (`tests/conftest.py`); tests use `tmp_path` instead of the
deprecated `isolated_filesystem`; SQL is lowercase per CLAUDE.md; the root
README no longer says "static HTML report" or Claude-only.

Left on purpose, low value for now (small, rarely-changing code):

- **Dead code:** `agent_backend` (always `"mcp"`, read by nothing; drop from
  `cli.py`, `storage.py`, `ui/src/data/types.ts`, tests, and the column in
  existing results files by hand). Grader and agent functions still default
  `model="claude-haiku-4-5"` and treat the judge as optional
  although `cli.py` always passes both. `storage.read_tool_calls(result_id=)`
  is used only by tests.
- **Stale comments:** Claude-only wording in provider-neutral code
  (`agent_runner.py` docstrings, `--max-tool-turns` help, `storage.py` token
  comment, `mcp_agent_runner.py` "MCP backend selected"); references to
  removed things (the eval YAML `tools:` key in `sql_capture.py`, the dbt
  `schema.yml` in `eval_loader.py`, the old `exact` method in `grading.py`);
  `read_agent_logs` claims to return
  extracted SQL. The semantic-layer explanation is repeated four times.
- **Duplication:** failure-line formatting in `cli.py` and `notify.py`; the
  turn-limit message and tool-result text join in the two agent runners;
  `_row()` test helpers in `test_cli.py` / `test_storage.py`; UI score bands
  in `Overview.tsx` and `derive.ts` instead of `bucketOf`/`pct` from
  `ui/src/ds/components/data/scale.js`; `METRICS` and the empty-state card
  in `Overview.tsx` / `Compare.tsx`.

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
   hit** -- so `check_provenance`'s source-checking has something to compare
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

## Provenance: open scoring questions

Provenance moved to parsed SQL on 2026-10-06 (`provenance.py`, sqlglot): only
`select` statements count, errored calls don't, and `expected_sources`
entries can carry their own database/schema. Three questions came up and were
left open on purpose:

1. **Acceptable alternatives.** `expected_sources` means *all* of them
   (recall). An eval can't say "the mart *or* the semantic view". In the
   Snowflake results, four answers that came from
   `agent_quiz_demo.public.tpch_semantic_view` scored 0 because the evals
   expect `fct_revenue_by_year` / `orders`. Decide whether the semantic view
   is an acceptable source there (then list it, or add an any-of form to the
   YAML) or a real miss.
2. **Extra sources.** Recall ignores tables the agent read beyond the
   expected ones, so joining the right mart with
   `snowflake_sample_data.tpch_sf1.customer` still scores 1.0. The report can
   show the extra ones; whether they should lower the score is undecided.
3. **Default database.** A bare table name with no `use` statement has an
   unknown location and never matches an expected database/schema. Right for
   Snowflake's MCP server, which has no default database (bare names fail to
   compile there). A warehouse whose connection does have one would score
   correct queries as misses; if that comes up, let a target declare its
   default database/schema.

## Result page: SQL calls and Trace cards

These need a frontend pass (seen 2026-10-06, kept apart from the storage work
on purpose). The raw record (`raw.events`, see `honest-agent logs`) now also
holds each call's `stop_reason`, usage and timing, and full tool results, which
the cards could show (e.g. flag a turn cut off by `max_tokens`); report.json
doesn't carry it yet:
- thinking blocks show as raw JSON with a long signature and empty text
  (Claude returns them redacted);
- tool results are raw JSON dumps (Snowflake's `result_set` with all its
  column metadata); the actual values are hard to find;
- long results don't collapse: the 12-line limit counts newlines, and these
  are one wrapped line;
- a tool call and its result are separate numbered steps, not visibly paired;
  steps count messages, not the agent's actions;
- every query appears twice (SQL calls card and Trace), and the SQL calls card
  doesn't show what each call returned.

## DuckLake, if ever needed

`honest-agent export` (a Parquet snapshot of `results` to S3) was removed on
2026-10-08: nothing used it once hosting stored the whole results file
(`docs/hosting.md`). The earlier plan was to make it write a **DuckLake**
table instead (Parquet data files + a small catalog), queryable by
DuckDB-WASM in the browser -- the foundation for an interactive report
running live SQL client-side against S3 data, instead of today's static
pre-rendered tables. If that comes back, it would be a DuckLake results store
or export, not a revived Parquet snapshot.

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

**DuckLake is also the path for results in S3 (decided 2026-10-07).** Teams
keep results in a local file, MotherDuck (`results_path: md:<name>`), or a
file in a bucket that CI downloads and uploads around each job (no code; one
job at a time, or runs are silently lost). A homemade "per-run Parquet in S3
with views" store (the pattern from DuckDB's view-only catalog post,
https://duckdb.org/2026/10/07/view-only-mode) was considered and rejected:
it fixes the download and overlapping-job problems, but adds a third store to
maintain, makes raw-layer migrations rewrite every old file, and needs its own
"run complete" markers and compaction. If teams need S3 without downloading,
move to DuckLake instead, which already solves those.

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
   serve`, or upload the folder as-is to a static host behind a sign-in
   (`docs/hosting.md`; never public). Showing new runs means regenerating
   and re-uploading, a CI step after each eval run.
2. **Live (later, opt-in).** Host the UI once, keep the data in S3 as
   DuckLake (see "DuckLake, if ever needed" above), and the UI queries the
   latest data with DuckDB-WASM whenever it's opened. The query box comes
   with it. Needs: option B above, CORS/Range on the bucket, and all three
   tables (results, traces, tool calls) in the lake.

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

## "Investigate in Claude Code" button on the result page

Discussed 2026-10-07, for later. A button on a failing result's page that
opens Claude Code with an investigation prompt already typed, through a
deep link: `claude-cli://open?repo=<owner/repo>&q=<prompt>`
(https://code.claude.com/docs/en/deep-links). Build the prompt from ids only
(eval id, target, run, and `honest-agent logs --run-id ... --eval-id ...`),
never from warehouse data. Not in the Slack alert (ruled out). Open: `repo`
vs `cwd`, and the person clicking needs that run's results locally. Claude
Tag (Claude in Slack) can't be started by the webhook, so that idea was
dropped.

## `honest-agent prune`: delete old records

`results.duckdb` keeps every run forever. That's a size issue in CI (the job
downloads and uploads the whole file each run) and, more importantly, a
retention issue: the raw layer, `traces` and `tool_calls` hold verbatim tool
output, possibly customer data, and many companies don't allow keeping that
indefinitely. Discussed 2026-10-07 with the hosting plan; not urgent, since
real data is ~7-8 KB per result (roughly 500 MB a year at 200 evals a day).

```bash
honest-agent prune --older-than 90d          # lists what it would delete
honest-agent prune --older-than 90d --yes    # deletes it
```

- **What it deletes.** By default the heavy, sensitive parts of old runs: the
  raw layer, `traces` and `tool_calls`. Their `results` rows stay, so scores
  remain for long-term trends in SQL. `--all` deletes whole runs, for strict
  retention.
- **Safety.** Without `--yes` it only lists. It never deletes a target's
  latest run, so `notify` and the report always have something. It refuses an
  age shorter than the report's window (30 days), so it can't empty the
  report.
- **Shrink the file.** Deleting rows doesn't make a DuckDB file smaller, so
  prune ends by copying into a fresh file (`copy from database`) and swapping
  it in, in one step so a crash can't leave a broken file. A fresh copy of the
  example project's 5.8 MB file came out at 3.3 MB.
- **In CI**, one line before the upload. No config key: the age lives where
  the job is defined.
- **Say in the output and docs** that `rebuild` and `logs` can't cover pruned
  runs, since their raw records are gone.

## Move `sql_fields` into the config file's targets

Which tool argument holds SQL is a fact about the MCP server, not about an eval,
so `provenance.sql_fields` belongs with the target in
`honest_agent_config.yml` (next to `ignore_tools`), not in each eval file. Left
in the evals for now: no current server needs it, since honest-agent finds
`sql`/`query`/`statement` arguments by itself. Move it when a real server does.

## `honest-agent init`: starter files for a new project

**Status (2026-10-09):** `env_var()` in the config and plain `init` are built
(decisions 1-8 below). Left: `init --example` (decision 9), which needs its 5-6
evals designed first.

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
  `.gitignore`: in a git repository where `.env` or `honest_agent_report/`
  isn't ignored, it prints a warning with the lines to add. (Since
  2026-10-08 the report folder holds only the website and no longer ignores
  itself, so the project's `.gitignore` must.)
- Since 2026-10-05 the bundled example commits `honest_agent_config.example.yml`
  and ignores the real file (like `.env.example`). `init` could offer the same
  split when the config names private account URLs.
- The example eval has marked placeholders, since honest-agent can't know a
  user's tables. Exception: every MotherDuck account has a `sample_data`
  database, so the MotherDuck template could ship an eval that passes out of
  the box (pick the question and verify its answer first).
- `init --example` (decided 2026-10-08): instead of setting up the user's
  own server, creates its own folder (e.g. `honest-agent-example/`) with a
  local example that passes out of the box: the demo MCP server and TPC-H
  seed from `example_project`, shipped inside the package, plus its passing
  evals. Its own folder so a demo target never ends up in a real project's
  config. Seeds with DuckDB's `tpch` extension on first run (the extension
  downloads once, so it needs the network; shipping sf=0.01 as Parquet,
  ~2.1 MB, is the fallback if offline seeding ever matters). Still needs a
  model API key, and passing still depends on the model.
- "Getting started" in README.md then shrinks to install, `init`, fill in
  `.env`, run.

**Decided 2026-10-09** (plan with the full discussion:
https://claude.ai/code/artifact/46742cb1-ce7b-4ad5-9255-0bbc9f36b6d0):

1. Prompts with numbered options and defaults (Enter accepts), free text only
   for the user's own values (URL, command); every answer is also a flag, and
   `--no-input` makes it scriptable.
2. Servers: local command (the default), Snowflake managed MCP, MotherDuck,
   another URL; Snowflake and MotherDuck prefill the URL shape and token
   variable.
3. Model: Claude (default) or OpenAI; only that key goes in `.env`.
4. Results: local file (default), MotherDuck (`results_path` +
   `HONEST_AGENT_RESULTS_TOKEN`, written under a "# MotherDuck only" comment;
   the name stays generic for other backends), or a file in S3 (prints the two
   `aws s3 cp` lines with a plain note that honest-agent won't copy to S3
   itself, and links `docs/hosting.md`).
5. Plain `init` always writes a placeholder eval; a passing MotherDuck
   `sample_data` eval belongs in `init --example`, if ever.
6. **Env vars in the config, dbt style:** any value can be
   `{{ env_var('VAR') }}`, with an optional default as the second argument.
   For every URL target, `init` writes the URL into `.env` and the config reads
   it, so accounts stay out of git with one committed file. A local command
   stays inline. Needs `env_var()` support in the config loader (a small
   pattern match, no Jinja).
7. `.gitignore`: print the lines to add, never edit it.
8. Target name: the server's name (`local`, `snowflake`, `motherduck`),
   changeable at the prompt; more targets (e.g. `snowflake_dev`) by hand.
9. `init --example`: its own folder, 5-6 evals on the demo warehouse, some
   failing on purpose, covering every accuracy method and every provenance
   check, on a cheap model (e.g. Claude Haiku); its README says which cases
   are meant to fail; it ends with a warning to add the provider's API key.

Later: two skills (project setup, e.g. drafting evals from the user's
schema; hosting and CI), in the Agent Skills format so they work in Claude
Code and Codex; `init` could add them behind an opt-in flag (`--with-skill`).


## Evaluate Snowflake's business chat (Snowflake Intelligence / Cortex Agents)

Goal: test the same experience business users have when they ask data
questions in Snowflake's chat, not just the MCP server's tools. Discussed
2026-10-03, after comparing honest-agent with the Claude Desktop connector:
the same server and tools gave different routes depending on the model and
the client's own instructions, so testing the tools alone doesn't reproduce
what users see.

The chat runs on a Cortex Agent: a schema-level object bundling the model,
instructions and tools (Cortex Analyst over semantic views, search, SQL),
set up by an admin. The same object can be called through Snowflake's REST
API, `/api/v2/databases/{db}/schemas/{schema}/agents/{agent}:run`, so an
eval would get the same model, instructions and tools as the chat.

That needs a new kind of target, not just configuration:

- New: a runner that sends each prompt to `agent:run` (PAT auth, as for the
  MCP server) and turns the streamed reply into the stored trace and answer.
  The agent runs its own loop, so honest-agent's model loop and
  `max_tool_turns` don't apply.
- Reused: eval files, grading, provenance, storage, report, the config file
  (one more target, e.g. `agent_run_url:`).
- First check, before building: whether the streamed reply includes the SQL
  Cortex Analyst generated and ran. If yes, provenance works as today; if
  not, only accuracy can be graded.
- Not reproducible: the user's conversation history (each eval starts
  fresh) and their exact identity; use a test user with the same role.
- Less faithful alternative: expose the agent as a `CORTEX_AGENT_RUN` tool on
  the MCP server. That works with today's code, but honest-agent's own model
  then sits in front of the agent.

CoCo (Cortex Code, with a CLI) was considered and set aside: it's Snowflake's
coding agent for developers, not what business stakeholders use. It could be
a later, separate target (`cortex -p ... --output-format stream-json`).

## User-reported issues from Claude Desktop (chat)

**Goal:** people who use the agent through the Claude Desktop chat can flag
a bad answer from inside the conversation ("report this"), and the report
lands in S3. Discussed 2026-10-04. Reports capture real failures where they
happen, and each one is a draft eval (see the end of this section).

**Decided:** reports go to S3.

**Storage format: one JSON file per report, not DuckLake (yet).**

- Layout: `s3://<bucket>/reports/date=YYYY-MM-DD/<report_id>.json`.
  Append-only, no coordination between writers, queryable as is with
  DuckDB: `select * from read_json('s3://<bucket>/reports/*/*.json')`.
- The writer only needs `s3:PutObject` on that prefix, so a reporter can't
  read, change or delete anyone else's reports.
- DuckLake would need a catalog that every writer updates. With reports
  written from several machines, that means a shared catalog database
  (e.g. Postgres) and writers with access to it; concurrent DuckLake writers
  were never tested either (see "Migrate S3 export ... to DuckLake"). Not
  worth it at a few reports a week. Revisit if the export moves to DuckLake;
  the JSON files can be loaded into a table then.

**Report schema (draft):**

| Field | Notes |
|---|---|
| `report_id`, `reported_at` | generated by the tool |
| `reporter` | from the server's config; Claude Desktop doesn't tell tools who the user is |
| `agent` | which agent/connector answered, e.g. `snowflake` |
| `question`, `answer` | the flagged exchange, as asked and answered |
| `tool_calls` | the SQL or tool calls the agent made, if visible in the chat, for provenance |
| `category` | `wrong_number`, `wrong_source`, `hallucinated_detail`, `missed_caveat`, `bad_logic`, `other` |
| `severity` | `low` / `medium` / `high`, optional |
| `note` | the reporter's own words |

No session id: Claude Desktop doesn't pass a conversation id to tools.

**MCP server:** one tool, `report_issue(record)`, that validates the record
and writes the JSON file.

- Personal use: a local server started by Claude Desktop (its MCP config
  file), with AWS credentials limited to `s3:PutObject` on the prefix. It
  could ship in the honest-agent package as a subcommand (e.g.
  `honest-agent report-server`), so there's nothing extra to install.
- Other users: a remote connector needs a hosted URL with OAuth, i.e. real
  infrastructure. Only worth it once several people use it.

**The Claude skill:**

- Triggers on "report this", "flag this", "this answer is wrong".
- Takes the question, answer and visible tool calls from the conversation;
  the reporter shouldn't have to paste anything.
- Asks at most one or two questions, only when the category or severity
  isn't clear from what they said.
- Shows the record before sending, then confirms with the report id.

**Decide before building:** personal use only, or an installable plugin for
other honest-agent users. It changes the server (local vs. hosted), auth,
and how the skill is distributed.

**Privacy:** reports contain real data from answers. The bucket needs
access limited to the people who triage reports, and a retention rule.

**Done when:** a report flagged in Claude Desktop shows up in S3 with every
field filled, and the DuckDB query above returns it.

**Link to evals:** a confirmed report has the question, the wrong answer
and the tools used. Once someone adds the right answer and source, it's an
eval that catches the same mistake next time. A later `honest-agent`
command could turn reports into draft eval files.
