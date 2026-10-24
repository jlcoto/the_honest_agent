---
title: Connect to MotherDuck
description: Evaluate an agent that uses MotherDuck's hosted MCP server.
---

:::caution[An example, not a security review]
This is one setup we tested, shown as an example. Don't copy it blindly: check each step
against your company's security policies, and adapt it before you use it with real data.
See [Your setup, your responsibility](/docs/team/#your-setup-your-responsibility).
:::

MotherDuck hosts an MCP server at `https://api.motherduck.com/mcp`, the same one Claude,
Cursor and other clients connect to. Nothing runs on your machine. honest-agent connects to
it with a MotherDuck token, sent with each request to prove it's allowed in.

## 1. Get a read-only token

Besides `query`, the server offers `query_rw` and tools that create and delete dives,
flights and guides. With a read/write token, the agent under test could change or delete
things in your account. honest-agent blocks SQL that changes data, but it can't block those
other tools.

A [read scaling token](https://motherduck.com/docs/key-tasks/authenticating-and-connecting-to-motherduck/read-scaling/)
can't write: it connects to read replicas that reject writes. Create one in MotherDuck,
under Settings → Access Tokens, for the account whose databases the agent reads.

- **Read replicas can lag** a few minutes behind the latest data. If you load data and run
  evals right after, an answer can be out of date.
- **No read scaling token?** Check your plan with MotherDuck. A read/write token works, with
  the risk above: use an account that only holds what the agent needs.

## 2. Run `init`

In the folder for your evals:

```bash
uv run honest-agent init --server motherduck
```

`init` fills in the server's URL and writes a `motherduck` target to
`honest_agent_config.yml`:

```yaml
targets:
  motherduck:
    mcp_url: "{{ env_var('MOTHERDUCK_MCP_URL') }}"
    bearer_token_env: MOTHERDUCK_MCP_TOKEN
    max_tool_steps: 10   # it explores databases and tables before it queries
    evals_dir: evals
```

`bearer_token_env` names the variable in `.env` that holds the token; the token itself never
goes in the config. Fill in `.env`: the token from step 1 goes in `MOTHERDUCK_MCP_TOKEN`, next
to your model's API key. Keep `.env` out of git.

```bash
MOTHERDUCK_MCP_URL=https://api.motherduck.com/mcp
MOTHERDUCK_MCP_TOKEN=...
ANTHROPIC_API_KEY=...
```

## 3. Check the connection

```bash
uv run honest-agent debug
```

The "MCP server" line should connect and count the server's tools: about 45 when we tested
it. If it can't connect, check that the token is in `MOTHERDUCK_MCP_TOKEN` and hasn't been
revoked.

## 4. Write a first eval

Pick a question with an answer you can check yourself: run the query in MotherDuck first,
and use its result as `expected_answer`. Every MotherDuck account has the
[`sample_data`](https://motherduck.com/docs/getting-started/sample-data-queries/datasets/)
database, so you can start there before using your own tables:

```sql
select count(*) from sample_data.kaggle.movies;
```

Then edit `evals/first_eval.yml`, with your result in `expected_answer`:

```yaml
version: 1

evals:
  - category: first
    grading:
      method: extract_match
      min_score: 0.8
    provenance:
      min_score: 0.7
    tests:
      - id: movie_count
        title: Movies in the Kaggle sample
        prompt: How many movies are in the Kaggle movies dataset in sample_data?
        expected_answer: "<your result>"
        provenance:
          expected_sources: [sample_data.kaggle.movies]
```

```bash
uv run honest-agent run
```

See [Writing evals](/docs/writing-evals/) for more questions, and the other grading methods.

## Cost: more tokens per eval

The server describes all its tools to the model on every call, and the agent explores
databases, tables and columns before it queries. In our tests an eval used about 75k to
140k input tokens, against about 7k with honest-agent's demo server. That's also why `init`
sets `max_tool_steps: 10`: in our tests, the default of 5 was too few for the agent to
answer. Start with a few evals and a cheap model, and check the cost on your provider's
dashboard.

The tool descriptions and the server's instructions are the same in every call, so
honest-agent asks the provider to cache them: with Claude, calls after the first in a run
read them at a tenth of the input price. `agent_input_tokens` still counts them; the cached
part is in `agent_cache_read_tokens`.

## MotherDuck's local server

MotherDuck also publishes a local server,
[`mcp-server-motherduck`](https://github.com/motherduckdb/mcp-server-motherduck), that you
start with a command. Use it if your team's agent does:

```yaml
targets:
  motherduck_local:
    mcp_command: uvx mcp-server-motherduck --db-path md:analytics
    mcp_env: [MOTHERDUCK_TOKEN]   # the server gets only these variables from .env
    evals_dir: evals
```

Without a read scaling token it needs `--read-write`, with the same risk as above. See
[Local servers](/docs/connect/#local-servers-mcp_command).

Still stuck? [Open an issue](https://github.com/jlcoto/the_honest_agent/issues/new) with the
output of `honest-agent debug`. It prints variable names, never their values, but check what
you paste anyway: no tokens, keys or private URLs.
