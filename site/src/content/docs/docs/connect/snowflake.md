---
title: Connect to Snowflake
description: Evaluate an agent that uses Snowflake's managed MCP server.
---

:::caution[An example, not a security review]
This is one setup we tested, shown as an example. Don't copy it blindly: check each step
against your company's security policies, and adapt it before you use it with real data.
See [Your setup, your responsibility](/docs/team/#your-setup-your-responsibility).
:::

This guide assumes your team already has a Snowflake MCP server, connected to Claude or
another client: that's the agent you want to evaluate. honest-agent connects to the same
server, as its own user, with a
[programmatic access token](https://docs.snowflake.com/en/user-guide/programmatic-access-tokens)
(PAT) sent with each request to prove it's allowed in.

- **OAuth**, which your team probably uses in Claude, isn't an option: it needs a browser to
  log in.
- **Key-pair authentication** (a PEM key) isn't supported by honest-agent, and Snowflake's
  [MCP server docs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp)
  only cover OAuth and PATs.

No MCP server yet? See [Don't have an MCP server yet?](#dont-have-an-mcp-server-yet) at the
end.

The SQL below has placeholders in angle brackets. Replace them with yours:

| Placeholder | What it is |
|---|---|
| `<mcp_database>`, `<mcp_schema>`, `<mcp_server>` | Where your MCP server lives, and its name. |
| `<database>`, `<schema>` | Where the tables the agent reads live. Step 3 also puts the network rule there; it can live in another schema. |
| `<warehouse>` | The warehouse that runs the agent's queries. |

The names the SQL creates, like the role `honest_agent_reader` and the user
`honest_agent_svc`, you can keep or rename. You'll need a role that can create roles, users
and network policies and grant access to the server, such as `securityadmin`.

## 1. Find your server

The URL honest-agent needs is the one your team entered when they added the server to
Claude. If you don't have it, find the server in Snowflake:

```sql
show mcp servers in account;
describe mcp server <mcp_database>.<mcp_schema>.<mcp_server>;
```

`describe` shows the server's tools. The URL follows this shape:

```
https://<account>.snowflakecomputing.com/api/v2/databases/<mcp_database>/schemas/<mcp_schema>/mcp-servers/<mcp_server>
```

Get `<account>` by running:

```sql
select current_organization_name() || '-' || current_account_name();
```

If it contains underscores (`_`), write them as hyphens (`-`): Snowflake's docs say MCP
connections have problems with underscores in the host name.

## 2. Create a read-only role and a service user

honest-agent can't log in as your team does, so it needs its own user. Give that user a
role that reads the same tables your team's role reads, so the agent sees the same data.
`show grants to role <team_role>;` lists what that role can read.

:::note[Why not your team's own role?]
Using it is the most faithful test, but it may be able to change data, and its PAT would be
a powerful secret in `.env` or your CI. A read-only role with the same `select` grants shows
the agent the same data with less risk. honest-agent blocks SQL that changes data, but a
read-only role is what makes sure it can't.
:::

```sql
create role honest_agent_reader;

grant usage on warehouse <warehouse> to role honest_agent_reader;
grant usage on database <database> to role honest_agent_reader;
grant usage on schema <database>.<schema> to role honest_agent_reader;
grant select on all tables in schema <database>.<schema> to role honest_agent_reader;
grant select on all views in schema <database>.<schema> to role honest_agent_reader;

-- the MCP server, and the database and schema it lives in
grant usage on database <mcp_database> to role honest_agent_reader;
grant usage on schema <mcp_database>.<mcp_schema> to role honest_agent_reader;
grant usage on mcp server <mcp_database>.<mcp_schema>.<mcp_server> to role honest_agent_reader;

create user honest_agent_svc
    type = service
    default_role = honest_agent_reader
    default_warehouse = <warehouse>;
grant role honest_agent_reader to user honest_agent_svc;
```

- **`type = service`** makes it a user for programs: it can't log in with a password.
- **`default_warehouse`** matters: the server's SQL tool runs queries on the user's default
  warehouse unless the server's spec names one (`describe` in step 1 shows it).
- **Several schemas?** Repeat the `usage` and `select` grants for each one your team's role
  reads.

**If the schema has semantic views**, the agent can query them too, but the grants above
don't cover them. Add:

```sql
grant select on all semantic views in schema <database>.<schema> to role honest_agent_reader;
```

**Objects created later:** these grants cover what exists today. To also cover tables,
views or semantic views created later, repeat them with `future` instead of `all`, e.g.
`grant select on future tables in schema ...`.

### Long-running queries

honest-agent stops waiting for a query after `tool_timeout` (120 seconds by default), and
the agent gets an error saying so. It asks the server to stop the query too, but can't
make sure the query stops in the warehouse. Make sure Snowflake ends long-running
queries; Snowflake's docs cover how to set a query timeout.

## 3. Add a network policy

Snowflake issues and accepts a PAT for a service user only if the user has a
[network policy](https://docs.snowflake.com/en/user-guide/network-policies). Allow only the
addresses honest-agent runs from: your machine, or your CI's (for GitHub Actions, see
[below](#running-in-github-actions)).

```sql
create network rule <database>.<schema>.honest_agent_ips
    type = ipv4
    mode = ingress
    value_list = ('<your_ip>/32');

create network policy honest_agent_policy
    allowed_network_rule_list = ('<database>.<schema>.honest_agent_ips');

alter user honest_agent_svc set network_policy = honest_agent_policy;
```

### Running in GitHub Actions

GitHub-hosted runners get a new address on almost every run, so the rule above can't list
them. There are two ways around that.

**Easy: Snowflake's GitHub Actions rule.** Snowflake maintains a
[network rule](https://docs.snowflake.com/en/user-guide/network-rules) with GitHub Actions'
addresses and keeps it up to date. Add it to the policy, next to your own addresses:

```sql
alter network policy honest_agent_policy add allowed_network_rule_list = (
    'snowflake.network_security.githubactions_global'
);
```

:::caution[It allows every GitHub Actions runner]
The rule covers all GitHub-hosted runners, from anyone's workflows, not only yours. It
applies only to this user, but the address check no longer keeps others out: the token,
the read-only role and the token's expiry do. Check that this fits your security rules.
:::

**Tight: send the job's traffic from a fixed address**, and allow only that one:

- a [larger runner with a static IP](https://docs.github.com/en/actions/concepts/runners/larger-runners),
  a paid GitHub feature;
- a self-hosted runner with a fixed outbound address;
- a VPN or proxy your team already runs, if it has a fixed outbound address.

## 4. Create a programmatic access token

```sql
alter user honest_agent_svc add programmatic access token honest_agent_token
    role_restriction = 'honest_agent_reader'
    days_to_expiry = 90;
```

- **Copy the token now:** Snowflake shows it only once.
- **`role_restriction`** is required for a service user: the token can only use that role.
- **It expires.** Without `days_to_expiry` a PAT lasts 15 days. When it expires, honest-agent
  can't connect until you create a new one and update `.env` (or your CI's secret).

## 5. Run `init`

In the folder for your evals:

```bash
uv run honest-agent init --server snowflake
```

`init` asks for the URL from step 1, then writes a `snowflake` target to
`honest_agent_config.yml`:

```yaml
targets:
  snowflake:
    mcp_url: "{{ env_var('SNOWFLAKE_MCP_URL') }}"
    bearer_token_env: SNOWFLAKE_MCP_TOKEN
    evals_dir: evals
```

`bearer_token_env` names the variable in `.env` that holds the token; the token itself never
goes in the config. Fill in `.env`: the token from step 4 goes in `SNOWFLAKE_MCP_TOKEN`, next
to your model's API key. Keep `.env` out of git.

```bash
SNOWFLAKE_MCP_URL=https://<account>.snowflakecomputing.com/api/v2/databases/...
SNOWFLAKE_MCP_TOKEN=...
ANTHROPIC_API_KEY=...
```

## 6. Check the connection

```bash
uv run honest-agent debug
```

The "MCP server" line should connect and count the server's tools, the same ones `describe`
listed in step 1. If it doesn't, see [When it doesn't connect](#when-it-doesnt-connect).

## 7. Write a first eval

Pick a question with an answer you can check yourself: run the query in a Snowflake
worksheet first, and use its result as `expected_answer`. Edit `evals/first_eval.yml`, with
your result in `expected_answer`:

```yaml
version: 1

evals:
  - category: first
    grading:
      method: extract_match
      min_score: 0.8
    provenance:
      expected_database: <database>
      expected_schema: <schema>
      min_score: 0.7
    tests:
      - id: orders_2025
        title: Orders in 2025
        prompt: How many orders did we get in 2025?
        expected_answer: "<your result>"
        provenance:
          expected_sources: [orders]
```

`expected_database` and `expected_schema` say where `orders` must live, so a same-named table
somewhere else (Snowflake's own `snowflake_sample_data`, say) doesn't count. Then:

```bash
uv run honest-agent run
```

See [Writing evals](/docs/writing-evals/) for more questions, and the other grading methods.

:::note[Queries start with no database]
In our tests, queries through this server started with no current database or schema:
`select current_database(), current_schema()` returned nothing. The agent has to write full
names, like `<database>.<schema>.orders`, so don't set `default_database` or `default_schema`
for this target. Check it on your account: ask the agent to run that query, or look at a
first run's SQL in `honest-agent logs`.
:::

## When it doesn't connect

- **The token is refused, or Snowflake won't create it:** the user needs a network policy
  (step 3), and your address must be in it. If your account has an authentication policy,
  it must allow `PROGRAMMATIC_ACCESS_TOKEN`.
- **It worked before and now it's refused:** the PAT may have expired (step 4).
- **Can't reach the host:** check for underscores in the account part of the URL (step 1).
- **The server is found, but access is denied:** the role needs `usage` on the MCP server
  and on its database and schema (step 2).
- **Queries fail with no warehouse:** set `default_warehouse` on the user (step 2), and
  grant `usage` on it to the role.
- **Queries fail with "does not exist or not authorized":** the role is missing `usage` on
  the database or schema, or `select` on the table. A bare table name also fails: see the
  note in step 7.

Still stuck? [Open an issue](https://github.com/jlcoto/the_honest_agent/issues/new) with the
output of `honest-agent debug`. It prints variable names, never their values, but check what
you paste anyway: no tokens, keys or private URLs.

## Don't have an MCP server yet?

honest-agent evaluates the server your agent uses; it doesn't need one of its own. If you're
setting one up, Snowflake's
[MCP server guide](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp)
covers it. A minimal server with one tool that runs SQL looks like this:

```sql
create mcp server <mcp_database>.<mcp_schema>.<mcp_server>
    from specification $$
    tools:
      - title: "SQL Execution Tool"
        name: query_warehouse
        type: SYSTEM_EXECUTE_SQL
        description: "Run read-only SQL queries against the <database> database."
        config:
          read_only: true
          query_timeout: 120
    $$;
```

- **`read_only: true`** makes the tool run only reads. It's Snowflake's default; setting it
  says so in the spec.
- **`warehouse:`** under `config` picks the warehouse, instead of the user's default.
- **`query_timeout:`** under `config` is a Snowflake setting: the maximum time in seconds
  for query execution, in Snowflake's words. It's separate from honest-agent's
  `tool_timeout`.
- The tool's `description` is what the model reads to decide when to use it.

Then follow the steps above, from step 1.
