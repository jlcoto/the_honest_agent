---
title: The report
description: Build the report, open it, and read what each page shows.
---

The report is a small website built from your results. It has three pages: the
**Overview** of one agent and model, **Model comparison**, and a page for each **result**.

## Build it and open it

```bash
uv run honest-agent report    # writes the report to honest_agent_report/
uv run honest-agent serve     # opens it in your browser (Ctrl+C to stop)
```

- `report` includes the results from the 30 days before your latest run. To go further
  back, pass any number of days with `--days`, e.g. `--days 90` or `--days 365`. Results outside the window
  stay in the results store; they're just left out of the report.
- `serve` publishes the report at `http://127.0.0.1:8000/` and opens your browser.
  `--port` picks another port, and `--no-open-browser` skips opening it.
- `--out <folder>` writes or serves another folder. `report` only writes into a new or
  empty folder, or one it wrote before, because it clears the old files there.

:::caution[A longer window makes a heavier report]
The report puts everything in its window into one data file, including every agent
conversation and tool result, and your browser loads it all when the report opens. Many
runs over a long window make that file large and the report slow to open.
:::

The report folder is a static website: it works on any static host. To share it with
your team, see [Running it for a team](/docs/team/).

## How scores are shown

Every score is from 0% to 100%, and coloured by how close it is to right:

| Colour | Score |
|---|---|
| Green | 95% or more |
| Yellow | 75% to 95% |
| Orange | 40% to 75% |
| Red | below 40% |

The **Combined** score is the average of accuracy and provenance. For an eval whose
provenance isn't checked, it's the accuracy alone.

A colour is about the score, not the threshold: an eval passes or fails by its own
`min_score` values. "Passed thresholds" and "Below threshold" count those.

## Overview

![The Overview page: score cards, a heatmap of scores by run, and the evals below threshold](/assets/review-overview.webp)

The Overview shows one agent and one model. Pick them, and the dates, at the top right.

- **The cards** show the latest run's combined, accuracy and provenance scores, each with
  the change since the previous run and a small trend, and how many evals passed their
  thresholds.
- **Scores by eval run** has one row per eval, grouped by category, and one column per run.
  Switch between Combined, Accuracy and Provenance at the top right. Click a cell to open
  [that result](#a-result).
- **Below threshold** lists the latest run's failing evals: their scores, what was
  expected and what the agent said, and which check failed. Export it as CSV with the
  button at the top right.

## Model comparison

![The Model comparison page: results by model, a heatmap by model, and scores over time](/assets/review-compare.webp)

Model comparison shows how different models do as the same agent. The baseline is the
model of the agent's most recent run; the others show their difference from it, in
percentage points, on the evals both ran.

- **Results by model** shows each model's latest run in the date range. Pick another run
  from its menu.
- **Scores by model** has one column per model. Grey cells are evals that weren't in that
  model's run.
- **Scores over time** has one row per model, with a point for its last run each day.

To compare models, run the same evals with each one:
`honest-agent run --model gpt-5.4-mini`. Keep the same `--grading-model` for every run, so
the grading is the same and the comparison is fair.

## A result

![A result page: the scores, the accuracy and provenance checks, the SQL calls and the trace](/assets/review-result.webp)

A result page shows why an eval passed or failed in a run: what the agent answered, how
that answer was graded, which tables it read, and the steps it took to get there.

- **The cards:** accuracy and provenance against their thresholds, the tokens the agent
  used, and how many steps it took out of the limit.
- **Accuracy:** what was expected and what the agent answered. For `extract_match`, the
  value the grader pulled out and the difference, against the tolerance; for
  `llm_judge`, the judge's score (under the answer) and its reason. "Show the agent's full
  reply" shows the whole answer.
- **Provenance:** each expected source, with the database, schema and table the agent
  read, or "not read".
- **SQL calls:** every query the agent sent, in order, and whether it ran or failed.
- **Trace:** the agent's steps, from the prompt to the final answer. Expand a step to see
  the tool call, what it returned, and its tokens and time.
- **Grading:** what the grading model did, for `extract_match` and `llm_judge`. "› Reply"
  opens its full reply, as it came back. Below it: how many tokens it spent thinking, its
  tokens and time, and how it stopped. A reply cut off at its token limit shows "Not
  graded" and "reached the token limit". `contains` calls no model, so the card says so.

For the raw records of every call, use
[`honest-agent logs`](/docs/running-evals/#find-out-why-an-eval-failed).

:::tip[Idea: investigate with a coding agent]
To find out why an eval failed, open a coding agent, like Claude Code, in your agent's
repository and give it the eval's log:

```bash
uv run honest-agent logs --eval-id revenue_q4 > revenue_q4.log
```

With the log and your agent's code side by side (its instructions, tool descriptions
and data models), the coding agent can trace where the answer went wrong and suggest a
fix. The log includes what your tools returned, so only share it with a coding agent
you'd trust with that data.
:::

:::caution[The report shows what the agent saw]
Result pages include what the agent's tools returned: query results, table listings,
error messages. Treat the report folder like the data your agent can query, and keep it
out of git. Host it only behind a sign-in.
:::
