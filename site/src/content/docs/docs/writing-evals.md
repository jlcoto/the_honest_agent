---
title: Writing evals
description: What to test, how to word the question, and how to grade the answer.
---

An eval is a question you know the right answer to. honest-agent asks it, then checks
two things: whether the answer is right (**accuracy**) and whether the agent's SQL read
the tables it should (**provenance**).

## The eval file

Evals live in `.yml` files in the target's evals folder (`evals/` by default). A file
groups evals into categories:

```yaml
version: 1

evals:
  - category: sales
    grading:
      method: extract_match
      min_score: 0.8              # the accuracy threshold
    provenance:
      min_score: 0.7              # the provenance threshold
    tags: [critical]
    tests:
      - id: revenue_q4
        title: Revenue in Q4 2026
        prompt: What was our revenue in Q4 2026, net of discounts and before tax?
        expected_answer: "307992639.49"
        provenance:
          expected_sources: [lineitem, warehouse.main.orders]

  - category: customers
    tests:
      - id: top_segment
        title: Market segment with the most customers
        prompt: Which market segment has the most customers?
        expected_answer: BUILDING
```

| Field | What it is |
|---|---|
| `id` | A short name for the eval, unique in the folder. Optional, but recommended: see below. |
| `title` | A readable name, shown in the report. |
| `prompt` | The question, as your users would ask it. |
| `expected_answer` | The right answer. Required. |
| `grading` | How accuracy is checked: `method`, `min_score`, and a tolerance for numbers. |
| `provenance` | What the agent should read: `expected_sources`, `min_score`. |
| `tags` | Labels for selecting evals, like `critical` or `smoke`. |

- **Settings flow down.** A test inherits its category's `grading`, `provenance` and
  `tags`; its own settings win, key by key. Tags add up.
- **Thresholds.** An eval fails when its accuracy score is below `grading.min_score`
  (0.8 by default) or its provenance score is below `provenance.min_score` (0.7 by
  default).
- **Ids.** Without an `id`, honest-agent makes one from the title:
  `Revenue in Q4 2026` becomes `revenue_in_q4_2026`. Set `id` yourself, so rewording the
  title later doesn't change the id and split the eval's history. The id is also how you
  run one eval: `honest-agent run --select revenue_q4`.

`honest-agent ls` checks that your files load, and lists every eval with its id,
category and tags.

## What to evaluate

The best evals are the questions people really ask. Places to look, from least to most
effort:

1. **Ask the team** which questions they ask the agent, or an analyst, most often, and
   which ones would hurt most if the answer were wrong.
2. **Dashboards and reports** people rely on: each headline number is a question.
3. **Your warehouse's query history:** the most frequent queries, and the tables they
   read, show what the business looks at.

### Query history: where to look

These are starting points; check your vendor's docs for the details. Reading query
history often needs extra privileges.

- **Snowflake:** `snowflake.account_usage.query_history` (up to a year, with some delay),
  or the `information_schema.query_history()` table function (recent days only).
  `snowflake.account_usage.access_history` shows which tables each query read
  (Enterprise edition).
- **BigQuery:** the region's `INFORMATION_SCHEMA.JOBS` views, with the tables each job
  referenced.
- **Databricks:** the `system.query.history` system table, if system tables are enabled.
- **Amazon Redshift:** `sys_query_history`.
- **PostgreSQL:** the `pg_stat_statements` extension, if it's installed.

A useful first query groups recent successful `select`s by their text, or by the tables
they read, counts them and keeps the top 20 to 50. Then pick the questions that matter
to the business, and write each one as a person would ask it.

Start with 5 to 10 evals, covering different kinds of questions.

## Word the prompt as users do

Write the question the way the people who use the agent ask it: their words, their
shorthand, their vagueness. Don't make it clearer than they would. An eval exists to
see how the agent copes with real questions.

Many real questions can be read more than one way. "Last year" can mean the calendar
year or the last twelve months; "revenue" can be gross or net. Don't rewrite the
question to remove the ambiguity. Decide what the business means, and write that into
the expected answer. Then:

- use `llm_judge`, which can give credit to an answer that states its assumption; or
- if the reading is settled and the answer is one number, use `extract_match` and note
  the reading in a comment.

## The expected answer

- **It comes from you,** or from a source you trust: a query you check, the official
  metric or report. Never copy it from the agent's own answer: the eval would then only
  check that the agent agrees with itself.
- **Write numbers plainly:** digits, `.` for decimals, no thousands separators, currency
  or units. `307992639.49`, not `307,992,639.49 $`. A percentage is the number shown:
  `12` for 12%. A number written any other way is compared as text and will rarely
  match; `ls`, `debug` and `run` warn about it.
- **Answers that change over time,** like "last month" or "active customers", need
  refreshing. Note in a comment when and how you computed the answer:

```yaml
      # Computed 2026-10-01 with the finance team's revenue query. Refresh monthly.
      - id: revenue_last_month
        title: Revenue last month
        prompt: What was revenue last month?
        expected_answer: "1284500.20"
```

## Grading accuracy

Pick the method from the shape of the right answer. `contains` is the default.

| The right answer is | Method | Model call |
|---|---|---|
| A name, label or value written exactly one way | `contains` | None |
| One number or value, possibly formatted or rounded differently | `extract_match` | One per eval |
| A list, an explanation, or an answer that needs judgment | `llm_judge` | One per eval |

### `contains`

Passes when the expected text appears anywhere in the answer, ignoring case:
`Acme` passes for "Our top customer is ACME Corp."

:::caution[A character-by-character match]
`contains` only checks that the characters of the expected answer appear somewhere in
the reply. It doesn't understand numbers or meaning, so it can pass wrong answers and
fail right ones:

- `4` passes for "we have 400 stores", which is wrong;
- `Acme` passes for "it isn't Acme, it's Globex": it can't tell the final answer from a
  value mentioned in passing;
- `1284500` fails for "revenue was 1,284,500" and for "$1.28M", which are right.

Use it for names and labels written one way. For numbers, use `extract_match`.
:::

### `extract_match`

A model pulls the one value out of the answer and writes it as a plain number,
whatever the agent's format: "1.284.500,20 €" becomes `1284500.20`, and "$310.33 million"
becomes `310330000`. Then code compares it with the expected answer.

:::note[Not `exact_match`]
In other eval tools, `exact_match` compares the whole reply as text, with no model and no
tolerance. `extract_match` first has the grading model extract the value, then compares
it, optionally within a tolerance. It is close to "answer extraction" in lm-eval or
Inspect, which use a regular expression instead of a model.
:::

```yaml
        grading:
          method: extract_match
          tolerance: 0.01            # an absolute difference that still counts as equal
          # tolerance_percent: 0.01  # or a relative one: 0.01 = within 1%
```

- Without a tolerance, the value must be exactly right. Set one when the agent may round
  differently.
- **Agents often round big numbers:** "about $308 million" for `307992639.49`. An absolute
  `tolerance: 0.01` fails that. For amounts, prefer `tolerance_percent` (for example
  `0.005`, within 0.5%), and note in a comment what rounding you accept.
- It expects one value. If the answer lists several numbers, it may pick the wrong one:
  use `llm_judge` instead.
- Units are dropped: "12%" and "12" become the same value.

:::caution[Write the expected number one way]
The extracted value is always a plain number, so write `expected_answer` the same way:
an optional minus, digits, and `.` for decimals. `307992639.49` and `-12.5` work.
`307,992,639.49`, `$307992639.49` and `12%` don't: they're compared as text, never
match, and the tolerance doesn't apply. `ls`, `debug` and `run` warn when a number is
written another way. A code with leading zeros, like `007`, stays text on purpose.
:::

### `llm_judge`

A model compares the answer with the expected one and scores it from 0 to 1, with a
one-sentence reason. It's the only method with partial credit.

```yaml
      - id: top_nations_last_year
        title: Top 5 nations by orders last year
        prompt: Which 5 nations placed the most orders last year?
        expected_answer: "Germany, France, Brazil, Japan and Canada placed the most orders."
        grading:
          method: llm_judge
```

- It's only as strict as the expected answer. Write what a right answer must contain,
  and what would make it wrong: "Exactly these 5" is stricter than a plain list.
- An answer that hedges between several values scores 0, even if one of them is right.
- The score comes from a model, so a borderline answer may pass one run and fail the
  next. The reason it gives shows why.

Both `extract_match` and `llm_judge` use the same model: the target's `grading_model`, or
its `model` if none is set (see [Models](/docs/connect/#models)).

## Checking provenance

Provenance checks that the agent's SQL read the sources it should. List them in
`expected_sources`:

```yaml
        provenance:
          expected_sources: [lineitem, warehouse.main.orders]
```

The score is the share of the expected sources the agent read: reading one of these two
scores 0.5.

- **Use the source your team trusts** for this question: the curated table rather than
  raw ones, the semantic view rather than hand-written joins.
- **List only what the answer needs.** Every entry must be read for full marks, so an
  extra one makes a correct answer fail.
- **Leave `expected_sources` out** if any source is fine. The report then shows
  provenance as "not checked".
- **Name a table the way SQL does:** `orders`, `main.orders` or `warehouse.main.orders`.
  Add the database and schema when the same table name exists in several places.
  `expected_database` and `expected_schema` set them for every entry that leaves them
  out.

:::caution[Read doesn't mean used]
Provenance shows which tables the agent's SQL read, not how it used them. An agent can
run `select * from orders limit 5` just to see the columns, then compute its answer from
another table: `orders` still counts as read. And reading the right table doesn't mean
the query was right: a wrong filter or join gives a wrong number from the right source.
That's why every eval checks accuracy too. Provenance tells you where the answer could
have come from; accuracy tells you whether it's right.
:::

### What counts as reading a table

- A `select` that ran successfully counts, including one inside `with` or `union`, and
  including a quick `select * from orders limit 5` while exploring.
- `show`, `describe`, catalog queries (like `information_schema`) and queries that failed
  don't count.
- Some tools answer with SQL instead of data: Snowflake's Cortex Analyst writes a query and
  returns it without running it. That query counts only if the agent then runs it, for
  example through `query_warehouse`.
- **Short table names.** If an expected source names its database or schema, like
  `warehouse.main.orders`, honest-agent needs to know where each table the agent read
  lives. When the agent writes just `from orders`, it takes the location from a `use`
  statement the agent ran earlier, or from the target's `default_database` and
  `default_schema`. With neither, it can't tell which `orders` that was, and the source
  doesn't match. A plain `orders` in `expected_sources` matches any `orders`.

:::caution[Provenance only sees SQL]
honest-agent reads the SQL in the agent's tool calls: any argument named `sql`, `query`
or `statement`. If your agent answers through a tool with structured arguments instead,
like `query_metrics(metric, grain)`, there's no SQL to read, and a correct answer scores
0. Leave `expected_sources` out for those evals, and
[open an issue](https://github.com/jlcoto/the_honest_agent/issues/new) naming the tool,
so support for it can be added.

If a tool keeps its SQL in a differently named argument, name it in the eval:
`provenance.sql_fields: {run_query: statement_text}`.
:::

## Check your evals

```bash
uv run honest-agent ls      # do the files load? what are the ids?
uv run honest-agent debug   # is everything ready for a run?
```

Then run them: [Running evals](/docs/running-evals/).
