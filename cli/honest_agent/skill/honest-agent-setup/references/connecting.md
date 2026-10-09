# Connecting honest-agent to the agent's MCP server

honest-agent talks to the same MCP server the agent uses. Setting that server up
(creating it, its users, roles and tokens) is the user's job, done with the vendor's
docs. Your part: explain what's needed, point to the right docs, and fill in
honest-agent's side. Never ask for or handle a token's value.

honest-agent's guides live in the repository's `example_project/README.md`
(https://github.com/jlcoto/the_honest_agent/blob/main/example_project/README.md):
"The config file", "Where bare table names run", "Pointing at a real MCP server",
"Connecting to a real MotherDuck account" and "Connecting to a real Snowflake account".

## Advice for every server

- **Read-only credentials.** honest-agent runs the agent with every tool its server
  offers. It refuses SQL that isn't a read (select, show, describe, use) before it
  reaches the server, but it only sees SQL: a tool like `delete_customer(id)` isn't
  checked. A read-only role or token is the real protection.
- **Secrets stay in `.env`.** For a remote server, `init` writes the target with
  `mcp_url: "{{ env_var('<TARGET>_MCP_URL') }}"` and `bearer_token_env:
  <TARGET>_MCP_TOKEN` (e.g. `SNOWFLAKE_MCP_URL`, `SNOWFLAKE_MCP_TOKEN`), and puts both
  names in `.env`. The user fills in the values; `.env` stays out of git.
- **Check with `honest-agent debug`**: its "MCP server" line connects and lists the
  server's tools without calling any.

## By kind of server

- **A local server started by a command** (`mcp_command`): the command runs from the
  config file's folder. It gets only a minimal environment plus the variables listed
  in the target's `mcp_env`, so a server that needs a token from `.env` must list its
  name there.
- **Snowflake managed MCP server** (`mcp_url` + `bearer_token_env`): the user creates
  an MCP server object and a programmatic access token (PAT) for a read-only role.
  Snowflake requires a network policy on the user before it issues a usable PAT.
  honest-agent's "Connecting to a real Snowflake account" section walks through it.
  Snowflake docs: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp,
  https://docs.snowflake.com/en/sql-reference/sql/create-mcp-server and
  https://docs.snowflake.com/en/user-guide/programmatic-access-tokens and
  https://docs.snowflake.com/en/user-guide/network-policies.
- **MotherDuck** (its hosted server is `https://api.motherduck.com/mcp`; `init`
  pre-fills it in `.env` as `<TARGET>_MCP_URL`): a MotherDuck token, ideally a
  read-only (read scaling) one:
  https://motherduck.com/docs/key-tasks/authenticating-and-connecting-to-motherduck/read-scaling/.
  See honest-agent's "Connecting to a real MotherDuck account" section.
- **Any other server:** its own docs say how to reach it and authenticate. Fill in
  `mcp_url` (and `bearer_token_env` if it needs a bearer token) or `mcp_command`.

## Settings that affect provenance

- **`default_database` / `default_schema`:** where the server's connection runs a bare
  table name (`from orders`). Set them when the agent writes bare names, so evals can
  check where a table lives. They must match the connection; a wrong one attributes
  tables to the wrong place without warning.
- **SQL found in tool arguments:** honest-agent reads SQL from arguments named `sql`,
  `query` or `statement`. A tool that keeps SQL in another argument needs the eval's
  `provenance.sql_fields: {tool_name: argument}`; a tool whose `query` argument isn't
  SQL (a search term) goes in the target's `ignore_tools`. A tool with structured
  arguments (`query_metrics(metric, grain)`) has no SQL to read: provenance can't
  check evals answered through it.
