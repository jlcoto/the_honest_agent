from __future__ import annotations

import json
import urllib.request

from .storage import read_latest_run_results
from .thresholds import failing_rows


def _post_to_slack(webhook_url: str, text: str) -> None:
    body = json.dumps({"text": text}).encode("utf-8")
    request = urllib.request.Request(webhook_url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request) as response:
        if response.status >= 300:
            raise RuntimeError(f"Slack webhook returned status {response.status}")


def notify_on_failures(results_path: str, webhook_url: str) -> None:
    rows = read_latest_run_results(results_path)
    if not rows:
        print(f"No results found under {results_path} -- nothing to notify.")
        return

    failures = failing_rows(rows)
    if not failures:
        print("No evals below threshold in the latest run -- nothing to notify.")
        return

    lines = [f"*honest-agent*: {len(failures)}/{len(rows)} eval(s) below threshold (run {rows[0]['run_id']})"]
    for f in failures:
        bits = []
        if not f["accuracy_pass"]:
            bits.append(f"accuracy {f['accuracy_score']:.2f} < {f['accuracy_min_score']}")
        if not f["provenance_pass"]:
            bits.append(f"provenance {f['provenance_score']:.2f} < {f['provenance_min_score']}")
        lines.append(f"- `{f['eval_id']}`: {', '.join(bits)}")

    _post_to_slack(webhook_url, "\n".join(lines))
    print(f"Posted Slack alert for {len(failures)} failing eval(s).")
