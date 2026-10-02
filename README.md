# The Honest Agent (`honest-agent`)

Quiz an analytics AI agent with known prompts/answers and check two things about
each response:

- **accuracy** — is the answer correct?
- **provenance** — did the agent use the right sources/tools to derive it?

Results are stored in a local DuckDB file, graded against per-quiz
thresholds, and can be visualized, alerted on, and (optionally) exported to
S3 as Parquet for sharing with a team or other tools.

Python tooling is managed with [`uv`](https://docs.astral.sh/uv/) — the
workflow in both `cli/` and `example_project/` is `uv sync` + `uv run ...`,
never a hand-rolled `venv`/`pip install`.

## Layout

- **`cli/`** — the `honest-agent` Python CLI. Owns every LLM call (running the
  quiz, LLM-judge grading, provenance scoring), the threshold checks, and
  everything else (Slack notifications, the static HTML report). Results
  storage is a local DuckDB file by default; `honest-agent export` can push a
  Parquet snapshot to S3 (via DuckDB's own `httpfs` extension) for sharing
  with a team, but that's an explicit, optional step. `honest-agent run` calls
  Claude with tools sourced live from an MCP server (`--mcp-command`/
  `--mcp-url`) — this tests the actual agent employees connect to, not a
  locally reimplemented stand-in whose behavior can drift out of sync with
  the real tool. Needs Python >=3.10 — see `example_project/README.md`.
- **`example_project/`** — a real-world-shaped consumer of the CLI: its own
  example quiz YAML and a README showing the actual install/run flow. This
  is the only place example data lives.

## Quickstart (using the bundled example)

```bash
cd example_project
uv python install 3.11                                       # one-time; honest-agent needs Python >=3.10
uv sync --python 3.11                                         # installs honest-agent, editable, from ../cli
uv run python warehouse/seed.py                               # seeds warehouse.duckdb from DuckDB's TPC-H generator
export ANTHROPIC_API_KEY=...                                 # or put it in a .env at the repo root -- auto-loaded
uv run honest-agent run --quizzes-dir quizzes \
  --mcp-command "$(pwd)/.venv/bin/python mcp_server/server.py"
uv run honest-agent report                                     # writes the web report to honest_agent_report/
uv run honest-agent serve                                      # opens the report in your browser, like `dbt docs serve`
uv run honest-agent notify --webhook-url ...                   # Slack alert on regressions
```

This calls Claude with the `query_warehouse` tool sourced live from the
bundled demo MCP server (`mcp_server/server.py`), against a real seeded
TPC-H warehouse — real SQL, real data, real provenance checking (does the
agent's SQL actually hit the table we expect). By default results land in
`./honest_agent_results/results.duckdb`. Run `honest-agent export --s3-path
s3://...` afterward if you want a Parquet snapshot in S3 too — see
`example_project/README.md` for details, including how to point at a real
MCP server (MotherDuck, Snowflake, or your own) instead of the bundled demo
one, and `example_project/quizzes/example_quiz.yml` for how each quiz
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
