# Changelog

honest-agent is in alpha: a minor version (0.1 -> 0.2) can break things, and
its notes start with what changed and what to do. A patch version (0.1.0 ->
0.1.1) only fixes bugs.

## Unreleased

- **A stronger default grading model, never the agent's own.** Without `grading_model`,
  grading used the agent's model, so an agent graded its own answers. Now the default is
  a stronger model from the agent's provider, at low effort: `claude-sonnet-5-5` for
  Claude agents, `gpt-6.1-sol` for OpenAI ones. Grades can change for runs that relied on
  the old default; set `grading_model` to keep grading with the same model as before.
  `run` and `debug` warn when the grading model is the agent's own model, or a lower
  tier of the same provider (Haiku below Sonnet below Opus, Luna below Sol below Astra).
- **The default OpenAI model is now `gpt-6-luna`** (was `gpt-5.4-mini`): about a ninth
  of the price, and newer. Set `model: gpt-5.4-mini` to keep the old one.
- **`effort` and `grading_effort`:** how much the agent's and the grading model think
  (`low`, `medium` or `high`), in the config file or with `--effort` and
  `--grading-effort`. Without `effort`, none is sent, as before. Both are stored with
  each result (`effort` and `grading_effort` columns), and the report shows a model run
  at an effort as its own model, such as `claude-haiku-5-5 · high`. Run
  `honest-agent rebuild` to add the columns to older results (empty there).

## v0.3.1 (alpha) — 2026-10-24

- **The Docker image is built for arm64 too** (`linux/amd64` and `linux/arm64`). The
  0.3.0 image is amd64 only; on Apple Silicon it needs `--platform linux/amd64`.

## v0.3.0 (alpha) — 2026-10-24

- **The default Claude model is now `claude-haiku-5-5`** (was `claude-haiku-4-5`),
  for the agent and the grading model when `--model` isn't set. It's 10x cheaper
  for prompts under 100k tokens. Runs that relied on the default now use another
  model, so their results can differ: set `model: claude-haiku-4-5` in
  `honest_agent_config.yml` to keep the old one.
- **A Docker image,** `ghcr.io/jlcoto/honest-agent:<version>`, for scheduled runs outside
  GitHub Actions (GitLab CI, Airflow, Kubernetes, ECS). It has honest-agent and uv, runs
  as a normal user, and is published on each release tag. See "Run it in a container" in
  the team docs.

## v0.2.0 (alpha) — 2026-10-21

- **The agent gets the MCP server's instructions.** Servers can send instructions when a
  client connects (MotherDuck's describe DuckDB's SQL and how to explore the catalog), and
  Claude's own clients put them in the model's context. honest-agent now sends them as the
  system prompt and stores them in the run's settings. Results can change for servers that
  send instructions: compare runs from before and after with that in mind.
- **Prompt caching.** The tools and the server's instructions are cached: with Claude, a
  cache breakpoint after them (reads cost a tenth of the input price); with OpenAI, a
  `prompt_cache_key` per run. Answers don't change, only the cost.
- **Cache tokens in results:** `agent_cache_read_tokens` and `agent_cache_write_tokens`.
  `agent_input_tokens` keeps counting every input token, cached or not. Run
  `honest-agent rebuild` to fill the new columns for older runs (0 there).

## v0.1.0 (alpha) — 2026-10-15

The first release for testers. Install it from the tag (see the README).
Documentation: https://thehonestagent.dev/docs/, with a demo report at
https://thehonestagent.dev/report/.

**What it does:** asks your analytics AI agent known questions through its
MCP server and checks each answer for **accuracy** (is it right?) and
**provenance** (did its SQL read the sources it should?).

- **Commands:** `init` (starter files, `--example` for a demo project that
  needs only a model API key), `debug` (checks the setup without calling a
  model), `ls`, `run`, `report`, `serve`, `logs`, `notify` (Slack) and
  `rebuild`.
- **Models:** Anthropic (Claude) or OpenAI, for the agent and the grading model.
- **Grading:** `contains`, `extract_match` (one number or value, with an
  optional tolerance) and `llm_judge`; per-eval thresholds for accuracy and
  provenance.
- **Selecting evals:** `--select` / `--exclude` by id, `tag:` or `category:`,
  like dbt.
- **Results:** a local DuckDB file or a MotherDuck database, with every model
  and tool call kept, so `logs` and `rebuild` work after the fact.
- **CI:** `run` exits 1 when any eval falls below its threshold.
  [Running it for a team](https://thehonestagent.dev/docs/team/) has recipes
  for GitHub Actions, shared results and hosting the report behind a sign-in.
- **Setup skill:** `init` can add a skill that helps a coding agent (Claude
  Code, Codex, Cursor and others) set up the project and write the first
  evals with you.
- **Safety:** only read-only SQL (`select`, `show`, `describe`, `use`) reaches
  the agent's MCP server; anything else is refused.

**Known limits:**

- No migrations yet: a results file from a later version may need a manual
  step, which its notes will explain.
- Provenance only sees SQL: an agent that reads data through structured,
  non-SQL tools can't have its sources checked.
- Each eval is one fresh question: no multi-turn conversations, and not the
  exact behaviour of a user's chat client (its own instructions and history).
- MCP servers are reached by URL with a bearer token, or started with a local
  command. Servers that only allow signing in through a browser (OAuth) aren't
  supported yet.
- Install from git only; not on PyPI yet.
