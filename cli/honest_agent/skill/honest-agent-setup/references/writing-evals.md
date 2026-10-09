# Writing evals

Evals live in `*.yml` files in the target's evals folder (`evals/` by default; see
`evals_dir` in `honest_agent_config.yml`). Full reference: "Writing evals", "How
provenance is checked" and "Choosing a grading method" in
https://github.com/jlcoto/the_honest_agent/blob/main/example_project/README.md.

## The format

```yaml
version: 1
evals:
  - category: sales                 # a group: its settings apply to its tests
    grading:
      method: extract_match
      min_score: 0.8                # accuracy threshold (default 0.8)
    provenance:
      min_score: 0.7                # provenance threshold (default 0.7)
    tags: [smoke]
    tests:
      # Computed 2026-10-01 with the team's revenue query; refresh it every month.
      - id: revenue_last_month
        title: Revenue last month
        prompt: what was revenue last month?
        expected_answer: "1284500.20"
        grading:
          tolerance_percent: 0.01   # within 1% counts as right
        provenance:
          expected_sources: [analytics.fct_revenue]

      # "Top customers" is deliberately vague: that's how people ask. The business
      # means the 5 customers with the most revenue this year.
      - id: top_customers
        title: Top customers
        prompt: who are our top customers?
        expected_answer: "Acme, Globex, Initech, Umbrella and Hooli (by revenue, this year)"
        grading:
          method: llm_judge         # overrides the group's method
        provenance:
          expected_sources: [analytics.fct_revenue, analytics.dim_customer]
```

- A test inherits its group's settings; its own win. `grading` and `provenance` merge
  key by key; `tags` add up.
- **Ids:** `id:` if given, else made from the title (`Revenue last month` becomes
  `revenue_last_month`). Ids must be unique within the evals folder. Suggest writing
  `id:`: rewording a title otherwise changes the id, and the eval loses its history.
- **Selecting:** `honest-agent run --select revenue_last_month` runs one eval;
  `--select tag:smoke`, `--select category:sales`; spaces mean OR, commas AND;
  `--exclude` leaves evals out. `honest-agent ls` lists ids, categories and tags.
- Every eval needs `expected_answer`. `expected_sources` is optional.

## The prompt

Write it the way the people who use the agent ask: their words, their shorthand,
their vagueness. Don't add "give me just the number" or define terms they wouldn't.
The eval exists to see how the agent copes with real questions.

When the question can be read more than one way ("last year": calendar or last full
year? "revenue": gross or net?), don't rewrite it. Ask the user what the business
means, write that into `expected_answer` (saying the reading, as in `top_customers`
above), use `llm_judge` so an answer that states its assumption can be weighed, and
add a comment that the ambiguity is on purpose.

## The expected answer

- It comes from the user: they know it, or they run a query you propose (or the
  trusted metric or report) and check the result. Never invent it, and never copy it
  from the agent's answer, even if the user suggests it: then the eval only checks
  the agent agrees with itself.
- Write numbers as the query returns them; use `tolerance` (an absolute difference)
  or `tolerance_percent` (0.01 = 1%) when rounding is fine.
- If the answer changes over time ("last month", "active customers"), keep the
  wording, note in a comment the date it was computed and how (as in
  `revenue_last_month` above), and tell the user it will need refreshing.

## The grading method

`contains` is the default when no method is set.

| The right answer is... | Method | Notes |
|---|---|---|
| An exact name or label | `contains` | Free and deterministic. Not for numbers: "4" is inside "400" |
| One number or value | `extract_match` | A model extracts the value; code compares it. Add a tolerance for rounded numbers |
| A list, an explanation, an ambiguous question, or needs judgment | `llm_judge` | A model scores 0 to 1 with a reason; the only one with partial credit |

## Provenance

Provenance checks that the agent's SQL read the sources it should. The score is the
share of `expected_sources` it read; below `provenance.min_score`, the eval fails.

- **Which source?** Ask the user which table, view or semantic view the team trusts
  for this question: the curated mart rather than raw tables, the semantic view
  rather than hand-written joins. That's a business decision; don't guess it from
  the schema.
- **Only what the answer needs.** Every entry must be read for full marks, so an
  extra one makes a correct answer fail. If any source is fine, leave
  `expected_sources` out: provenance then shows "not checked", never a pass.
- **Where it lives.** An entry is written like a table name in SQL: `orders`,
  `analytics.orders` or `prod.analytics.orders`. `provenance.expected_database` and
  `expected_schema` fill in the parts an entry leaves out. Bare names in the agent's
  SQL are placed by earlier `use` statements, else by the target's
  `default_database`/`default_schema`; without either, a bare name has no known
  location and won't match an expected database or schema.
- **What counts as reading:** a successful `select` (with `with`, `union`, ...).
  `show`, `describe`, catalog queries (`information_schema`, ...), failed queries and
  SQL a tool only generated (without running it) don't count. Any successful select
  does, even a quick `select * from t limit 5` while exploring.
- **Only SQL is seen.** A tool with structured arguments instead of SQL (a
  semantic-layer tool like `query_metrics(metric, grain)`) leaves nothing to read, so a
  correct answer through it scores 0. For such evals leave `expected_sources` out and
  tell the user their provenance can't be checked. A tool that keeps SQL in an unusual
  argument needs `provenance.sql_fields: {tool_name: argument}`.

## After writing

`honest-agent ls` confirms the evals load and shows their ids. `honest-agent debug`
checks everything before a run.
