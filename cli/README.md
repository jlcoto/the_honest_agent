# honest-agent

Open-source evals for agentic analytics. `honest-agent` asks your analytics agent
questions you know the answers to, through the agent's own MCP server, and checks each
answer for **accuracy** (is it right?) and **provenance** (did the agent's SQL read the
tables it should?). Results go to DuckDB or MotherDuck, into a web report you can host for
your team, and to Slack when an eval falls below its threshold.

```bash
uv init --bare --python 3.11
uv add "honest-agent @ git+https://github.com/jlcoto/the_honest_agent.git@v0.2.0#subdirectory=cli"
uv run honest-agent init --example
```

- Docs: [thehonestagent.dev/docs](https://thehonestagent.dev/docs/)
- Source and issues: [github.com/jlcoto/the_honest_agent](https://github.com/jlcoto/the_honest_agent)
- Changelog: [CHANGELOG.md](https://github.com/jlcoto/the_honest_agent/blob/main/CHANGELOG.md)

honest-agent is in alpha: expect breaking changes between versions. MIT licensed.
