# The Honest Agent (`honest-agent`)

Evaluate an analytics AI agent with known prompts/answers and check two things about
each response:

- **accuracy** — is the answer correct?
- **provenance** — did the agent use the right sources/tools to derive it?

Results are stored in a DuckDB file, graded against per-eval thresholds,
shown in a web report you can host for your team, and alerted on in Slack.
See [Running it for a team](#running-it-for-a-team).

Python tooling is managed with [`uv`](https://docs.astral.sh/uv/) — the
workflow in both `cli/` and `example_project/` is `uv sync` + `uv run ...`,
never a hand-rolled `venv`/`pip install`.

## Layout

- **`cli/`** — the `honest-agent` Python CLI. Owns every LLM call (running the
  eval, LLM-judge grading, provenance scoring), the threshold checks, and
  everything else (Slack notifications, the web report and `serve`). Results
  storage is a local DuckDB file by default, or a MotherDuck database. `honest-agent run` calls
  the model you choose, Claude or OpenAI (GPT), with tools sourced live from
  the MCP server a target in `honest_agent_config.yml` points to — this tests
  the actual tools employees connect to, not a locally reimplemented stand-in
  whose behavior can drift out of sync with the real tool. Needs Python
  >=3.10.
- **`ui/`** — the source of the web report (React + Vite). Its build is
  committed to `cli/honest_agent/report_ui/`, so users don't need Node.
- **`example_project/`** — a real-world-shaped consumer of the CLI: its own
  example eval YAML and a README showing the actual install/run flow. This
  is the only place example data lives.

## Getting started

You need:

- [uv](https://docs.astral.sh/uv/getting-started/installation/). It also
  installs Python for you if needed (honest-agent needs 3.10 or later).
- A model API key: `ANTHROPIC_API_KEY` for Claude
  ([console.anthropic.com](https://console.anthropic.com)) or
  `OPENAI_API_KEY` for GPT ([platform.openai.com](https://platform.openai.com/api-keys)).
  These are API keys, separate from a claude.ai or ChatGPT subscription.
- The MCP server your agent uses: its URL and a token, or the command that
  starts it locally.

To see it work before connecting your own agent, run
`uv run honest-agent init --example` after step 1: it creates
`honest-agent-example/`, a demo agent over DuckDB's sample data with six evals
(some fail on purpose), runnable with only a model API key.

### 1. Create a project and install

```bash
mkdir my-agent-evals && cd my-agent-evals
uv init --bare --python 3.11
uv add "honest-agent @ git+https://github.com/jlcoto/the_honest_agent.git#subdirectory=cli"
```

`uv init --bare` creates only a `pyproject.toml`. `uv add` installs
honest-agent into the project and records the exact version in `uv.lock`, so
teammates who run `uv sync` get the same one.

### 2. Create the starter files

```bash
uv run honest-agent init
```

`init` asks a few questions, with numbered options and defaults (Enter accepts
them): which MCP server your agent uses (a local command, Snowflake's managed
MCP server, MotherDuck or another URL), its URL or command, which model runs
the agent (Claude or OpenAI) and where results live (here, MotherDuck or a
file in S3). Then it writes three files, and never overwrites one that exists:

| File | What it holds |
|---|---|
| `honest_agent_config.yml` | One target for your agent, like a target in a dbt profile |
| `evals/first_eval.yml` | A first eval to fill in |
| `.env` | The variables the setup needs: your server's URL, and empty slots for the keys |

Every answer is also a flag, for scripts and CI:
`uv run honest-agent init --server snowflake --mcp-url https://... --no-input`
(`honest-agent init --help` lists them).

If the project is in git, add `.env` and `honest_agent_report/` to
`.gitignore`; `init` lists whatever isn't ignored yet. The results folder
keeps itself out of git; the report folder holds only the website, so it can
be uploaded as is.

### 3. Fill in `.env`

```
ANTHROPIC_API_KEY=...        # or OPENAI_API_KEY=...
SNOWFLAKE_MCP_TOKEN=...      # the token for your MCP server
```

Only secrets and account URLs go here. The config reads the URL with
`{{ env_var('SNOWFLAKE_MCP_URL') }}`, the way dbt does, so the config holds no
account and you can commit it to share targets with your team
([details](example_project/README.md#reading-values-from-the-environment)).
More targets, `mcp_env` for local servers and every other setting are in
[The config file](example_project/README.md#the-config-file).

**Give the MCP server read-only credentials.** honest-agent runs your agent
with every tool its MCP server offers, and the agent reads your data, which
can contain text written as instructions. honest-agent refuses SQL that isn't
a read (`select`, `show`, `describe`, `use`) before it reaches the server, but
it only sees SQL: a tool like `delete_customer(id)` isn't checked.

### 4. Write your first eval

Edit `evals/first_eval.yml` and replace each `TODO`: a question your agent
should answer from your data, the answer you know is right, and the tables it
should read. For example:

```yaml
    tests:
      - title: Orders placed in 1996
        prompt: How many orders were placed in 1996? Query the warehouse and give me just the number.
        expected_answer: "2297"
        provenance:
          expected_sources: [orders]
```

`expected_answer` checks accuracy; `expected_sources` checks provenance, i.e.
that the SQL the agent ran actually read `orders`. (This example fits the
bundled demo warehouse's TPC-H data, not yours.) See
[Writing evals](example_project/README.md#writing-evals) and
[Choosing a grading method](example_project/README.md#choosing-a-grading-method).

### 5. Run and look at the results

```bash
uv run honest-agent run       # runs every eval against the default target
uv run honest-agent report    # writes the report to honest_agent_report/
uv run honest-agent serve     # opens it in your browser (Ctrl+C to stop)
```

- `run` uses `default_target`, so you only need `--target` for another one:
  `run --target motherduck`.
- `uv run honest-agent debug` checks the setup first, like `dbt debug`: config,
  variables, evals, the MCP server and the results store, without calling a
  model or running a query.
- To run only some evals, select them dbt-style: by id (`run --select
  orders_placed_in_1996`), tag (`--select tag:smoke`) or category
  (`--select category:sales`). Spaces mean OR, commas mean AND, and
  `--exclude` leaves evals out. `honest-agent ls` takes the same options and
  lists what would run, with each eval's id, category and tags.
- To see why an eval failed, `uv run honest-agent logs --eval-id
  orders_placed_in_1996` prints what the agent sent and received, call by
  call: every model call, tool call and grading call, with its timing (`--json`
  for the records as stored). An eval's id comes from its title unless you set
  `id:`.
- `uv run honest-agent rebuild` re-scores past runs from what they recorded,
  after an upgrade changes how honest-agent scores or reads them. It calls no
  model, so it costs nothing.
- To update honest-agent: `uv lock --upgrade-package honest-agent && uv sync`.

**Your results contain what the agent saw.** The results file
(`honest_agent_results/results.duckdb`) keeps everything each run sent and
received, and the report folder the agent's conversations, including what
the agent's tools returned: query results
(possibly customer rows, names or emails), table and column listings, error
messages that can name accounts and roles, and the agent's answers. Access
tokens are never stored. Keeping these files safe is up to you: treat them
like the data your agent can query, and think before hosting or sharing the
report. Keep both out of git (step 2).

### Alternative: one `honest-agent` command for every project

```bash
uv tool install "honest-agent @ git+https://github.com/jlcoto/the_honest_agent.git#subdirectory=cli"
```

Then run `honest-agent run` (without `uv run`) in any folder with a
`honest_agent_config.yml`; it reads that folder's `.env` and config. Update
with `uv tool upgrade honest-agent`. The tradeoff: every project uses the
same version, instead of the one pinned in its `uv.lock`.

### If something goes wrong

Run `honest-agent debug` first: it checks each part of the setup and says what's wrong.

| You see | What to do |
|---|---|
| `--mcp-command or --mcp-url is required` | honest-agent found no `honest_agent_config.yml`: run it from your project folder, or create one with `honest-agent init`. In the bundled example, copy `honest_agent_config.example.yml` to `honest_agent_config.yml` first. |
| `... reads env_var('X'), but X isn't set` | The config reads `X` from the environment: add it to `.env`. |
| `Note: MCP_URL from the environment overrides target ...` | An environment variable beats the config file. Remove `MCP_URL`/`MCP_COMMAND` from `.env` and your shell. |
| `Unknown setting(s) in target ...` | A typo in `honest_agent_config.yml`; the message lists the allowed settings. |
| A local server fails to log in to its database | It only gets the variables listed in its target's `mcp_env`; add the one it needs. |
| `report` says a folder `isn't an honest-agent report folder` | `report` only writes into a new or empty folder, or one it wrote before, because it clears old files there. Pick another `--out`. |
| `serve` says a folder `isn't an honest-agent report folder` | `serve` only publishes a folder `report` wrote, so it can't expose other files (like `.env`). Run `honest-agent report` first, or pass its folder with `--out`. |
| `Address already in use` from `serve` | Another server uses the port: `serve --port 8001`. |
| `honest-agent didn't run this SQL: it contains a ... statement` | The agent sent SQL that isn't a read, so it wasn't run: honest-agent never lets an agent change the warehouse, temp tables included. |
| `hit the step limit without a final answer` | The agent needed more steps: set `max_tool_steps: 10` on the target. |

## Try the bundled example

```bash
cd example_project
uv python install 3.11                                       # one-time; honest-agent needs Python >=3.10
uv sync --python 3.11                                         # installs honest-agent, editable, from ../cli
uv run python warehouse/seed.py                               # seeds warehouse.duckdb from DuckDB's TPC-H generator
cp honest_agent_config.example.yml honest_agent_config.yml    # local config, ignored by git; add your own URLs
export ANTHROPIC_API_KEY=...                                 # or put it in a .env here or in a parent folder -- auto-loaded
uv run honest-agent run                                        # evaluates the default target in honest_agent_config.yml
uv run honest-agent report                                     # writes the web report to honest_agent_report/
uv run honest-agent serve                                      # opens the report in your browser, like `dbt docs serve`
uv run honest-agent notify --webhook-url ...                   # Slack alert if the default target's latest run failed
```

`honest_agent_config.yml` holds the project's settings, with one target
per agent being evaluated, like the targets in a dbt profile: `honest-agent run --target
motherduck` evaluates another one. The default target calls the model with the
`query_warehouse` tool sourced live from the
bundled demo MCP server (`python -m honest_agent.demo_server`), against a real seeded
TPC-H warehouse — real SQL, real data, real provenance checking (does the
agent's SQL actually hit the table we expect). By default results land in
`./honest_agent_results/results.duckdb`. See `example_project/README.md` for
details, including how to point at a real
MCP server (MotherDuck, Snowflake, or your own) instead of the bundled demo
one, and `example_project/evals/example_eval.yml` for how each eval
declares its own accuracy/provenance thresholds (`grading.min_score` /
`provenance.min_score`).

## Running it for a team

Locally, everything lives in your project folder. For a team, two different
things are shared, in two different places:

| | The results database | The report |
|---|---|---|
| What it is | `results.duckdb`: every run, with what each call sent and received | A website (`honest_agent_report/`) built from the database by `honest-agent report` |
| What it holds | All history | The last 30 days (`--days`) |
| Who uses it | The job that runs the evals; people who query it with SQL | Your team, in the browser |
| Where it goes | MotherDuck, or private storage such as an S3 bucket | A static host behind a sign-in |

Keep them apart: viewers of the report never need the database, which holds
more (all history, the raw records, run settings). Sharing the report doesn't
share the database, and the database is never put on the report's host.

A scheduled job ties them together: it runs the evals into the database,
rebuilds the report and publishes it. [`docs/hosting.md`](docs/hosting.md) is
a tested recipe for all of it (results in MotherDuck or S3, the report on
Cloudflare Pages or CloudFront, GitHub Actions, Slack). Never host the report
publicly: it holds what your agent's tools returned.

**Results in MotherDuck** instead of a local file: set
`results_path: md:honest_agent_results` and put a read/write token in
`HONEST_AGENT_RESULTS_TOKEN`. The database is created on the first `run`, and
CI jobs and teammates then share one store with nothing to download or upload.
Use a token of a MotherDuck service account that holds only the results, never
the motherduck target's `MOTHERDUCK_TOKEN`: the agent being evaluated must not
be able to change its own results. honest-agent opens the results with
`HONEST_AGENT_RESULTS_TOKEN` alone, even when `MOTHERDUCK_TOKEN` is also set.

**Slack alerts:** `honest-agent notify` alerts on one target's latest run: the default target,
or another with `--target`, the same way `run` picks one. Use one webhook per
environment (`notify --target snowflake_dev` to a dev channel), and give a dev
target its own `agent_name`: two targets with the same `agent_name` file their
runs, and alerts, as the same agent. Pass `--report-url` (or set
`HONEST_AGENT_REPORT_URL`) to where the report is published, and the alert
links each failing eval to its page.

## Developing the CLI

```bash
cd cli
uv sync --all-extras     # base deps + test + lint (Python >=3.10;
                          # uv picks a suitable interpreter, or pass --python 3.11)
uv run pytest -q
uv run honest-agent --help
```
