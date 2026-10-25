---
title: Connect your agent
description: Point honest-agent at your agent's MCP server, and choose the model.
---

honest-agent reaches your agent's data through the agent's own MCP server: the same
server, with the same tools, that your team's agent uses. It doesn't set that server up.
Creating the server, its users, roles and tokens is done with your vendor's docs; this
page covers honest-agent's side.

## Targets

`honest_agent_config.yml` holds one **target** per agent you evaluate, like a target in a
dbt profile. `init` writes the first one. For a remote server it looks like this:

```yaml
default_target: sales-agent

targets:
  sales-agent:
    mcp_url: "{{ env_var('SALES_AGENT_MCP_URL') }}"
    bearer_token_env: SALES_AGENT_MCP_TOKEN   # names the variable in .env, never the token
    evals_dir: evals
```

- `honest-agent run` evaluates the `default_target`. `--target <name>` picks another one.
- Results record which agent they came from: the target's name, or its `agent_name` if
  you set one. The report lists agents by that name; you pick one at the top of the Overview.
- honest-agent finds the config file in the folder you run it from, or the nearest
  parent folder. Relative paths in it are relative to the file's folder.

### Secrets stay in `.env`

`{{ env_var('NAME') }}` reads a value from `.env` or your shell, the way dbt does, so the
config file holds no account details and you can commit it. `bearer_token_env` names the
variable that holds the server's token; the token itself never goes in the config.

```bash
# .env: keep it out of git
SALES_AGENT_MCP_URL=https://...
SALES_AGENT_MCP_TOKEN=...
```

- Quote the whole value in YAML (`"{{ env_var('...') }}"`).
- `{{ env_var('NAME', 'default') }}` gives a default when the variable isn't set.
- A variable that isn't set, with no default, stops only the target that reads it, with
  an error that names it.

## Remote servers: `mcp_url`

Set `mcp_url` to the server's address and, if it needs a bearer token, `bearer_token_env`
to the variable that holds it. honest-agent sends the token only to that target's server.

### Snowflake and MotherDuck

These have their own step-by-step guides, from creating the token to a first eval:

- [Connect to Snowflake](/docs/connect/snowflake/): a managed MCP server, with a
  programmatic access token for a read-only role.
- [Connect to MotherDuck](/docs/connect/motherduck/): MotherDuck's hosted server, with a
  read scaling token.

### Any other server

Its own docs say how to reach it and how to authenticate. Fill in `mcp_url`, plus
`bearer_token_env` if it takes a bearer token.

### Can't connect?

If your server isn't covered here, or you can't get it to connect,
[open an issue](https://github.com/jlcoto/the_honest_agent/issues/new) with the server you
use and the output of `honest-agent debug`. `debug` prints variable names, never their
values, but check what you paste anyway: no tokens, keys or private URLs.

## Local servers: `mcp_command`

For a server you start yourself, set `mcp_command` instead of `mcp_url`:

```yaml
targets:
  sales-agent-local:
    mcp_command: python my_mcp_server.py
    mcp_env: [WAREHOUSE_TOKEN]   # the variables from .env this server needs
    evals_dir: evals
```

- The command runs from the config file's folder.
- The server gets a minimal environment (`PATH`, `HOME` and similar) plus only the
  variables listed in `mcp_env`, never the rest of `.env`. A server that needs a token
  from `.env` must list it there.

## Models

honest-agent works with Anthropic (Claude) and OpenAI (GPT) models. You only need the API key for the
provider you use: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`.

```yaml
model: claude-sonnet-4-5        # for every target
targets:
  sales-agent:
    model: claude-sonnet-4-5    # or per target
    grading_model: claude-haiku-5-5
```

- **`model`** runs the agent. Without one, honest-agent picks a small, cheap model from
  the key it finds: `claude-haiku-5-5` if `ANTHROPIC_API_KEY` is set, otherwise
  `gpt-5.4-mini`. It prints which one it chose.
- **The provider comes from the name:** `gpt-*`, `o3`, `o4-mini` and similar are OpenAI;
  anything else is Claude.
- **`grading_model`** is the model for grading, for both methods that use one:
  `extract_match` has it pull the value out of the answer, `llm_judge` has it judge the
  answer. `contains` uses none. Without one, `model` grades too.

## Other target settings

| Setting | What it does |
|---|---|
| `max_tool_steps` | Steps the agent may take for each question before the eval fails. A step is one model call and the tool calls it asks for. Default: 5. Can also be set at the top level. |
| `agent_name` | The name results are recorded under. Default: the target's name. |
| `evals_dir` | The folder with this target's evals. Default: `evals`. |
| `default_database`, `default_schema` | Where the server runs a bare table name like `orders`, so provenance can tell where the table lives. Set them only if the server's connection really starts there: a wrong value puts tables in the wrong place without warning. |
| `ignore_tools` | Tools whose `sql`, `query` or `statement` argument isn't SQL (a search term, say), so provenance doesn't read it as SQL. MotherDuck's `search_catalog` is ignored already. |

`results_path`, where results are stored, is set at the top level only: every target's
results share one store, so one report covers every agent.

### When a setting is set in more than one place

A setting can come from four places. honest-agent uses the first one it finds, in this
order:

1. a flag on the command, like `--model claude-haiku-5-5`;
2. an environment variable, from `.env` or your shell, like `HONEST_AGENT_MODEL`;
3. `honest_agent_config.yml`;
4. honest-agent's own default.

So if the config says `model: claude-sonnet-4-5` but you run
`honest-agent run --model claude-haiku-5-5`, that run uses `claude-haiku-5-5`. The flag
changes only that one run; the config stays as it is.

When an environment variable overrides the config, `run` prints a note saying so. Keep
only secrets and account URLs in `.env`, so a leftover variable there doesn't override
your config without you noticing.

## Check the connection

```bash
uv run honest-agent debug
```

`debug` connects to the target's MCP server and counts its tools, without calling any. It
also checks the config, the variables, the evals and the results store. Use
`--target <name>` to check another target.

:::caution[Use read-only credentials]
honest-agent blocks SQL that changes data, but it can only check SQL. If the server has
other tools that change things, honest-agent can't block them. A read-only role or
token can.
:::
