from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from .storage import read_latest_run_results
from .thresholds import failing_rows

# Slack allows 50 blocks per message; the rest of the failures are counted, not listed.
_MAX_LISTED = 20


def _post_to_slack(webhook_url: str, message: dict[str, Any]) -> None:
    body = json.dumps(message).encode("utf-8")
    request = urllib.request.Request(webhook_url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request) as response:
        if response.status >= 300:
            raise RuntimeError(f"Slack webhook returned status {response.status}")


def _escape(text: str) -> str:
    """Slack's escaping for message text, so an eval id or title can't mention
    `<!channel>` or disguise a link."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _context(text: str) -> dict[str, Any]:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def _result_link(report_url: str, result_id: str) -> str:
    """A link to one result's page as `?result=<id>`, not `#/result/<id>`: a sign-in in
    front of a hosted report keeps the query through its login but drops the `#...` part.
    The report's router turns the query into its usual route."""
    parts = urllib.parse.urlsplit(report_url)
    query = urllib.parse.parse_qsl(parts.query) + [("result", result_id)]
    return urllib.parse.urlunsplit(
        parts._replace(query=urllib.parse.urlencode(query, quote_via=urllib.parse.quote), fragment="")
    )


def alert_message(
    rows: list[dict[str, Any]], failures: list[dict[str, Any]], report_url: str | None = None
) -> dict[str, Any]:
    """The Slack message for one run's failing evals: which agent and model, when, and each
    failure's scores. `text` is what notifications and the sidebar show."""
    first = rows[0]
    agent = _escape(first["agent_name"] or "unknown agent")
    model = _escape(first["model_name"] or "unknown model")
    started = min(r["run_timestamp"] for r in rows)[:16]
    headline = f"{len(failures)} of {len(rows)} evals below threshold"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"🔴 {headline}"}},
        _context(f"*{agent}* · {model} · run started {started} UTC"),
        {"type": "divider"},
    ]
    for f in failures[:_MAX_LISTED]:
        title = _escape(f["eval_title"] or f["eval_id"])
        if report_url:
            title = f"<{_result_link(report_url, f['result_id'])}|{title}>"
        scores = [f"Accuracy *{f['accuracy_score']:.2f}* (min {f['accuracy_min_score']})"]
        if f["provenance_score"] is not None:
            scores.append(f"Provenance *{f['provenance_score']:.2f}* (min {f['provenance_min_score']})")
        text = f"*{title}*  `{_escape(f['eval_id'])}`\n" + "  ·  ".join(scores)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
    if len(failures) > _MAX_LISTED:
        blocks.append(_context(f"…and {len(failures) - _MAX_LISTED} more"))
    footer = f"<{report_url}|Open the report>" if report_url else "Details: `honest-agent report`"
    blocks += [{"type": "divider"}, _context(f"{footer} · honest-agent")]
    return {"text": f"{headline} for {agent} ({model})", "blocks": blocks}


def notify_on_failures(
    results_path: str, webhook_url: str, agent_name: str | None = None, report_url: str | None = None
) -> None:
    rows = read_latest_run_results(results_path, agent_name)
    whose = f" for agent {agent_name}" if agent_name else ""
    if not rows:
        print(f"No results{whose} found under {results_path} -- nothing to notify.")
        return

    failures = failing_rows(rows)
    if not failures:
        print(f"No evals below threshold in the latest run{whose} -- nothing to notify.")
        return

    _post_to_slack(webhook_url, alert_message(rows, failures, report_url))
    print(f"Posted Slack alert for {len(failures)} failing eval(s){whose}.")
