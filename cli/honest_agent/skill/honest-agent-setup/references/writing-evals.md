# Writing evals

Evals live in `*.yml` files in the target's evals folder (`evals/` by default; see
`evals_dir` in `honest_agent_config.yml`). Full reference, for you and the user:
https://thehonestagent.dev/docs/writing-evals/.

Use what follows as you need it for the eval at hand; don't recite it.

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
      # Computed 2026-10-01 with the team's revenue query, for September (the business
      # means the last full calendar month); refresh it every month.
      - id: revenue_last_month
        title: Revenue last month
        prompt: what was revenue last month?
        expected_answer: "1284500.20"
        grading:
          tolerance_percent: 0.01   # within 1% counts as right
        provenance:
          expected_sources: [analytics.fct_revenue]

      # By "top customers" the business means the 5 customers with the most
      # revenue this year.
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
above), and use `llm_judge` so an answer that states its assumption can be weighed.
When the business's reading is settled and the answer is one number, `extract_match`
is fine instead; say the reading in a comment, as `revenue_last_month` above does.

## The expected answer

- It comes from the user: they know it, or they run a query you propose (or the
  trusted metric or report) and check the result. Never invent it, and never copy it
  from the agent's answer, even if the user suggests it: then the eval only checks
  the agent agrees with itself.
- Write a number in one form: digits, "." for decimals, no thousands separators,
  currency or units (`1284500.20`, not "1,284,500.20" or "1.284.500,20 €"). A
  percentage is the number shown: 12 for 12%. Written another way, it is compared as
  text and never matches; `honest-agent ls`, `debug` and `run` warn about it. Use
  `tolerance` (an absolute difference) or `tolerance_percent` (0.01 = 1%) when
  rounding is fine.
- If the answer changes over time ("last month", "active customers"), keep the
  wording, note in a comment the date it was computed and how (as in
  `revenue_last_month` above), and tell the user it will need refreshing.

## The grading method

`contains` is the default when no method is set. Pick the method from the shape of
the right answer:

| The right answer is... | Method | Cost |
|---|---|---|
| A value the agent will write exactly one way: a name, a label, an ID, a year | `contains` | Free, no model |
| One number or value that may be formatted or rounded differently | `extract_match` | One model call per eval |
| A list, an explanation, an ambiguous question, or needs judgment | `llm_judge` | One model call per eval |

Say which method you picked in a few words. Mention a limit only if it matters for
this eval (for example, `contains` with a number the agent may format differently).
The limits, for when you need them:

- **`contains`**: the expected text must appear in the answer, character by character,
  ignoring case. "4" passes for "400 stores"; "1284500" fails for "1,284,500". Fine for
  names and labels, not for numbers.
- **`extract_match`**: a model pulls the one value out of the answer as a plain number
  ("$310.33 million" becomes 310330000), then code compares it. Without a tolerance the
  value must match exactly; agents often round big amounts, so prefer
  `tolerance_percent` (e.g. 0.005, within 0.5%) for those. It expects one value: for a
  list, use `llm_judge`.
- **`llm_judge`**: a model scores the answer from 0 to 1 against `expected_answer`, with
  a reason. It's only as strict as `expected_answer`: write what a right answer must
  contain ("Exactly these 5: …"). If `grading_model: llm_judge:` is a decision model
  (`jev-*`, `gemini-decision-*`, `decision:gpt-6-luna`), it gives pass/fail instead:
  pass when its P(yes) reaches `min_score`, with no reason.

## Provenance

If the user named a trusted table for the question, put it in `expected_sources`
(written like a table name in SQL: `orders`, `analytics.orders`). List only what the
answer needs: every entry must be read for full marks. If any source is fine, leave
`expected_sources` out. Don't explain more than that now: if provenance looks wrong
after a run, `references/reading-results.md` covers it.

## After writing

`honest-agent ls` confirms the evals load and shows their ids. `honest-agent debug`
checks everything before a run.
