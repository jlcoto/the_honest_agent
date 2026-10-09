# example_project

A real-world-shaped consumer of the `honest-agent` CLI — this is where
example/demo content lives; the CLI itself ships none of its own.

Python dependencies here are managed with [`uv`](https://docs.astral.sh/uv/);
`honest-agent` is pulled in as an **editable local path dependency** on `../cli`
(see `pyproject.toml`'s `[tool.uv.sources]`) rather than published to PyPI.

This demo's example evals (`evals/`, and `evals_motherduck/`,
`evals_snowflake/` for pointing at real warehouses) ask real questions
against a warehouse (`warehouse.duckdb`) seeded from DuckDB's own built-in
TPC-H generator — a standard multi-table schema (`orders`, `lineitem`,
`customer`, `part`, `supplier`, `nation`, `region`, ...) with real joins, not
a single flat table. The tool that answers them (`query_warehouse`) is
exposed by the demo MCP server that ships with honest-agent
(`honest_agent/demo_server.py`), or by a
real MotherDuck/Snowflake MCP server — this is what demonstrates provenance
checking against *real* SQL and *real* data: `honest-agent` calls Claude with
tools sourced live from that MCP server, so it's testing the actual agent
employees would connect to, not a locally reimplemented stand-in.

> **The demo MCP server is for trying honest-agent, not for real data.** It
> runs any read-only SQL the model sends against the whole DuckDB file it's
> given (`python -m honest_agent.demo_server warehouse.duckdb`), with no
> authentication and no limits besides a 200-row cap. honest-agent evaluates
> your agent through your agent's own MCP server; it doesn't provide one. Like
> a real server, the demo doesn't list its tables to the agent: the agent
> finds them itself.

## Setup

honest-agent requires **Python >=3.10** — `uv` manages that interpreter for you:

```bash
cd example_project
uv python install 3.11                          # one-time; uv manages this interpreter itself
uv sync --python 3.11                            # installs honest-agent, editable
uv run python warehouse/seed.py                  # seeds warehouse.duckdb from DuckDB's TPC-H generator
cp honest_agent_config.example.yml honest_agent_config.yml   # your local config (ignored by git)
export ANTHROPIC_API_KEY=...                     # needed for the agent + the extract_match grader
# or put it (and MOTHERDUCK_TOKEN / SLACK_WEBHOOK_URL / AWS_* as needed) in a
# .env at the repo root -- auto-loaded on every `honest-agent` command, since
# it's the nearest .env above this folder.
```

## Run the eval end to end

```bash
uv run honest-agent run
uv run honest-agent report
uv run honest-agent serve
uv run honest-agent notify --webhook-url https://hooks.slack.com/services/...
```

`run` takes its settings from `honest_agent_config.yml` (see "The project
file" below). Its default target, `demo`, starts the bundled MCP server and
reads the evals in `evals/`.

- `honest-agent run` reads `evals/example_eval.yml`, connects to the MCP
  server, calls Claude with the live `query_warehouse` tool for each prompt,
  grades accuracy (`extract_match`: a cheap extraction call normalizes the
  answer, then compares it exactly against `expected_answer`) and provenance
  — by inspecting the SQL a tool actually ran, *which table* it queried
  (`expected_sources`, optionally narrowed to a specific database/schema via
  `expected_database`/`expected_schema`) — against each eval's own
  thresholds (`grading.min_score` / `provenance.min_score` in the YAML —
  default to 0.8 / 0.7 if omitted), and appends the results into a local
  DuckDB file at `./honest_agent_results/results.duckdb` (created on first
  run).
- `q_revenue_1996` expects the agent to read `lineitem` and `orders`, where
  TPC-H's revenue comes from — if it reads only one of them,
  `provenance_score` drops below threshold even though the *answer* might
  still come out correct. Run `honest-agent logs` after a run to see every
  call it made, including the SQL it executed.
- `honest-agent report` writes the web report to `honest_agent_report/`: the
  report UI plus `data/report.json`, holding every stored run's results,
  agent traces, and SQL calls.
- `honest-agent serve` opens that report in your browser, the same way `dbt
  docs serve` serves `target/`. Opening `index.html` directly doesn't work,
  because browsers won't load the data from a `file://` page.
- `honest-agent notify` checks only the *most recent* run's results against
  their thresholds and posts to Slack if anything's below.

Every command takes `--results-path` (default
`./honest_agent_results/results.duckdb`) pointing at that local file. DuckDB
(like SQLite) allows only one writer at a time, so this is a good fit for
`honest-agent run`'s occasional, sequential writes, but it's **not** a
shared/concurrent store on its own — it's a local file on whoever's machine
runs `honest-agent run`.

Re-running `honest-agent run` inserts another batch of rows under a new
`run_id`, so history just accumulates in the same file — `honest-agent
report`'s run-summary table picks up the trend automatically.

### Sharing results with a team

See [`docs/hosting.md`](../docs/hosting.md): results in MotherDuck or a file
in S3, the report behind a sign-in, and scheduled runs in CI. To query
results from SQL, open the DuckDB file (or the MotherDuck database) directly.

## Writing evals

An evals directory holds one or more `*.yml` files. Each has an `evals:`
list of category groups, and each group has `tests:`:

```yaml
version: 1
evals:
  - category: finance
    grading:
      method: extract_match
      min_score: 0.8
    provenance:
      min_score: 0.7
    tags: [motherduck]
    tests:
      - title: Total revenue in 1996
        prompt: What was our total revenue in 1996?
        expected_answer: "311928357.78"
        provenance:
          expected_sources: [lineitem, orders]
        tags: [smoke]
```

- **Inheritance:** anything set on a group (`category`, `grading`,
  `provenance`, `tags`, ...) applies to its tests. The most specific value
  wins, like dbt's config precedence: a test's own setting overrides its
  group's. `grading` and `provenance` merge key by key, so a test can
  override just `min_score` or add `tolerance`. `tags` add up: the test
  above ends up with `[motherduck, smoke]`.
- **Ids come from titles.** Each test needs a `title`. Its id is derived
  from the title (`Total revenue in 1996` → `total_revenue_in_1996`) and is
  what ties its results together across runs, agents and models. Set an
  explicit `id:` to keep that history when you reword a title; without one,
  renaming a title starts the eval over under a new id. The example evals
  here keep explicit ids for that reason.
- **Selecting evals:** `run --select` and `--exclude` pick evals the way
  dbt picks models. A bare word is an eval id, `tag:smoke` a tag and
  `category:finance` a group's category; spaces mean OR and commas AND, so
  `--select "category:finance,tag:smoke total_revenue_in_1996"` runs the
  finance evals tagged smoke plus that one eval. A part that matches no eval
  is an error, not an empty run. `honest-agent ls` lists ids, categories and
  tags, with the same options.
- **The same title or id in different evals directories is intended:**
  that's how results for the same question line up across agents (e.g.
  `evals_motherduck/` and `evals_snowflake/`). Within one directory,
  ids must be unique, and `honest-agent run` stops with an error naming both
  places if two collide.
- **Every eval needs an `expected_answer`;** accuracy is always checked.
  Provenance is optional: leave out `expected_sources` and it isn't checked.
- A plain list of evals without groups also works, each eval carrying all
  of its own settings.

### How provenance is checked

honest-agent parses the SQL the agent ran (with
[sqlglot](https://github.com/tobymao/sqlglot)) and lists every table, view
or semantic view it read, with the database and schema each one lives in.
`provenance_score` is the share of `expected_sources` found in that list.

- **An entry is written like a table name in SQL:** `orders`,
  `public.orders` or `agent_quiz_demo.public.orders`. `expected_database` and
  `expected_schema` fill in the parts an entry leaves out, so sources in
  different places can sit in one list:

  ```yaml
  provenance:
    expected_database: agent_quiz_demo
    expected_schema: public
    expected_sources:
      - orders                                   # agent_quiz_demo.public
      - snowflake_sample_data.tpch_sf1.customer  # its own database and schema
      - staging.customer_flags                   # agent_quiz_demo.staging
  ```

  With no database or schema anywhere, any location counts.
- **No `expected_sources`, no check.** Such an eval's provenance isn't
  scored: the score is left empty (shown as "Not checked"), not 100%, and it
  can't fail. What the agent read is still recorded.
- **Only reads count.** `select` statements (including `with` and `union`)
  count; `describe`, `show` and other exploration don't, and neither do
  queries the tool reported as errors. A tool that returns a failure inside
  a normal response (e.g. `{"success": false, ...}`) instead of flagging it
  as an error isn't caught, so its failed queries still count.
- **SQL a tool generated doesn't count until it runs.** Some tools answer
  with SQL instead of data: Snowflake's Cortex Analyst returns the query it
  wrote for the semantic view. That SQL is recorded, but it only counts once
  the agent runs it itself (e.g. through `query_warehouse`).
- **Locations follow the session.** A table written without its database or
  schema takes them from earlier `use database` / `use schema` statements,
  across tool calls. With neither, its location is unknown and doesn't match
  an expected database or schema.
- **Names in comments, strings, columns or CTEs don't count**, only real
  table references.

## Choosing a grading method

Each eval picks exactly one `grading.method` in its YAML entry — there's no
blending or fallback between them (see `honest_agent/grading.py`):

- **`contains`** (default) — a plain string check, no LLM call at all: does
  `expected_answer` (case/whitespace-insensitive) appear anywhere in the
  agent's answer? Free, deterministic, strictly binary (1.0 or 0.0). Best
  for a short, distinctive phrase you expect verbatim (a name, a fixed
  label). Not a good fit for numbers — it can't tell "4" from "400" if one
  contains the other's digits, and there's no partial credit for close-but-
  wrong.
- **`extract_match`** — a cheap LLM call extracts and normalizes the agent's
  stated value (explicitly told *not* to judge correctness, only extract),
  then compares it deterministically against `expected_answer`. Still
  binary, but tolerant of how the agent phrases things ("The answer is 4."
  / "4" / "It's four" all extract to the same value). Best for a single
  literal answer — a number, a name, a short fact. If the expected value
  might legitimately differ slightly (an unrounded raw query result vs. a
  rounded `expected_answer`, e.g. `q_revenue_1996` in
  `evals/example_eval.yml`), add `tolerance` (an absolute delta) or
  `tolerance_percent` (relative to `expected_answer`'s magnitude) so a
  numeric answer within that range still scores 1.0 instead of failing on a
  precision mismatch. One caveat: this relies on the extraction call
  correctly identifying which value is the "final" one if the agent's
  answer mentions more than one candidate — usually reliable when the
  answer clearly signals its conclusion, not guaranteed otherwise.
- **`llm_judge`** — the judge model reads the question, expected answer, and
  given answer, and scores correctness holistically from 0.0 to 1.0 with a
  rationale. The only method that can give real partial credit, not just
  pass/fail, and the only one that checks how the answer is given: an
  answer that contradicts itself or wavers between values scores 0.0, even
  if one of them is right (`extract_match` would pass it if the value it
  extracts matches). Best for open-ended or multi-part answers where there's no
  single literal value to extract and compare — an explanation, a summary,
  a judgment call on quality. Also the least deterministic and most
  expensive of the three (a full reasoning call, not just extraction), so
  reach for it only when `contains`/`extract_match` genuinely can't express
  what "correct" means for that eval.

| If the expected answer is...                          | Use              |
|---------------------------------------------------------|------------------|
| A short, exact phrase (a name, a label)                  | `contains`       |
| A single number or literal value (possibly rounded)      | `extract_match`  |
| Free text — an explanation, summary, or judgment call     | `llm_judge`      |

### The judge model

`extract_match` and `llm_judge` call a model to grade. By default that's the
same model being evaluated (`--model`). Pass `--judge-model` (or set
`HONEST_AGENT_JUDGE_MODEL`) to grade with a different one, e.g. evaluate Sonnet and
grade with Haiku:

```bash
honest-agent run ... --model claude-sonnet-5 --judge-model claude-haiku-4-5
```

Using the same judge for every run keeps comparisons between agent models
fair: otherwise each model grades itself, and part of a difference between
two models can come from the judge. Each result records its judge in
`grading_model` (empty for `contains`, which uses no model).

## Claude or OpenAI (GPT) models

honest-agent works with either, and installs both SDKs. You only need an API
key for the provider you use: `ANTHROPIC_API_KEY` for Claude, or
`OPENAI_API_KEY` for GPT.

- **Without `--model`**, `run` picks a small, cheap default from the key it
  finds: `claude-haiku-4-5` if `ANTHROPIC_API_KEY` is set (also when both
  are), otherwise `gpt-5.4-mini`. It prints which one it chose.
- **To choose a model**, pass `--model`, or set `HONEST_AGENT_MODEL` in `.env`
  so you don't have to pass it every time. The provider comes from the
  name: `gpt-*`, `o3`, `o4-mini` and similar are OpenAI, anything else is
  Claude.

So a ChatGPT user with only `OPENAI_API_KEY` in `.env` runs exactly the same
command as everyone else:

```bash
uv run honest-agent run --target motherduck
```

Without `--judge-model`, the eval model also grades. The
agent runs the same loop either way (same MCP tools, same SQL capture and
provenance checks), and the report shows GPT runs alongside Claude ones in
the model menus and Model comparison.

## The config file

`honest_agent_config.yml` holds the project's settings, with one **target**
per agent being evaluated, like the targets in a dbt profile. Secrets stay in
`.env`, which the file never contains. In this repo the file itself isn't
committed, because the MotherDuck and Snowflake targets point at your own
accounts: copy `honest_agent_config.example.yml` (committed, with
placeholders) to `honest_agent_config.yml` and fill in your values, the same
way `.env.example` works for secrets. In your own project you can commit the
config to share targets with your team, keeping account URLs in `.env` with
`env_var()` (below), or follow the same example pattern.

```yaml
results_path: ./honest_agent_results/results.duckdb
default_target: demo

targets:
  demo:
    mcp_command: uv run python -m honest_agent.demo_server warehouse.duckdb
    evals_dir: evals
  motherduck:
    mcp_url: https://api.motherduck.com/mcp
    bearer_token_env: MOTHERDUCK_TOKEN   # names the variable in .env, never the token
    evals_dir: evals_motherduck
    max_tool_steps: 10
```

- `honest-agent run` evaluates the `default_target`; `honest-agent run --target
  motherduck` evaluates another one.
- honest-agent finds the file in the folder you run it from, or the nearest
  parent folder, like `.env`. `--config-file PATH` (before the command) or
  `HONEST_AGENT_CONFIG_FILE` points to another one. Without a file,
  everything comes from flags and environment variables.
- Relative paths are relative to the file's folder, and a target's
  `mcp_command` runs from there, so `run` works from any subfolder.

| Setting | Where | Flag it replaces |
|---|---|---|
| `results_path` | top level only: every agent's results share one file, so the report can compare them | `--results-path` |
| `model`, `judge_model`, `max_tool_steps` | top level, or per target | `--model`, `--judge-model`, `--max-tool-steps` |
| `mcp_command` or `mcp_url` (one of them) | target | `--mcp-command`, `--mcp-url` |
| `bearer_token_env`: the variable holding the server's token | target | `--mcp-bearer-token` |
| `evals_dir` | target | `--evals-dir` |
| `agent_name`: defaults to the target's name | target | `--agent-name` |
| `default_database`, `default_schema`: where the server's connection runs a bare table name (see below) | target | none |
| `ignore_tools`: tools whose `sql`/`query`/`statement` argument isn't SQL | target | none |
| `mcp_env`: variables a local server (`mcp_command`) needs, e.g. `[MOTHERDUCK_TOKEN]`. It gets only these plus PATH, HOME and similar, never the rest of `.env` | target | `--mcp-env` (repeatable) |

### Reading values from the environment

Any value can read an environment variable, from `.env` or your shell, the
way dbt does. That keeps account URLs out of a committed file:

```yaml
targets:
  snowflake:
    mcp_url: "{{ env_var('SNOWFLAKE_MCP_URL') }}"
    bearer_token_env: SNOWFLAKE_MCP_TOKEN
    max_tool_steps: "{{ env_var('SNOWFLAKE_MAX_TOOL_STEPS', '10') }}"   # with a default
```

- Quote the whole value, since YAML reads `{` as the start of a map.
- A variable that isn't set, with no default, stops only the target that
  reads it, with an error that names it: other targets still run.
- Only `env_var()` works: other dbt (Jinja) expressions are refused.

### Where bare table names run

Provenance reads a table's database and schema from the SQL: `db.schema.table`,
or an earlier `use`. A bare `from orders` runs wherever the server's connection
starts, which the SQL doesn't show, so its location is unknown and never matches
`expected_database`/`expected_schema`. If your server's connection has a fixed
starting point, declare it on the target:

```yaml
targets:
  demo:
    default_database: warehouse   # DuckDB names the database after the file
    default_schema: main
```

- The SQL always wins: a default only fills in what a name leaves out, and a
  `use` changes it as usual. With only one of the two declared, the other
  stays unknown.
- DuckDB also reads `warehouse.orders` as database.table when there's no schema
  called `warehouse`; with `default_database: warehouse`, so does provenance.
- Each run stores the defaults it used, so `honest-agent rebuild` gives the same
  result even if you change them later.
- **A wrong default fails silently:** provenance would place tables where they
  aren't. Declare only what your server's connection really uses. Snowflake's
  managed MCP server has no default database (bare names fail there), so it
  needs none.
- A server that opens a new connection per tool call (the demo does) doesn't
  keep a `use` from one call to the next, though provenance assumes it does.
  With several schemas on a search path, a default can only name the first.

### Which value wins

For each setting, the first one found:

1. a flag in the command, e.g. `--max-tool-steps 3`
2. an environment variable, from your shell or `.env`, e.g. `HONEST_AGENT_MODEL`
3. the target in `honest_agent_config.yml`
4. the built-in default

When an environment variable overrides the file, `run` prints a note, e.g.
`Note: MCP_URL from the environment overrides target 'motherduck's MCP
server.` Once you use the config file, keep only secrets in `.env`, so
`MCP_URL`/`MCP_COMMAND` left there from before don't override every target.

The bearer token follows its server: a target's server gets the token from
its `bearer_token_env`, never from `MCP_BEARER_TOKEN`, so a token meant for
one vendor isn't sent to another.

## Pointing at a real MCP server instead of the bundled demo one

Add a target with the server's `mcp_url` (and `bearer_token_env`, if it
requires auth) or `mcp_command`, and rewrite its evals' `expected_sources`
to match that server's actual table/model names.

honest-agent finds the SQL by itself in any tool argument named `sql`,
`query` or `statement`. Two settings cover the rare exceptions: the eval's
`provenance.sql_fields` names the argument for a tool that keeps its SQL
somewhere else, and the target's `ignore_tools` lists tools whose
`query`-style argument isn't SQL (a search term, say). MotherDuck's
`search_catalog` is already excluded by default. See
`honest_agent/sql_capture.py` for details.

### Naming the agent

Every result records which agent was evaluated, so the report can filter and
compare by agent.

- **With a target:** the target's name (`demo`, `motherduck`, ...), or its
  `agent_name` if set.
- **Without a config file:** the name the MCP server reports about itself
  when it connects, e.g. `agent_quiz_demo` for the demo server. Pass
  `--agent-name` to choose your own.
- `honest-agent run` prints the name it used (`Evaluating agent: ...`).
- **Labels must match exactly to group together.** Results stored before
  targets existed may carry the server's own name (e.g.
  `mcp-server-motherduck`) and show up as a separate agent in the report.
- **"Unknown agent"** only appears on results stored before agent names were
  recorded.

## Connecting to a real MotherDuck account

The `motherduck` target uses MotherDuck's hosted MCP server
(`https://api.motherduck.com/mcp`), the same one Claude, Cursor and other
clients connect to. Nothing runs locally. Put your token in `.env`:

```
MOTHERDUCK_TOKEN=...
```

and run:

```bash
uv run honest-agent run --target motherduck
```

- **Use a read-only token.** Besides `query`, the server offers `query_rw`
  and tools that create and delete dives, flights and guides, so an agent
  under test could change or delete things in your account with a
  read/write token.
- **Expect more tokens per eval.** The server describes 45 tools to the model
  on every call, and the agent explores (databases, tables, columns) before
  it queries: about 75k–140k input tokens per eval, against about 7k with the
  demo server. That's also why the target sets `max_tool_steps: 10`.

MotherDuck also publishes a local server (`uvx mcp-server-motherduck`). To
use it instead:

```yaml
  motherduck_local:
    mcp_command: uvx mcp-server-motherduck --read-write --db-path md:agent_quiz_demo
    mcp_env: [MOTHERDUCK_TOKEN]
    evals_dir: evals_motherduck
```

`--read-write` is needed unless you have a [read-scaling
token][motherduck-read-scaling] (Business plan only). The server gets only
the variables in `mcp_env`, so it can't read your model API keys or other
secrets in `.env`.

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

Given that, PAT is the practical choice for `honest-agent` specifically: OAuth
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

The URL for the `snowflake` target's `mcp_url` follows a fixed shape
([reference][create-mcp-server]):

```
https://<account_identifier>.snowflakecomputing.com/api/v2/databases/<database_name>/schemas/<schema_name>/mcp-servers/<mcp_server_name>
```

Get `<account_identifier>` in the right format with
`select current_organization_name() || '-' || current_account_name();`.
Put the PAT in `.env` as `SNOWFLAKE_MCP_TOKEN` (the target's
`bearer_token_env`) and run `uv run honest-agent run --target snowflake`.

[create-mcp-server]: https://docs.snowflake.com/en/sql-reference/sql/create-mcp-server
[cortex-agents-mcp]: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp
[pat-guide]: https://docs.snowflake.com/en/user-guide/programmatic-access-tokens
[network-policy-guide]: https://docs.snowflake.com/en/user-guide/network-policies
[alter-user-pat]: https://docs.snowflake.com/en/sql-reference/sql/alter-user-add-programmatic-access-token
