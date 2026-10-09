---
name: honest-agent-setup
description: "Helps set up honest-agent in a project after `honest-agent init`: connect the agent's MCP server, decide what to evaluate, write the first evals (accuracy and provenance), check the setup with `honest-agent debug` and read the first results. Use when the user wants help setting up honest-agent or writing evals for it."
---

# Setting up honest-agent

honest-agent evaluates a data agent: it asks the agent known questions through the
agent's MCP server and checks each answer for **accuracy** (is it right?) and
**provenance** (did the agent's SQL read the sources it should?). `honest-agent init`
has written the project's files; your job is to help the user fill them in and get
to a first run. The user stays in charge: you explain, propose and write files they
approve; they decide what is right for their data.

## Rules that always apply

- **Credentials never go through the chat.** At the start, and whenever a token, key
  or password comes up, say: "Don't paste tokens, keys or passwords here. Put them in
  `.env` yourself; I only need the variable names." Never open `.env`, never write a
  secret value into any file, and never put one in `.env` for the user, even if they
  ask. If the user pastes one anyway, don't repeat it or use it; tell them to treat it
  as exposed, revoke it, and add a new one to `.env` themselves.
- **You never touch the user's warehouse.** Don't run queries, list tables or call the
  agent's MCP server, including through database or MCP tools your own session may
  have. When data is needed (which questions people ask, the right answer to one, which
  tables exist), propose a query for the user to run, or ask them, and work from what
  they choose to share.
- **Commands:** you may run `honest-agent ls`, `honest-agent logs`, `honest-agent
  debug` and `--help` without asking: they only read local files or check the setup
  (debug connects to the MCP server without calling a tool). Ask before every
  `honest-agent run`, even if the user said "just run it": it calls models (it costs
  money) and the agent queries the warehouse. Keep the question to one line (what runs,
  on which target and model). Never run `honest-agent notify` or `honest-agent init`;
  the one exception is suggesting `honest-agent init --with-skill` to update this
  skill. `honest-agent serve` keeps running, so give the user the command instead.
- **Edits:** show each change to `honest_agent_config.yml` or an eval file before
  writing it. Never edit `.env`; say which variable names it needs (they're in the
  config: `bearer_token_env`, `mcp_env`, `env_var('...')`).
- **Every step can be skipped,** except `honest-agent debug` before the first run,
  which is free. Say so when you start a step, and move on when the user wants to.

## Steps

### 1. Check the starting point

Check that `honest_agent_config.yml`, an evals folder (usually `evals/`) and `.env`
exist, without opening `.env`. If they're missing, `honest-agent init` hasn't run
here: ask the user to run it in their terminal, and stop. Read the config to learn
the target(s), the MCP server (a local `mcp_command` or a remote `mcp_url`), the model
and where results go. Give the credentials warning, then a short plan of the steps
below, and ask where they want to start.

### 2. Connect the MCP server

honest-agent reaches the agent through the agent's own MCP server; it doesn't set
that server up. Explain what the user needs for their kind of server and point them
to the vendor's docs and to honest-agent's guides (see `references/connecting.md`).
Don't create servers, users, roles or tokens for them. On honest-agent's side, help
with the target in `honest_agent_config.yml` (`mcp_url` or `mcp_command`,
`bearer_token_env`, `mcp_env`, `default_database`/`default_schema`, `ignore_tools`)
and tell them which variable names go in `.env`. Recommend a read-only role.

### 3. Find what to evaluate

First ask: "Do you already know which questions your agent should be tested on? If
so, we can skip this and write the evals." If not, help them look: the questions
their team asks most, the dashboards and reports people rely on, and the warehouse's
query history. `references/finding-questions.md` has starting points for well-known
warehouses; they are pointers to check against the vendor's docs, not guaranteed SQL.
Propose a query, the user runs it and shares what they choose. They decide what
matters.

### 4. Write evals, one at a time

Offer to skip ("Would you rather write the evals yourself?"). Otherwise take the
questions one by one: work through each together, show the YAML, write it once
approved, then ask "Another eval, or move on?" (or, if the user gave a list, "Next:
<question>. Ready?"). Suggest about 5 to 10 for a first round, covering different
kinds of questions, but follow the user's pace. Replace the TODO placeholder eval that
`init` wrote in `evals/first_eval.yml` with the first real one; never leave it, or a
full run fails on it. The format and the details are in `references/writing-evals.md`;
the essentials:

- **The prompt is the question as users really ask it,** ambiguity included: "last
  year", "top customers", "active". That's what the eval should test. Don't make it
  clearer. If it's ambiguous, ask the user what the business means, write that reading
  into `expected_answer`, use `llm_judge` (it can weigh an answer that states its
  assumption; `extract_match` is fine when the reading is settled and the answer is
  one number), and add a comment that the ambiguity is deliberate.
- **The expected answer comes from the user:** they know it, or they run a query you
  propose (or the trusted metric or report) and check the result. Never invent it,
  and never take it from the agent's own answer, even if the user suggests it: the
  eval would only check that the agent agrees with itself. If it changes over time
  ("last week", "active customers"), note in a comment the date it was computed and
  how, and tell the user it will need refreshing.
- **The grading method fits the answer:** `contains` (the default) for an exact name
  or label, `extract_match` for one number or value (with `tolerance` or
  `tolerance_percent` if it's rounded), `llm_judge` for lists, explanations,
  ambiguous questions or answers that need judgment.
- **Provenance is half the check.** Ask which source the team trusts for this
  question (the curated table or view, the semantic view) and put it in
  `expected_sources`. List only what the answer truly needs: every entry must be
  read for full marks, so an extra one makes a correct answer fail. If any source is
  fine, leave `expected_sources` out and provenance isn't checked. If the same name
  exists in several databases or schemas, pin the location.
- **Provenance only sees SQL.** If the trusted source is reached through a tool with
  structured arguments instead of SQL (e.g. `query_metrics(metric, grain)`; ask the
  user which tools their agent uses, or look at the tool calls in `honest-agent logs`
  after the first run), a correct answer would still score 0. Leave `expected_sources`
  out for that eval and tell the user plainly that its provenance can't be checked.
- **Suggest an explicit `id:`** so rewording the title later keeps the eval's
  history. The id is also how one eval is run alone (`--select <id>`).

### 5. Check the setup, then the first run

When the evals are written, run `honest-agent debug`: it checks the config, the
variables, the evals, the MCP connection and the results store, without calling a
model or querying the warehouse. Help fix whatever fails and run it again.

Then `honest-agent ls` to show what would run. Ask before running, and start with one
eval (`honest-agent run --select <id>`): it catches setup problems for the price of
one eval. Each eval costs model calls, more when the agent takes many steps or the
eval uses a model grader; after the first one, the report shows its tokens, so the
user can judge the rest. Then run the others (`honest-agent run`, or `--select` by
`tag:` or `category:`), asking again.

### 6. Read the results

For each eval below its threshold, find out why: `honest-agent logs --eval-id <id>`
shows every call the agent and the grader made. Tell apart four cases and say which
it is:

1. **The agent got it wrong:** a real finding. Keep the eval; the fix belongs in the
   agent. If the user wants to loosen it, explain that it would hide the problem.
2. **The eval is off:** a wrong expected answer, or a grading method that doesn't fit.
   Fix the eval.
3. **Provenance is too strict:** a source in `expected_sources` the answer didn't
   need. Remove it.
4. **Provenance can't see the tool:** the agent used a structured, non-SQL tool.
   Remove `expected_sources`; don't present the 0 as a finding.

Give the user `honest-agent report` and `honest-agent serve` to see everything in
their browser.

## Updating this skill

This folder is written by honest-agent; don't edit it. After upgrading honest-agent,
`honest-agent init --with-skill` replaces it with the matching version.
