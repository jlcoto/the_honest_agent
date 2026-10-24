---
title: Getting started
description: Install honest-agent, try the bundled example, and set up a project for your own agent.
---

honest-agent asks your analytics agent questions you know the answers to, through the
agent's own MCP server, and checks each answer for **accuracy** (is it right?) and
**provenance** (did the agent's SQL read the tables it should?).

## What you need

- **[uv](https://docs.astral.sh/uv/getting-started/installation/).** It installs Python
  for you if needed (honest-agent needs 3.10 or later).
- **A model API key.** honest-agent plays your agent with an AI model you choose: the
  model reads each question, decides which of your agent's tools to call, and writes the
  answer. Some grading methods use a model too. You pay the model provider for those calls, so you
  need an API key: `ANTHROPIC_API_KEY` for Claude
  ([console.anthropic.com](https://console.anthropic.com)) or `OPENAI_API_KEY` for GPT
  ([platform.openai.com](https://platform.openai.com/api-keys)). These are API keys,
  separate from a claude.ai or ChatGPT subscription.
- **Your agent's MCP server:** its URL and a token, or the command that starts it
  locally. To try honest-agent before connecting it, the [example](#2-try-the-example-optional)
  brings its own demo agent and sample database. It shows how honest-agent works, not how
  your agent does: for that, you need your agent's server.

## 1. Install

Create a folder for your evals and install honest-agent into it:

```bash
mkdir my-agent-evals && cd my-agent-evals
uv init --bare --python 3.11
uv add "honest-agent @ git+https://github.com/jlcoto/the_honest_agent.git@v0.2.0#subdirectory=cli"
```

To upgrade later, run the same `uv add` with a newer tag from
[Releases](https://github.com/jlcoto/the_honest_agent/releases).

To have one `honest-agent` command for every project instead, install it as a tool:

```bash
uv tool install "honest-agent @ git+https://github.com/jlcoto/the_honest_agent.git@v0.2.0#subdirectory=cli"
```

Then run `honest-agent` without `uv run` in any folder with a `honest_agent_config.yml`.
To upgrade, run the same command with the new tag and `--force`. The tradeoff: every
project uses the same version, instead of the one its `uv.lock` pins.

:::note[Alpha]
honest-agent is in alpha: expect breaking changes between versions. Each release's notes
in the [changelog](https://github.com/jlcoto/the_honest_agent/blob/main/CHANGELOG.md) say
what changed and what to do.
:::

## 2. Try the example (optional)

To see how a run works before connecting your own agent, try it on sample data:

```bash
uv run honest-agent init --example
```

It asks which model provider to use, then creates `honest-agent-example/`: a demo agent
over DuckDB's TPC-H sample data, with six evals. Some fail on purpose, and its
`README.md` says which ones and why. Then:

```bash
cd honest-agent-example
# add your API key to .env, e.g. ANTHROPIC_API_KEY=...
uv run honest-agent run       # a few cents with the example's model
uv run honest-agent report
uv run honest-agent serve     # opens the report in your browser (Ctrl+C to stop)
```

The demo MCP server is for trying honest-agent only, not for real data.

## 3. Create the starter files

Back in your project folder:

```bash
uv run honest-agent init
```

`init` asks a few questions with numbered options and defaults (Enter accepts them):

- which MCP server your agent uses: Snowflake's managed MCP server, MotherDuck, another
  URL, or a local command;
- its URL, or the command that starts it;
- which model provider runs the agent: Anthropic (Claude) or OpenAI;
- where results live: on your machine, in MotherDuck, or in a file in S3. Not sure? Keep
  the default, your machine; [Storing results](/docs/storing-results/) compares the three.

The target is named after the server (`snowflake`, `motherduck`, …); `--target-name`
chooses another name. Then it writes three files, and never overwrites one that exists:

| File | What it holds |
|---|---|
| `honest_agent_config.yml` | One target for your agent, like a target in a dbt profile |
| `evals/first_eval.yml` | A first eval to fill in |
| `.env` | The variables the setup needs: your server's URL, and empty slots for the keys |

Every answer is also a flag, for scripts and CI. For example:

```bash
uv run honest-agent init --server snowflake --mcp-url https://... --no-input
```

`honest-agent init --help` lists them all.

If the project is in git, add `.env` and `honest_agent_report/` to `.gitignore`; `init`
lists whatever isn't ignored yet. The results folder keeps itself out of git.

### With a coding agent

At the end, `init` asks whether to continue the setup with a coding agent (yes by
default). If you say yes, it adds a setup skill, in the open
[Agent Skills](https://agentskills.io) format, to `.agents/skills/` (read by Codex,
Cursor, Copilot, Gemini CLI and others) and `.claude/skills/` (Claude Code).

Open your coding agent in the project and ask it to set up honest-agent. It helps you
connect your MCP server and write your first evals, and asks before anything that costs
money. To add the skill later, or update it after upgrading honest-agent, run
`honest-agent init --with-skill`.

:::caution
Never paste tokens or keys into a coding agent's chat. They go in `.env`, which you
fill in yourself.
:::

## 4. Fill in `.env`

`init` wrote the variable names your setup needs. Add the values:

```bash
ANTHROPIC_API_KEY=...        # or OPENAI_API_KEY=...
SNOWFLAKE_MCP_URL=...        # your MCP server's URL
SNOWFLAKE_MCP_TOKEN=...      # its token
```

Only secrets and account URLs go here. The config reads them with
`{{ env_var('SNOWFLAKE_MCP_URL') }}`, the way dbt does, so `honest_agent_config.yml`
holds no account details and you can commit it to share targets with your team.
[Connect your agent](/docs/connect/) covers the other settings.

:::caution[Give the MCP server read-only credentials]
honest-agent runs your agent with every tool its MCP server offers, and the agent reads
your data, which can contain text written as instructions. honest-agent blocks SQL that
changes data: only reads (`select`, `show`, `describe`, `use`) reach the server. But it
can only check SQL. If the server has other tools that change things, such as one that
deletes a customer, honest-agent can't block them. Read-only credentials can.
:::

## 5. Write your first eval

Open `evals/first_eval.yml` and replace each `TODO`: a question your agent should answer
from your data, the answer you know is right, and the tables it should read. For example:

```yaml
    tests:
      - id: revenue_q4
        title: Revenue in Q4 2026
        prompt: What was our revenue in Q4 2026, net of discounts and before tax?
        expected_answer: "307992639.49"
        provenance:
          expected_sources: [lineitem, warehouse.main.orders]
```

`expected_answer` checks accuracy. `expected_sources` checks provenance: that the SQL the
agent ran actually read those tables. [Writing evals](/docs/writing-evals/) explains the
grading methods and how to choose the questions.

## 6. Check the setup, then run

```bash
uv run honest-agent debug
```

`debug` checks the config, the variables, the evals, the connection to the MCP server and
the results store, without calling a model or running a query. Fix whatever it reports,
then run.

:::caution[Each run costs money]
Every eval calls the model, and you pay the model provider for those calls. The cost
depends on the model, how many steps the agent takes for each question, and whether the
grading method calls a model too. Check your provider's prices
([Anthropic](https://www.anthropic.com/pricing#api),
[OpenAI](https://openai.com/api/pricing/)) and start with one eval:
`uv run honest-agent run --select <id>`. The report shows the tokens each eval used, so you can
estimate the rest. Your warehouse may also charge for the queries the agent runs.
:::

```bash
uv run honest-agent run       # runs every eval against the default target
uv run honest-agent report    # writes the report to honest_agent_report/
uv run honest-agent serve     # opens it in your browser (Ctrl+C to stop)
```

`run` exits with code 1 when any eval falls below its threshold, like a failing test.
[Running evals](/docs/running-evals/) covers selecting evals, reading the logs and
running in CI.

:::caution[Your results contain what the agent saw]
The results file (`honest_agent_results/results.duckdb`) keeps everything each run sent
and received, and the report holds the agent's conversations. That includes what its
tools returned: query results (possibly customer rows, names or emails), table listings,
and error messages that can name accounts and roles. Access tokens are never stored.
Treat both like the data your agent can query, and keep them out of git.
:::

## Next

- [Writing evals](/docs/writing-evals/): what to test and how to grade it.
- [The report](/docs/report/): reading the results.
- [Running it for a team](/docs/team/): runs in CI, a hosted report and Slack alerts.
