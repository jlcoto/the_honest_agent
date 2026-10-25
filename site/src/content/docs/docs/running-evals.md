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
Starting eval run 7d2e41a0-3c55-4f0b-9a61-2b8e5d90c417 (4 evals)...
Evaluating agent: sales-agent
Model: claude-sonnet-4-5 · grading model: claude-sonnet-4-5
  - revenue_q4: 'What was our revenue in Q4 2026, net of discounts and before tax?'
  - order_total_2026: 'What was the total price of all the orders placed in 2026?'
  - top_segment: 'Which market segment has the most customers?'
  - top_nations_last_year: 'Which 5 nations placed the most orders last year?'
Wrote 4 result(s) to ./honest_agent_results/results.duckdb
2/4 eval(s) below threshold this run:
  - revenue_q4: accuracy 0.00 < 0.8, provenance 0.50 < 0.7
  - order_total_2026: provenance 0.50 < 0.7
Run 7d2e41a0-3c55-4f0b-9a61-2b8e5d90c417 complete. Next: `honest-agent report` / `honest-agent notify`.
```

- **Which agent:** `run` evaluates the config's `default_target`. `--target <name>` picks
  another one.
- **Which model:** the target's `model`, or `--model` for one run. `--grading-model` sets
  the grading model. See [Models](/docs/connect/#models).
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
it again. Start with one eval, check its tokens in the report, then run the rest.
:::

### Check first

`honest-agent debug` checks the config, the variables, the evals, the MCP server and the
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
