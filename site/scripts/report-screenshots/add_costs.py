"""The v0.4.0 fields for the sample report data: what each eval cost, the grading model's
call, and each step's cost, as `honest-agent run` stores them now.

Usage: add_costs.py FILE...   (run from cli/ with `uv run`; rewrites in place)

Costs are the sample's own token counts × honest-agent's built-in prices (no cache, as
the sample has no cache tokens). Grading is claude-sonnet-5-5 at low effort, the default
for Claude agents, for every run, as the landing page's terminal shows.
"""

import json
import sys
from datetime import datetime, timedelta

from honest_agent.prices import BUILT_IN

GRADER = "claude-sonnet-5-5"
# The sample gave every eval the same tokens and time; each eval gets its own here, varied a
# little from run to run, so the costs differ as real ones do. revenue_q4 keeps its own: its
# trace (the one result with steps) adds up to them.
AGENT = {  # eval: input tokens, output tokens, latency ms
    "order_total_2026": (4300, 260, 6100),
    "top_segment": (2900, 180, 4200),
    "top_nations_last_year": (7400, 420, 11700),
}
JITTER = [1.00, 0.96, 1.04, 0.98, 1.03, 0.97, 1.01, 0.95, 1.05, 0.99, 1.02, 0.97, 1.03, 1.00, 0.98]

# Grading tokens for evals the sample left without them (extract_match always calls the model).
DEFAULT_GRADING_TOKENS = {"extract_match": (380, 18), "llm_judge": (500, 90)}


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price = BUILT_IN[model]
    return (input_tokens * price.input + output_tokens * price.output) / 1_000_000


def grading_reply(r: dict) -> str:
    if r["accuracy_method"] == "extract_match":
        return json.dumps({"extracted_answer": r["extracted_answer"]})
    return json.dumps({"score": r["accuracy_score"], "rationale": r["accuracy_rationale"]})


def update(path: str) -> None:
    data = json.load(open(path))
    logs = {a["result_id"]: a for a in data["agent_logs"]}
    for r in data["results"]:
        if r["eval_id"] in AGENT:
            k = JITTER[int(r["run_id"].removeprefix("run")) % len(JITTER)]
            tokens_in, tokens_out, ms = AGENT[r["eval_id"]]
            r["agent_input_tokens"], r["agent_output_tokens"] = round(tokens_in * k), round(tokens_out * k)
            r["latency_ms"] = int(round(ms * k, -2))
        graded = r["accuracy_method"] in DEFAULT_GRADING_TOKENS
        if graded and r["grading_input_tokens"] is None:
            r["grading_input_tokens"], r["grading_output_tokens"] = DEFAULT_GRADING_TOKENS[r["accuracy_method"]]
        if not graded:
            r["grading_input_tokens"] = r["grading_output_tokens"] = 0
        r["grading_model"] = GRADER if graded else None
        r["grading_effort"] = "low" if graded else None
        r["effort"] = None
        r["agent_cache_read_tokens"] = r["agent_cache_write_tokens"] = 0
        r["agent_cost_usd"] = cost(r["model_name"], r["agent_input_tokens"], r["agent_output_tokens"])
        r["grading_cost_usd"] = cost(GRADER, r["grading_input_tokens"], r["grading_output_tokens"]) if graded else 0.0
        started = datetime.fromisoformat(r["run_timestamp"])
        r["finished_at"] = r["derived_at"] = str(started + timedelta(milliseconds=r["latency_ms"] or 0))[:19]
        r["honest_agent_version"] = "0.4.0"
        log = logs.get(r["result_id"])
        if log is None:
            continue
        if log.get("step_details"):
            details = json.loads(log["step_details"])
            for step in details["steps"]:
                step["cost_usd"] = cost(r["model_name"], step["input_tokens"], step["output_tokens"])
            log["step_details"] = json.dumps(details)
        log["grading_call"] = (
            json.dumps(
                {
                    "model": GRADER,
                    "reply": grading_reply(r),
                    "stop_reason": "end_turn",
                    "max_tokens": 2048,
                    "input_tokens": r["grading_input_tokens"],
                    "output_tokens": r["grading_output_tokens"],
                    "thinking_tokens": 0,
                    "duration_ms": 1300,
                }
            )
            if graded
            else None
        )
    with open(path, "w") as f:
        json.dump(data, f)


for path in sys.argv[1:]:
    update(path)
