# The Honest Agent (`honest-agent`)

Evaluate an analytics AI agent with known prompts/answers and check two things about
each response:

- **accuracy** — is the answer correct?
- **provenance** — did the agent use the right sources/tools to derive it?

Results are stored in a local DuckDB file, graded against per-eval
thresholds, and can be visualized, alerted on, and (optionally) exported to
S3 as Parquet for sharing with a team or other tools.

Python tooling is managed with [`uv`](https://docs.astral.sh/uv/) — the
workflow in both `cli/` and `example_project/` is `uv sync` + `uv run ...`,
never a hand-rolled `venv`/`pip install`.

## Layout

- **`cli/`** — the `honest-agent` Python CLI. Owns every LLM call (running the
  eval, LLM-judge grading, provenance scoring), the threshold checks, and
  everything else (Slack notifications, the static HTML report). Results
  storage is a local DuckDB file by default; `honest-agent export` can push a
  Parquet snapshot to S3 (via DuckDB's own `httpfs` extension) for sharing
  with a team, but that's an explicit, optional step. `honest-agent run` calls
  Claude with tools sourced live from an MCP server (`--mcp-command`/
  `--mcp-url`) — this tests the actual agent employees connect to, not a
  locally reimplemented stand-in whose behavior can drift out of sync with
  the real tool. Needs Python >=3.10 — see `example_project/README.md`.
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

### 1. Create a project and install

```bash
mkdir my-agent-evals && cd my-agent-evals
uv init --bare --python 3.11
uv add "honest-agent @ git+https://github.com/jlcoto/the_honest_agent.git#subdirectory=cli"
```

`uv init --bare` creates only a `pyproject.toml`. `uv add` installs
honest-agent into the project and records the exact version in `uv.lock`, so
teammates who run `uv sync` get the same one.

### 2. Put secrets in `.env`

```
ANTHROPIC_API_KEY=...        # or OPENAI_API_KEY=...
SNOWFLAKE_MCP_TOKEN=...      # the token for your MCP server
```

Only secrets go here. If the project is in git, add `.env` to `.gitignore`.
honest-agent's own results and report folders keep themselves out of git.

### 3. Describe your agent in `honest_agent_config.yml`

One target per agent you evaluate, like the targets in a dbt profile:

```yaml
default_target: snowflake
targets:
  snowflake:
    mcp_url: https://<account>.snowflakecomputing.com/api/v2/databases/<db>/schemas/<schema>/mcp-servers/<server>
    bearer_token_env: SNOWFLAKE_MCP_TOKEN   # the .env variable holding the token
```

Other servers work the same way, for example MotherDuck's hosted one:

```yaml
  motherduck:
    mcp_url: https://api.motherduck.com/mcp
    bearer_token_env: MOTHERDUCK_TOKEN
    max_tool_turns: 10
```

A server you run locally takes `mcp_command:` instead of `mcp_url:`. Every
setting is described in [`example_project/README.md`](example_project/README.md#the-config-file).

### 4. Write an eval in `evals/`

`evals/orders.yml`:

```yaml
version: 1
evals:
  - category: orders
    grading:
      method: extract_match
      min_score: 0.8
    provenance:
      min_score: 0.7
    tests:
      - title: Orders placed in 1996
        prompt: How many orders were placed in 1996? Query the warehouse and give me just the number.
        expected_answer: "2297"
        provenance:
          expected_sources: [orders]
```

`expected_answer` checks accuracy; `expected_sources` checks provenance, i.e.
that the SQL the agent ran actually read `orders`. See
[Writing evals](example_project/README.md#writing-evals) and
[Choosing a grading method](example_project/README.md#choosing-a-grading-method).

### 5. Run and look at the results

```bash
uv run honest-agent run       # runs every eval against the default target
uv run honest-agent report    # writes the report to honest_agent_report/
uv run honest-agent serve     # opens it in your browser (Ctrl+C to stop)
```

- `run --target motherduck` evaluates another target.
- To see why an eval failed, `uv run honest-agent logs --eval-id
  orders_placed_in_1996` prints the answer, the SQL the agent ran and the
  full trace. An eval's id comes from its title unless you set `id:`.
- To update honest-agent: `uv lock --upgrade-package honest-agent && uv sync`.

### Alternative: one `honest-agent` command for every project

```bash
uv tool install "honest-agent @ git+https://github.com/jlcoto/the_honest_agent.git#subdirectory=cli"
```

Then run `honest-agent run` (without `uv run`) in any folder with a
`honest_agent_config.yml`; it reads that folder's `.env` and config. Update
with `uv tool upgrade honest-agent`. The tradeoff: every project uses the
same version, instead of the one pinned in its `uv.lock`.

### If something goes wrong

| You see | What to do |
|---|---|
| `--mcp-command or --mcp-url is required` | honest-agent found no `honest_agent_config.yml`: run it from your project folder. |
| `Note: MCP_URL from the environment overrides target ...` | An environment variable beats the config file. Remove `MCP_URL`/`MCP_COMMAND` from `.env` and your shell. |
| `Unknown setting(s) in target ...` | A typo in `honest_agent_config.yml`; the message lists the allowed settings. |
| `Address already in use` from `serve` | Another server uses the port: `serve --port 8001`. |
| `hit the tool-turn limit without a final answer` | The agent needed more steps: set `max_tool_turns: 10` on the target. |

## Try the bundled example

```bash
cd example_project
uv python install 3.11                                       # one-time; honest-agent needs Python >=3.10
uv sync --python 3.11                                         # installs honest-agent, editable, from ../cli
uv run python warehouse/seed.py                               # seeds warehouse.duckdb from DuckDB's TPC-H generator
export ANTHROPIC_API_KEY=...                                 # or put it in a .env here or in a parent folder -- auto-loaded
uv run honest-agent run                                        # evaluates the default target in honest_agent_config.yml
uv run honest-agent report                                     # writes the web report to honest_agent_report/
uv run honest-agent serve                                      # opens the report in your browser, like `dbt docs serve`
uv run honest-agent notify --webhook-url ...                   # Slack alert on regressions
```

`honest_agent_config.yml` holds the project's settings, with one target
per agent being evaluated, like the targets in a dbt profile: `honest-agent run --target
motherduck` evaluates another one. The default target calls Claude with the
`query_warehouse` tool sourced live from the
bundled demo MCP server (`mcp_server/server.py`), against a real seeded
TPC-H warehouse — real SQL, real data, real provenance checking (does the
agent's SQL actually hit the table we expect). By default results land in
`./honest_agent_results/results.duckdb`. Run `honest-agent export --s3-path
s3://...` afterward if you want a Parquet snapshot in S3 too — see
`example_project/README.md` for details, including how to point at a real
MCP server (MotherDuck, Snowflake, or your own) instead of the bundled demo
one, and `example_project/evals/example_eval.yml` for how each eval
declares its own accuracy/provenance thresholds (`grading.min_score` /
`provenance.min_score`).

## Developing the CLI

```bash
cd cli
uv sync --all-extras     # base deps + test + lint (Python >=3.10;
                          # uv picks a suitable interpreter, or pass --python 3.11)
uv run pytest -q
uv run honest-agent --help
```
