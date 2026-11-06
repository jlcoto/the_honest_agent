---
title: Connect to Databricks
description: Evaluate Genie One, or a model writing its own SQL on Databricks, through Databricks-provided MCPs.
---

:::caution[An example, not a security review]
This is one setup we tested, shown as an example. Don't copy it blindly: check each step
against your company's security policies, and adapt it before you use it with real data.
See [Your setup, your responsibility](/docs/team/#your-setup-your-responsibility).
:::

Databricks hosts MCP servers of its own, [Databricks-provided MCPs](https://docs.databricks.com/aws/en/agents/mcp-tools/built-in-mcp-services),
that Claude and other agents connect to.
honest-agent works with two of them, and they test different things:

| Server | Who writes the SQL | What you evaluate |
|---|---|---|
| **Genie One** | Genie, Databricks' own AI | Genie's answers, as your business users get them in Claude or another client |
| **Databricks SQL** | The model honest-agent runs | How well a model answers from your data, writing its own SQL through this server |

honest-agent connects to either one as a
[service principal](https://docs.databricks.com/aws/en/admin/users-groups/service-principals),
with a personal access token sent with each request. Databricks supports these tokens here
but [recommends OAuth](https://docs.databricks.com/aws/en/agents/mcp-tools/authentication-networking) for unattended
agents, which honest-agent doesn't do yet: check this against your company's policies. We
tested this setup on a Databricks Free Edition workspace in November 2026.

The SQL and commands below have placeholders in angle brackets. Replace them with yours:

| Placeholder | What it is |
|---|---|
| `<host>` | Your workspace's host, like `dbc-1234abcd-5678.cloud.databricks.com` |
| `<workspace_id>` | Your workspace's ID (step 1) |
| `<catalog>`, `<schema>` | Where the tables the agent reads live |
| `<application_id>` | The service principal's application ID (step 2) |

Make sure you have the privileges to complete steps 2 to 4.

## 1. Find your workspace's host and ID

- **Host:** the part of your browser's address between `https://` and the next `/` when
  you're in Databricks.
- **Workspace ID:** the number after `?o=` in Databricks' URLs.

The server URLs use the newer
[Unity Gateway](https://docs.databricks.com/aws/en/agents/mcp-tools/built-in-mcp-services) endpoints:

```
https://<host>/ai-gateway/mcp-services/system.ai.genie_one_mcp?o=<workspace_id>
https://<host>/ai-gateway/mcp-services/system.ai.dbsql?o=<workspace_id>
```

Databricks SQL's URL uses the Unity Gateway beta: on your workspace, an account admin might
need to turn it on. Check [Databricks' docs](https://docs.databricks.com/aws/en/agents/mcp-tools/databricks-sql).

The older endpoints under `/api/2.0/mcp/` need the "Managed MCP Servers" preview turned on.
On a workspace without it, they answer "Databricks managed MCP servers are not enabled".
The older Genie One URL [stops working on November 30, 2026](https://docs.databricks.com/aws/en/agents/mcp-tools/genie-mcp),
so use the ones above.

## 2. Create a service principal

honest-agent can't log in as your users do, so it needs its own identity. Using a
service principal also matters for Genie One, which remembers each user's past
conversations: see [Genie One remembers](#genie-one-remembers).

Check the cost first: Databricks' docs say Genie One's usage by users is free until January
31, 2027, but [service principals are excluded and billed](https://docs.databricks.com/aws/en/genie/monitor-cost), and every
eval is a Genie conversation.

Go to **Settings → Identity and access → Service principals → Add new**, name it (for
example `honest_agent_service`), and set its entitlements:

- **Databricks SQL access** and **Consumer access**: on.
- Anything else: off. Evals don't need it. See Databricks' docs on
  [entitlements](https://docs.databricks.com/aws/en/security/auth/entitlements).

Open the new service principal and copy its **Application ID**: grants use it, not the
name.

## 3. Give it read access

Give the service principal the same `select` grants as the users whose answers you want
to test, so the agent sees the same data. In the SQL Editor:

```sql
grant use catalog on catalog <catalog> to `<application_id>`;
grant use schema, select on schema <catalog>.<schema> to `<application_id>`;
```

- **Use the service principal's application ID, not its name,** in backticks.
- **Several schemas?** Repeat the grants for each one.
- **Extra privileges:** your setup might require more, like `EXECUTE` on the MCP or `CAN USE`
  on a SQL warehouse. Check Databricks' docs on
  [the MCP](https://docs.databricks.com/aws/en/ai-gateway/govern-mcp-service) and
  [the warehouse](https://docs.databricks.com/aws/en/agents/mcp-tools/built-in-mcp-services).

For Genie One, also share your Genie Agents and workspace instructions with the service
principal. Without them, it might not get the same answers as your users:

- each **Genie Agent** they use: open it, **Share**, the service principal with
  **CAN RUN**;
- the **workspace instructions** file, `/Workspace/.genie_workspace_instructions.md`, if
  you have one: **Share**, **CAN VIEW** (Databricks' docs share it with all users).

## 4. Create a token for it

A service principal can only have a token if the workspace allows it. In **Settings →
Advanced**, find the permissions for personal access tokens and give the service principal
**CAN USE**. See Databricks' docs on
[token permissions](https://docs.databricks.com/aws/en/security/auth/api-access-permissions). You'll also need a token of
your own for the next step.

Create the service principal's token with the
[token management API](https://docs.databricks.com/api/token-management/v1/create-on-behalf-of-token),
with your own token as an admin:

```bash
curl -X POST "https://<host>/api/2.0/token-management/on-behalf-of/tokens" \
  -H "Authorization: Bearer <your_own_token>" \
  -d '{"application_id": "<application_id>", "lifetime_seconds": 7776000, "comment": "honest-agent"}'
```

- **Copy `token_value` from the reply now:** Databricks shows it only once.
- **It expires:** `lifetime_seconds` here is 90 days. When it expires, honest-agent can't
  connect until you create a new one and update `.env` (or your CI's secret).

## 5. Run `init`

In the folder for your evals, run `init` for the server you want to evaluate. For Genie One:

```bash
uv run honest-agent init --server databricks_genie
```

For Databricks SQL:

```bash
uv run honest-agent init --server databricks_sql
```

`init` asks for the URL from step 1, then writes a target to `honest_agent_config.yml`.
For Genie One:

```yaml
targets:
  databricks_genie:
    mcp_url: "{{ env_var('DATABRICKS_GENIE_MCP_URL') }}"
    bearer_token_env: DATABRICKS_GENIE_MCP_TOKEN
    max_tool_steps: 30
    evals_dir: evals
```

`max_tool_steps: 30` is there because Genie answers asynchronously: see
[Genie One takes many steps](#genie-one-takes-many-steps).

Fill in `.env`: the token from step 4 goes in `DATABRICKS_GENIE_MCP_TOKEN`
(or `DATABRICKS_SQL_MCP_TOKEN`), next to your model's API key. Keep `.env` out of git.

```bash
DATABRICKS_GENIE_MCP_URL=https://<host>/ai-gateway/mcp-services/system.ai.genie_one_mcp?o=<workspace_id>
DATABRICKS_GENIE_MCP_TOKEN=...
ANTHROPIC_API_KEY=...
```

To evaluate both Genie One and Databricks SQL, run `init` once, then copy the target in
`honest_agent_config.yml` and change its name, URL and token variable.

## 6. Check the connection

```bash
uv run honest-agent debug
```

The "MCP server" line should connect and count the server's tools: 4 for Genie One
(`genie_ask`, `genie_poll_response` and two more), 2 for Databricks SQL (`execute_sql` and
`poll_sql_result`). If it doesn't, see [When it doesn't connect](#when-it-doesnt-connect).

## 7. Write a first eval

Pick a question with an answer you can check yourself: run the query in the SQL Editor
first, and use its result as `expected_answer`. Edit `evals/first_eval.yml`:

```yaml
version: 1

evals:
  - category: first
    grading:
      method: extract_match
      min_score: 0.8
    provenance:
      expected_database: <catalog>
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

`expected_database` takes the catalog. It and `expected_schema` say where `orders` must
live, so a same-named table somewhere else (in Databricks' `samples` catalog, say) doesn't
count. Then:

```bash
uv run honest-agent run
```

For Genie One, read [Routed answers have no SQL](#routed-answers-have-no-sql) before you
rely on provenance. See [Writing evals](/docs/writing-evals/) for more questions, and the
other grading methods.

## What to know about Genie One

### Genie One takes many steps

Genie One answers asynchronously. The agent asks with `genie_ask`, then calls
`genie_poll_response` until Genie has finished, and each poll is a step. In our tests evals
took 25 to 56 seconds and the agent used 7 to 13 steps; yours may be slower on larger data.
The agent always needed more than the default of 5 steps. `init` sets 30; raise it if
results say the eval hit the step limit.

The agent may answer before Genie has finished: Genie's replies show its query results as
they come, and the agent can answer from them.

### Routing to Genie Agents

Genie One can hand a question to one of your
[Genie Agents](https://docs.databricks.com/aws/en/genie-agents), with its curated tables,
instructions and example SQL. Genie One may not pick your agent on its own. In our tests, it
used ours after we added this line to the
[workspace instructions](https://docs.databricks.com/aws/en/genie-one/chat):

```markdown
- For questions about orders, customers or sales, use the "Sales Agent" Genie Agent.
```

### Routed answers have no SQL

When Genie One uses other, specialized agents (Genie Agents) to generate the response, the
SQL isn't in the MCP output, so provenance can't be checked. The reply only links to the
agent that answered. For questions that Genie One routes to an agent, grade accuracy only:
leave `expected_sources` out of those evals, or provenance fails.

To see whether an answer was routed, open its result: in our tests, routed answers showed no
SQL calls and usually named the agent.

When Genie One answers itself, its reply includes the SQL it ran, and provenance works as
for any other server.

### Genie One remembers

Genie One [remembers each user's past conversations](https://docs.databricks.com/aws/en/genie-one/chat)
and can use them in later answers, so use a separate service principal (step 2) rather than
a person's token.

### `samples` is demo data to Genie

In our tests, Genie treated Databricks' `samples` catalog as demo data. To try Genie One on
sample data, copy the tables into your own catalog first.

## What to know about Databricks SQL

- **It can change data by default.** `execute_sql` runs writes too, limited only by the
  caller's grants. honest-agent blocks SQL that changes data, but a service principal with
  only `select` grants (step 3) is what makes sure it can't. Databricks' docs also describe
  turning writes off for the server, with `disallow_writes` in the `system.ai.dbsql_policy`
  policy, which needs another preview; we haven't tried it.
- **Steps:** the agent can need several steps for one question, so raise `max_tool_steps` if
  evals hit the limit. We ran ours with 10.

## When it doesn't connect

- **"Databricks managed MCP servers are not enabled":** the URL uses an `/api/2.0/mcp/`
  endpoint. Use the `/ai-gateway/mcp-services/` one from step 1.
- **"does not have permission to use tokens"** when creating the token: give the service
  principal **CAN USE** on tokens (step 4).
- **`PRINCIPAL_DOES_NOT_EXIST`** in a grant: use the application ID, not the name (step 3).
- **It worked before and now it's refused:** the token may have expired (step 4), or been revoked after 90
  days without use.

Still stuck? [Open an issue](https://github.com/jlcoto/the_honest_agent/issues/new) with the
output of `honest-agent debug`. It prints variable names, never their values, but check what
you paste anyway: no tokens, keys or private URLs.
