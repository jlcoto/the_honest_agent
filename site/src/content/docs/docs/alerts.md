---
title: Setting up alerts
description: Get a Slack message when an eval falls below its threshold.
---

`honest-agent notify` posts a message to a Slack channel when the latest run had an eval
below its threshold. When every eval passed, it posts nothing.

## 1. Create a Slack webhook

honest-agent posts through a Slack
[incoming webhook](https://api.slack.com/messaging/webhooks): a private URL that posts to
one channel. Create one with Slack's guide, for the channel the alerts should go to.

Put it in `.env`, like the other secrets:

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

:::caution
Anyone with the webhook URL can post to your channel. Keep it in `.env` or your CI's
secrets, never in the config or in git.
:::

## 2. Send the alert after a run

```bash
uv run honest-agent run
uv run honest-agent notify
```

`notify` reads the latest run of the default target from your results. `--target <name>`
picks another one. It prints whether it posted:

```
Posted Slack alert for 2 failing eval(s) for agent sales-agent.
```

### One channel per environment

To alert a dev channel apart from production, give each its own webhook, and pass it with
`--webhook-url` (or a separate `SLACK_WEBHOOK_URL` in that job):

```bash
uv run honest-agent notify --target snowflake_dev --webhook-url "$DEV_SLACK_WEBHOOK_URL"
```

Give the dev target its own `agent_name` too. Two targets with the same `agent_name`
record their runs, and send their alerts, as the same agent.

## What the alert says

```
🔴 2 of 4 evals below threshold
sales-agent · claude-sonnet-4-5 · run started 2026-10-10 08:02 UTC
───
Revenue in Q4 2026  revenue_q4
Accuracy 0.00 (min 0.8)  ·  Provenance 0.50 (min 0.7)

Order total in 2026  order_total_2026
Accuracy 1.00 (min 0.8)  ·  Provenance 0.50 (min 0.7)
───
Open the report · honest-agent
```

Each failing eval shows its title, id and scores against their thresholds. An eval that
stopped with an error (a provider or MCP failure) shows `Error:` and the reason instead,
and the headline counts it apart, as in "3 of 4 evals failed: 2 below threshold, 1
stopped with an error". A message lists up to 20 failing evals, and counts the rest.

## Link the alert to your report

If your report is [hosted](/docs/team/) somewhere your team can open it, give `notify` its
address:

```bash
HONEST_AGENT_REPORT_URL=https://reports.example.com/
```

Each eval's title in the alert then links to its result page, and "Open the report" to
the report. The links work through a sign-in page in front of the report. Without an
address, the alert says to run `honest-agent report` instead.

[Running it for a team](/docs/team/) shows how to host the report, and
[Run it in GitHub Actions](/docs/team/ci/) how to run `notify` after every run.
