---
title: What are evals for agentic analytics?
description: How to test an AI analytics agent with questions you know the answers to, checking both the answer and where it came from.
---

**Evals for agentic analytics** are tests for an AI agent that answers business questions
from your data: a set of questions with known right answers, asked again and again, to
check that the agent's answers are right and that they come from the right sources.

An analytics agent turns a business question into SQL (text-to-SQL), runs it against your
warehouse through tools (often an MCP server), and turns the result into an answer. Your team acts on that answer. When it's
wrong, nothing looks wrong: the agent sounds just as sure. Evals are how you find out
before your team does.

Because the questions stay the same, evals also show what changes around them:

- **Drift:** an agent that was right last month and is wrong today, because the model,
  its tools or the data changed.
- **Differences between models:** the same questions, asked with different models, show
  which one answers right, from the right sources.

## Two checks: accuracy and provenance

A good answer has to pass two checks.

- **Accuracy:** is the answer right? The number, name or list matches the answer you know
  is right.
- **Provenance:** did the answer come from the right place? The agent's SQL read the
  sources your team trusts for that question: the curated tables or views, not raw ones.

You need both, because each catches mistakes the other misses:

| Accuracy | Provenance | What it means |
|---|---|---|
| Right | Right | The answer is right, for the right reason. |
| Wrong | Right | The right source, but a wrong filter, join or date range. Or the agent only looked at the right source, then answered from another. |
| Right | Wrong | Right by luck: a raw or stale source happened to match today. It breaks when the data changes. |
| Wrong | Wrong | The agent didn't find the right data. |

The third row is the one accuracy alone can't see. An answer from a deprecated source or a
hand-written join can match today and drift next month. Checking provenance catches it
while it still looks right.

## How answers are graded

Text-to-SQL benchmarks often grade the SQL an agent writes, or the rows it returns.
honest-agent grades what your team sees: the final answer, and the sources behind it.

An analytics answer is usually a number, a name or a short list, written in a sentence.
honest-agent has three ways to grade accuracy, picked by the shape of the right answer:

| Method | How it grades | Best for | Model call |
|---|---|---|---|
| `contains` | The expected text appears in the answer, character by character (case is ignored) | Names and labels written one way | None |
| `extract_match` | A model pulls out the final answer's one value; code compares it, with an optional tolerance for numbers | One value: a number however it's formatted or rounded, or a name | One per eval |
| `llm_judge` | A model compares the answer with the expected one and scores it from 0 to 1, with a reason | Lists, explanations, answers that need judgment | One per eval |

Each method has its tradeoffs: read [Writing evals](/docs/writing-evals/#grading-accuracy)
before you pick one. Provenance is always checked by code, from the SQL the agent ran.

## Golden questions: what to test

Your eval set is made of questions you know the answers to, from a source you trust (also
called *golden questions*, or a *golden set*). The best ones are the questions people really ask:

- the questions your team asks the agent, or an analyst, most often;
- the headline numbers on the dashboards people rely on;
- the most frequent queries in your warehouse's query history.

Write each question as people ask it, vague wording included. Provide the expected answer
yourself, deciding what the business means. Never copy it from your agent: the eval would
only check that the agent agrees with itself. Start with 5 to 10. See
[What to evaluate](/docs/writing-evals/#what-to-evaluate).

## Run them like regression tests

An agent that was right last week can be wrong today. The model changes, someone edits a
table or a view, a tool's description changes. Evals catch that only if they run again:

- **Run them on a schedule,** daily for example, and after every change to the agent, its
  tools or its data model.
- **Give each eval a threshold** for accuracy and for provenance. `honest-agent run` exits
  with 1 when any eval falls below, like a failing test, so CI can catch it.
- **Watch the trend.** The report shows each eval's scores over time, so you see when a
  regression started, and that the fix worked.
- **Alert the team.** `honest-agent notify` posts to Slack when an eval falls below its
  threshold.

## An example eval

```yaml
version: 1

evals:
  - category: sales
    grading:
      method: extract_match
      min_score: 0.8              # the accuracy threshold
    provenance:
      min_score: 0.7              # the provenance threshold
    tests:
      - id: revenue_q4
        title: Revenue in Q4 2026
        prompt: What was our revenue in Q4 2026, net of discounts and before tax?
        expected_answer: "307992639.49"
        provenance:
          expected_sources: [lineitem, warehouse.main.orders]
```

honest-agent asks the question with the model you choose, using the tools from your
agent's own MCP server, then grades the answer and checks the SQL it ran. With the eval
above, if the agent answers with a revenue figure that doesn't match the expected one, and
reads only `lineitem`, accuracy is 0 and provenance is 0.5: it read one of the two expected
sources. Both are below their thresholds, so the eval fails.

## What it doesn't check

- **Provenance sees what was read, not what was used.** It shows every source the agent's
  SQL read during the run, not which query produced the answer: a quick
  `select * from orders limit 5` while exploring counts as reading `orders`.
- **Provenance sees SQL.** If your agent answers through tools with structured arguments
  and no SQL, provenance can't be checked for those evals.
- **It tests the model and the tools, not your app.** honest-agent asks the question with
  the model and the MCP tools your agent uses, plus the instructions the MCP server sends
  when it connects (as Claude's own clients do). Your agent's own system prompt, memory or
  conversation history aren't part of the run.
- **A passing eval set isn't proof.** It covers the questions you wrote. Add an eval each
  time the agent gets a real question wrong.

## Try it

honest-agent is open source (MIT) and runs from the command line. `honest-agent init
--example` sets up a demo agent over DuckDB's sample data with six evals, some failing on
purpose, runnable with only a model API key. Start with
[Getting started](/docs/getting-started/), or see [a demo report](/report/).
