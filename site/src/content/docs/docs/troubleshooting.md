---
title: Troubleshooting
description: What common honest-agent messages mean and how to fix them.
---

Run `honest-agent debug` first. It checks the config, the variables, the evals, the MCP
server and the results store, without calling a model, and says what's wrong.

| You see | What to do |
|---|---|
| `--mcp-command or --mcp-url is required` | honest-agent found no `honest_agent_config.yml`. Run it from your project folder, or create one with `honest-agent init`. |
| `... reads env_var('X'), but X isn't set` | The config reads `X` from the environment: add it to `.env`. |
| `Note: ... from the environment overrides target ...` | An environment variable beats the config file. Remove it from `.env` and your shell if you want the config's value. |
| `Unknown setting(s) in ...` | A typo in `honest_agent_config.yml`. The message lists the allowed settings. |
| A local server fails to log in to its database | A local server only gets the variables listed in its target's `mcp_env`. Add the one it needs. |
| `report` says a folder `isn't empty and isn't an honest-agent report folder` | `report` clears old files where it writes, so it only writes into a new or empty folder, or one it wrote before. Pick another `--out`. |
| `serve` says a folder `isn't an honest-agent report folder` | `serve` only publishes a folder `report` wrote, so it can't expose other files (like `.env`). Run `honest-agent report` first, or pass its folder with `--out`. |
| `Address already in use` from `serve` | Another program uses the port: `serve --port 8001`. |
| `honest-agent didn't run this SQL: it contains a ... statement` | The agent sent SQL that isn't a read, so it wasn't run. honest-agent never lets an agent change the warehouse, temp tables included. |
| `honest-agent stopped this tool call: it took longer than 120s` | A query took longer than the tool timeout. If your warehouse is just slow, raise `tool_timeout` on the target (in seconds). |
| `... hit the step limit without a final answer` | The agent needed more steps than allowed: raise `max_tool_steps` on the target (default 5), for example to 10. |

To see what happened in a run, call by call, use
[`honest-agent logs`](/docs/running-evals/#find-out-why-an-eval-failed).

Something else? [Open an issue](https://github.com/jlcoto/the_honest_agent/issues/new/choose)
with the output of `honest-agent debug`, with any URLs or account names you'd rather not
share removed.
