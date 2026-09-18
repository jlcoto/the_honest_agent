# example_project

A real-world-shaped consumer of the `agent-quiz` CLI — this is where
example/demo content lives; the CLI itself ships none of its own.

Python dependencies here are managed with [`uv`](https://docs.astral.sh/uv/);
`agent-quiz` is pulled in as an **editable local path dependency** on `../cli`
(see `pyproject.toml`'s `[tool.uv.sources]`) rather than published to PyPI.

This demo covers both of the CLI's agent backends, in two separate quiz
directories:

- **`quizzes/` (and `quizzes_motherduck/`, `quizzes_snowflake/`) — MCP.**
  Real questions against a warehouse (`warehouse.duckdb`) seeded from
  DuckDB's own built-in TPC-H generator — a standard multi-table schema
  (`orders`, `lineitem`, `customer`, `part`, `supplier`, `nation`, `region`,
  ...) with real joins, not a single flat table. The tool that answers them
  (`query_warehouse`) is only exposed by the bundled demo MCP server
  (`mcp_server/server.py`), or by a real MotherDuck/Snowflake MCP server —
  this is what demonstrates provenance checking against *real* SQL and
  *real* data.
- **`quizzes_claude/` — Claude-direct.** A lightweight `calculator` tool,
  declared right in the quiz YAML and executed locally (no MCP server, no
  warehouse to seed) — see `quizzes_claude/example_quiz.yml`. Good for a
  fast first run, or as a template for wiring up your own local tool
  executor.

## Setup

The `mcp` package requires **Python >=3.10**, one version floor higher than
the rest of this project (>=3.9) — `uv` manages that interpreter for you:

```bash
cd example_project
uv python install 3.11                          # one-time; uv manages this interpreter itself
uv sync --extra mcp --python 3.11                # installs agent-quiz + mcp, editable
uv run python warehouse/seed.py                  # seeds warehouse.duckdb from DuckDB's TPC-H generator
export ANTHROPIC_API_KEY=...                     # needed for the agent + the extract_match grader
# or put it (and SLACK_WEBHOOK_URL / MCP_BEARER_TOKEN / AWS_* as needed) in a
# .env at the repo root -- auto-loaded on every `agent-quiz` command, no
# export/--env-file needed.
```

## Quickest path: Claude-direct backend

No MCP extra, no Python 3.11, no warehouse seeding — just base deps:

```bash
cd example_project
uv sync                                          # base deps only
export ANTHROPIC_API_KEY=...                     # or put it in a .env at the repo root
uv run agent-quiz run --quizzes-dir quizzes_claude --agent-backend claude
uv run agent-quiz report --out agent_quiz_report.html
```

This calls Claude directly with the `calculator` tool declared in
`quizzes_claude/example_quiz.yml`, executed locally by
`agent_quiz_cli/tools.py` — no server process, nothing to connect to. Good
for confirming the CLI itself works end to end before setting up MCP.

## Run the quiz end to end (MCP backend)

```bash
uv run agent-quiz run --quizzes-dir quizzes \
  --agent-backend mcp \
  --mcp-command "$(pwd)/.venv/bin/python mcp_server/server.py"
uv run agent-quiz report --out agent_quiz_report.html
uv run agent-quiz notify --webhook-url https://hooks.slack.com/services/...
```

Use `$(pwd)/.venv/bin/python` (not a bare `python`/`python3`) for
`--mcp-command` — `agent-quiz` launches it as a subprocess, and a bare
`python` may not resolve to the right interpreter (or any interpreter) once
it's out of your interactive shell's PATH.

- `agent-quiz run` reads `quizzes/example_quiz.yml`, connects to the MCP
  server, calls Claude with the live `query_warehouse` tool for each prompt,
  grades accuracy (`extract_match`: a cheap extraction call normalizes the
  answer, then compares it exactly against `expected_answer`) and provenance
  — by inspecting the SQL a tool actually ran, *which table* it queried
  (`expected_sources`, optionally narrowed to a specific database/schema via
  `expected_database`/`expected_schema`) — against each quiz's own
  thresholds (`grading.min_score` / `provenance.min_score` in the YAML —
  default to 0.8 / 0.7 if omitted), and appends the results into a local
  DuckDB file at `./agent_quiz_results/results.duckdb` (created on first
  run).
- `q_revenue_1996` expects the agent to query `fct_revenue_by_year` (the
  pre-aggregated mart) rather than joining `orders`+`lineitem` and
  recomputing TPC-H's revenue formula by hand — if it queries the wrong
  table, `provenance_score` drops below threshold even though the *answer*
  might still come out correct. Run `agent-quiz logs` after a run to see
  exactly what SQL it executed.
- `agent-quiz report` renders `agent_quiz_report.html` from every stored run.
- `agent-quiz notify` checks only the *most recent* run's results against
  their thresholds and posts to Slack if anything's below.

Every command takes `--results-path` (default
`./agent_quiz_results/results.duckdb`) pointing at that local file. DuckDB
(like SQLite) allows only one writer at a time, so this is a good fit for
`agent-quiz run`'s occasional, sequential writes, but it's **not** a
shared/concurrent store on its own — it's a local file on whoever's machine
runs `agent-quiz run`.

Re-running `agent-quiz run` inserts another batch of rows under a new
`run_id`, so history just accumulates in the same file — `agent-quiz
report`'s run-summary table picks up the trend automatically.

### Sharing results with a team (optional)

If you want results durable and queryable by other tools/people rather than
sitting in one local file, export a Parquet snapshot to S3 — built on
DuckDB's own `httpfs` extension (installed automatically on first use, no
separate S3 SDK dependency):

```bash
uv run agent-quiz export --s3-path s3://your-bucket/agent_quiz/results.parquet
```

This reads AWS credentials the standard way DuckDB does (`AWS_ACCESS_KEY_ID`
/ `AWS_SECRET_ACCESS_KEY` env vars, a shared `~/.aws/credentials` profile,
etc.) — nothing bespoke. The resulting Parquet file is exactly what
Snowflake/BigQuery/Athena would define an external table over, or what
another DuckDB (anyone's laptop, a scheduled job) can query directly with
`read_parquet('s3://...')`. This step is entirely optional — nothing else
in this project requires it, and if you never run it nothing ever touches
S3.

## Pointing at a real MCP server instead of the bundled demo one

Swap `--mcp-command "$(pwd)/.venv/bin/python mcp_server/server.py"` for
`--mcp-url https://your-mcp-server/mcp` (add `--mcp-bearer-token`, or set
`MCP_BEARER_TOKEN`, if it requires auth), and rewrite the quizzes'
`expected_sources` to match that server's actual table/model names.
`provenance.sql_fields` may also need updating if the real tool's
SQL-holding input field isn't literally called `sql` — see the top-level
`README.md` and `agent_quiz_cli/sql_capture.py` for how that's resolved.

## Connecting to a real MotherDuck account

`quizzes_motherduck/example_quiz.yml` points at MotherDuck's own official MCP
server (`uvx mcp-server-motherduck`) instead of the bundled demo one.

**If you're not on a MotherDuck Business-plan (team) account, pass
`--read-write`, or expect a confusing auth error.**
`mcp-server-motherduck` defaults to a read-only mode that requires a
**read-scaling token** specifically — not just any read-only permission, a
distinct token type generated for that purpose, and (per MotherDuck's
pricing page) only available on the Business plan. A personal/free-tier
account's token is always read/write, so the default `--read-only` mode
can never work there — this isn't a one-off config mistake to fix, it's a
plan limitation. If you connect with that ordinary read/write token anyway,
the server refuses to start at all:

```
ValueError: The --read-only flag with MotherDuck requires a read-scaling
token. You appear to be using a read/write token.
```

See [read scaling docs][motherduck-read-scaling] for what a read-scaling
token actually is (its plan requirement isn't stated on that page itself,
only on the pricing page). If you *are* on a Business-plan account, you
could generate one and use `--read-only` instead — but for everyone else,
the fix isn't "generate the right token," it's passing `--read-write`
instead, using your normal token:

```bash
agent-quiz run --quizzes-dir quizzes_motherduck \
  --agent-backend mcp \
  --mcp-command "uvx mcp-server-motherduck --read-write --db-path md:agent_quiz_demo"
```

This means `agent_quiz`'s own PAT (via `MOTHERDUCK_TOKEN`) has full
read/write access to whatever database it's pointed at for the duration of
the run — same tradeoff as any read/write credential, worth keeping in mind
if you point this at something other than a disposable demo database.

[motherduck-read-scaling]: https://motherduck.com/docs/key-tasks/authenticating-and-connecting-to-motherduck/read-scaling/

## Connecting to a real Snowflake account (managed MCP server)

Snowflake's own connector is a good worked example of "pointing at a real MCP
server" above, since it has real constraints worth understanding before you
try it.

### Why this only works with a PAT, not key-pair auth

Snowflake's current, officially supported MCP offering isn't a package you
install and run yourself (a community one, `Snowflake-Labs/mcp`, existed and
supported key-pair auth over stdio, but it's now deprecated). The current
path is a **Snowflake-managed server object**, created inside your own
account via `create mcp server` ([SQL reference][create-mcp-server], [feature
guide][cortex-agents-mcp]), reachable only over remote HTTP — there's no
local/stdio version anymore.

That managed server supports exactly two auth methods: **OAuth 2.0**
(Snowflake's primary, most-documented flow — see the feature guide above) or
a **Personal Access Token (PAT)** sent as an `Authorization: Bearer <token>`
header. **RSA key-pair auth isn't supported at this layer** — it's a real
feature of Snowflake's Python connector for normal SQL connections, but the
managed MCP server's auth surface doesn't expose it.

Given that, PAT is the practical choice for `agent-quiz` specifically: OAuth
means a full browser-based authorization-code flow, which a CLI test harness
isn't set up to do (and which real Claude clients like Claude Cowork have
also hit friction with against Snowflake specifically — its OAuth
implementation doesn't support Dynamic Client Registration, the mechanism
those clients rely on to register automatically). PAT, by contrast, is just
a bearer token — exactly what `--mcp-bearer-token`/`MCP_BEARER_TOKEN` already
handles, no new code needed.

### Generating a PAT

Snowflake requires a **network policy** to be attached before it'll issue a
PAT usable for authentication ([PAT guide][pat-guide], [network policy
guide][network-policy-guide]) — for a `service`-type user specifically (the
right type for a non-human/automated credential like this), it's required
even to *generate* the token, not just to use it afterward. Run this as a
role with `create user`/`create role` privileges, e.g. `accountadmin`:

```sql
-- a dedicated role, scoped to only what's needed
create role if not exists <role_name>;
grant usage on warehouse <warehouse_name> to role <role_name>;
grant usage on database <database_name> to role <role_name>;
grant usage on schema <database_name>.<schema_name> to role <role_name>;
grant select on table <database_name>.<schema_name>.<table_name> to role <role_name>;  -- repeat per table in use

-- a service user -- no password/MFA, meant for programmatic access like this
create user if not exists <user_name>
    type = service
    default_role = <role_name>
    default_warehouse = <warehouse_name>;
grant role <role_name> to user <user_name>;

-- a network policy must exist on the user before a PAT can be generated
-- (current docs recommend `allowed_network_rule_list` over the legacy
-- `allowed_ip_list` used here -- either works, but network rules are the
-- forward-looking option if you're setting this up fresh)
create network policy <network_policy_name>
    allowed_ip_list = ('0.0.0.0/0');  -- or a specific IP/CIDR -- see [network-policy-guide]
alter user <user_name> set network_policy = <network_policy_name>;

-- generate the token -- shown once, save it immediately
alter user <user_name> add programmatic access token <token_name>
    role_restriction = '<role_name>'
    days_to_expiry = 90;
```

Put the returned token in `.env` as `MCP_BEARER_TOKEN=...` ([`ALTER USER ...
ADD PROGRAMMATIC ACCESS TOKEN` reference][alter-user-pat]).

### The MCP server object and its URL

```sql
-- the server name must be fully qualified (database.schema.name) -- it's
-- stored at that path, which is also what the URL below is built from.
-- `SYSTEM_EXECUTE_SQL` takes no `input:` block (database/schema/warehouse
-- aren't tool config). The warehouse comes from the calling role/user's
-- default warehouse, but the *session has no default database/schema* --
-- `select current_database(), current_schema()` inside a query run through
-- this tool both return empty, even though the server object itself lives
-- at a specific database.schema path. Every table reference in SQL sent to
-- this tool must be fully qualified (`<database_name>.<schema_name>.<table>`);
-- an agent that queries `information_schema.tables` first (unqualified --
-- that part resolves fine) can discover the right fully-qualified names
-- before querying real tables.
create mcp server <database_name>.<schema_name>.<mcp_server_name>
    from specification $$
    tools:
      - title: "SQL Execution Tool"
        name: query_warehouse
        type: SYSTEM_EXECUTE_SQL
        description: "Execute read-only SQL queries against the connected Snowflake database."
    $$;
grant usage on mcp server <database_name>.<schema_name>.<mcp_server_name> to role <role_name>;
```

The URL to pass as `--mcp-url`/`MCP_URL` follows a fixed shape
([reference][create-mcp-server]):

```
https://<account_identifier>.snowflakecomputing.com/api/v2/databases/<database_name>/schemas/<schema_name>/mcp-servers/<mcp_server_name>
```

Get `<account_identifier>` in the right format with
`select current_organization_name() || '-' || current_account_name();`.

[create-mcp-server]: https://docs.snowflake.com/en/sql-reference/sql/create-mcp-server
[cortex-agents-mcp]: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp
[pat-guide]: https://docs.snowflake.com/en/user-guide/programmatic-access-tokens
[network-policy-guide]: https://docs.snowflake.com/en/user-guide/network-policies
[alter-user-pat]: https://docs.snowflake.com/en/sql-reference/sql/alter-user-add-programmatic-access-token

## Note on the Claude-direct backend (`--agent-backend claude`)

Demonstrated by `quizzes_claude/example_quiz.yml` (see "Quickest path"
above) — Claude called directly, with tools defined right in the quiz
YAML's `tools:` block and executed locally (see `agent_quiz_cli/tools.py`).
Its `calculator` tool is a minimal stand-in; real usage means registering
your own tool executors for whatever your agent actually calls (a warehouse
query tool, a metrics-layer lookup, etc.) in `BUILTIN_TOOL_EXECUTORS`.

One real limitation this example surfaces: `calculator` returns a bare
number, not SQL, so `provenance.py`'s `expected_sources` check (which only
inspects captured SQL text) has nothing to check against here — provenance
scoring on `quizzes_claude`'s quizzes falls back to its trivially-satisfied
default (1.0) rather than meaningfully verifying anything. Provenance
checking as currently built is really aimed at SQL-producing tools; a
non-SQL tool needs its own way of asserting "used the right underlying
data" if that matters for your use case.
