# agent_quiz

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

- **`cli/`** — the `agent-quiz` Python CLI. Owns every LLM call (running the
  quiz, LLM-judge grading, provenance scoring), the threshold checks, and
  everything else (Slack notifications, the static HTML report). Results
  storage is a local DuckDB file by default; `agent-quiz export` can push a
  Parquet snapshot to S3 (via DuckDB's own `httpfs` extension) for sharing
  with a team, but that's an explicit, optional step. Two agent backends:
  `--agent-backend claude` (default,
  tools defined in quiz YAML, executed locally) or `--agent-backend mcp`
  (tools sourced live from an MCP server, for testing the actual agent
  employees connect to — needs the `mcp` extra, Python >=3.10, see
  `example_project/README.md`).
- **`example_project/`** — a real-world-shaped consumer of the CLI: its own
  example quiz YAML and a README showing the actual install/run flow. This
  is the only place example data lives.

## Quickstart (using the bundled example)

```bash
cd example_project
uv sync                                                      # installs agent-quiz, editable, from ../cli
export ANTHROPIC_API_KEY=...                                 # or put it in a .env at the repo root -- auto-loaded
uv run agent-quiz run --quizzes-dir quizzes_claude --agent-backend claude  # calls Claude directly, no MCP server needed
uv run agent-quiz report                                     # static HTML dashboard
uv run agent-quiz notify --webhook-url ...                   # Slack alert on regressions
```

This runs the lightweight `quizzes_claude/` example (a local `calculator`
tool, no MCP server or warehouse needed). By default results land in
`./agent_quiz_results/results.duckdb`. Run `agent-quiz export --s3-path
s3://...` afterward if you want a Parquet snapshot in S3 too — see
`example_project/README.md` for details.

`agent-quiz run` with no `--quizzes-dir`/`--agent-backend` defaults to
`quizzes/` + `--agent-backend claude`, which won't work as-is: `quizzes/`
is an MCP-only example (no `tools:` block, so the claude-direct backend
would have nothing to call) — it needs `--agent-backend mcp
--mcp-command ...` instead. See `example_project/README.md` for the full
MCP setup (real SQL/data provenance against a seeded warehouse), and
`example_project/quizzes/example_quiz.yml` for how each quiz declares its own
accuracy/provenance thresholds (`grading.min_score` / `provenance.min_score`).

## Developing the CLI

```bash
cd cli
uv sync --all-extras     # base deps + test + mcp (mcp needs Python >=3.10;
                          # uv picks a suitable interpreter, or pass --python 3.11)
uv run pytest -q
uv run agent-quiz --help
```
