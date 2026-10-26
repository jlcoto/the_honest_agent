---
title: Running evals
description: Run your evals, pick which ones, and find out why one failed.
---

## Run

```bash
uv run honest-agent run
```

`run` asks every eval's question, grades each answer, and stores the results. It prints
each eval as it goes, then which ones fell below their thresholds:

```
Target: sales-agent (honest_agent_config.yml)
No --grading-model given; using claude-sonnet-5-5 (low effort), the default for Claude agents.
Starting eval run 7d2e41a0-3c55-4f0b-9a61-2b8e5d90c417 (4 evals)...
Evaluating agent: sales-agent
Model: claude-haiku-5-5 · grading model: claude-sonnet-5-5 (low effort)
  - revenue_q4: 'What was our revenue in Q4 2026, net of discounts and before tax?'
  - order_total_2026: 'What was the total price of all the orders placed in 2026?'
  - top_segment: 'Which market segment has the most customers?'
  - top_nations_last_year: 'Which 5 nations placed the most orders last year?'
Wrote 4 result(s) to ./honest_agent_results/results.duckdb
Estimated cost: $0.025 (agent $0.008 · grading $0.018)
2/4 eval(s) below threshold this run:
  - revenue_q4: accuracy 0.00 < 0.8, provenance 0.50 < 0.7
  - order_total_2026: provenance 0.50 < 0.7
Run 7d2e41a0-3c55-4f0b-9a61-2b8e5d90c417 complete. Next: `honest-agent report` / `honest-agent notify`.
```

- **Which agent:** `run` evaluates the config's `default_target`. `--target <name>` picks
  another one.
- **Which model:** the target's `model`, or `--model` for one run. `--grading-model` sets
  the grading model, and `--effort` and `--grading-effort` how much each thinks. See
  [Models](/docs/connect/#models).
- **The exit code:** `run` exits with 0 when every eval meets its thresholds, and 1 when
  any falls below, like a failing test. It also exits with 1 when the run itself fails,
  for example when the MCP server can't be reached. In CI, the job fails on a regression;
  [Run it in GitHub Actions](/docs/team/ci/) shows how to still publish the report and
  send the alert.
- **Step limit:** an agent gets 5 steps per question by default (a step is one model call
  and the tool calls it asks for). An eval that runs out fails with "hit the step limit
  without a final answer". Raise it with `max_tool_steps` in the config, at the top level
  or on a target, or with `--max-tool-steps` for one run (see
  [Other target settings](/docs/connect/#other-target-settings)).

:::caution[Each run costs money]
Every eval calls the model, and the grading methods `extract_match` and `llm_judge` call
it again. Start with one eval, check what it cost, then run the rest.
:::

### What a run costs

After the results are written, `run` prints an estimate of what the run cost, with the
agent and grading apart:

```
Estimated cost: $0.025 (agent $0.008 · grading $0.018)
```

It's an estimate: the token counts each call reports, times the provider's published
prices. Your provider's bill is the real figure.

- **The prices** come from a table in honest-agent, checked against
  [Claude's](https://platform.claude.com/docs/en/about-claude/pricing) and
  [OpenAI's](https://developers.openai.com/api/docs/pricing) pricing pages for each
  release. Nothing is downloaded during a run.
- **Each kind of token has its own price:** input, input read from the cache, input
  written to it, and output, which includes thinking. Each call is priced on its own, so
  a call over a model's long-prompt threshold (Claude Haiku 5.5 above 100k tokens) gets
  the higher rate.
- **Each result keeps its cost** at the prices of the day it ran, in the
  `agent_cost_usd` and `grading_cost_usd` columns. A later price change, or a
  `rebuild`, doesn't change it.
- **A model with no price** is named instead of counted as $0, for example a model behind
  a proxy or one newer than your honest-agent:

  ```
  Estimated cost: $0.008 for the agent · no price for the grading model my-proxy-model; add it under prices: in honest_agent_config.yml
  ```

#### Your own prices

Add a model, or override a built-in price (a negotiated rate, say), under `prices:` at
the top level of `honest_agent_config.yml`, in USD per million tokens:

```yaml
prices:
  my-proxy-model:
    input: 3.00
    output: 15.00
    cache_read: 0.30     # optional; without it, priced as input
    cache_write: 3.75    # optional; without it, priced as input
  claude-sonnet-5-5:
    input: 1.80
    output: 9.00
```

- **Each entry applies to the model with that name**, as the agent or as the grading
  model, so one file can list every model you switch between. An entry no run uses does
  nothing.
- **The name must match the model's**, ignoring case. A model id with a date on the end
  (`claude-sonnet-5-5-20261001`) also matches an entry without it.
- **Your entries come first,** then the built-in table. An entry has one flat rate, with
  no long-prompt rate.
- **To check which price applies,** run `honest-agent debug`. Its Prices line says where
  each model's price comes from, so a typo shows up before you spend anything:

  ```
  Prices         OK       claude-haiku-5-5 built-in (as of 2026-10-25) · my-proxy-model from honest_agent_config.yml
  ```

### Check first

`honest-agent debug` checks the config, the variables, the prices, the evals, the MCP server and the
results store, without calling a model or running a query. Run it after changing your
setup, before a run that costs money. If it reports a problem, see
[Troubleshooting](/docs/troubleshooting/).

## Select which evals run

`--select` picks evals, the way dbt does:

```bash
uv run honest-agent run --select revenue_q4                  # one eval, by id
uv run honest-agent run --select tag:critical                # every eval tagged critical
uv run honest-agent run --select category:sales              # every eval in a category
uv run honest-agent run --select "revenue_q4 top_segment"    # either one: a space means OR
uv run honest-agent run --select "category:sales,tag:critical"   # both: a comma means AND
uv run honest-agent run --exclude tag:slow                   # all but these
```

`--exclude` takes the same syntax and is applied after `--select`. A selector that matches
no eval is an error that names it, so a typo doesn't silently run nothing.

`honest-agent ls` takes the same options and lists what would run, with each eval's id,
category and tags, without running anything:

```bash
uv run honest-agent ls --select category:sales
```

## Find out why an eval failed

```bash
uv run honest-agent logs --eval-id revenue_q4
```

`logs` prints everything an eval sent and received, call by call: each model call, each
tool call with its SQL and what the warehouse returned, and each grading call, with its
timing. Use it to see where the agent went wrong.

- `--run-id <id>` shows one run only; without it, you get every run of that eval.
- `--json` prints the records exactly as stored, for scripts.

The [report](/docs/report/) shows the same run more readably, with scores and the SQL
the agent ran.

When an eval fails, it's usually one of these:

1. **The agent got it wrong.** That's a real finding: keep the eval, and fix the agent.
2. **The eval is off:** a wrong expected answer, or a grading method that doesn't fit the
   answer. Fix the eval.
3. **Provenance is too strict:** `expected_sources` lists a table the answer doesn't need.
   Remove it.
4. **Provenance can't see the tool:** the agent answered through a tool without SQL, so
   provenance scores 0. Remove `expected_sources` from that eval (see
   [Provenance only sees SQL](/docs/writing-evals/#checking-provenance)).

## Re-score past runs

```bash
uv run honest-agent rebuild
```

Every run keeps a full record of what was sent and received. After an upgrade that
changes how honest-agent scores or reads runs, `rebuild` re-scores your past runs from
those records. It calls no model, so it costs nothing. `--run-id <id>` rebuilds one run.

## Where results are stored

By default, in a DuckDB file in your project, `honest_agent_results/results.duckdb`. They
can also live in MotherDuck or in cloud storage: [Storing results](/docs/storing-results/)
compares the options.

:::caution[Your results contain what the agent saw]
The results keep everything each run sent and received, including what the agent's
tools returned: query results, table listings, error messages. Access tokens are never
stored. Treat them like the data your agent can query.
:::
