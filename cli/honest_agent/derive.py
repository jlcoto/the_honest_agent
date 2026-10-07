"""Builds the derived tables (`results`, `tool_calls`, `traces`) from the raw layer
(raw.py). `run` derives each eval as soon as it ends; `rebuild` re-derives past
runs after this code changes, e.g. a new scoring rule.

Deriving never calls a model: the answer, the conversation and both scores come
from what the run recorded, using the settings and eval definition stored with it,
so re-deriving an unchanged run gives the same rows.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple

from .eval_loader import EvalDefinition
from .grading import score
from .llm import OPENAI, response_stop, response_text, response_tokens
from .provenance import check_provenance
from .raw import honest_agent_version
from .sql_capture import extract_sql_calls

_TIME = "%Y-%m-%d %H:%M:%S"


class Derived(NamedTuple):
    row: dict  # one `results` row + its trace and SQL calls, the shape storage.write_derived takes
    unparsed: list[str]  # SQL that couldn't be parsed, so it didn't count toward provenance


def _wants_tools(event: dict) -> bool:
    if event["provider"] == OPENAI:
        return bool(event["response"]["choices"][0]["message"].get("tool_calls"))
    return any(block.get("type") == "tool_use" for block in event["response"].get("content", []))


def _tool_result(event: dict) -> dict:
    """A tool call's result in the shared format: its text, and whether it failed."""
    if event["error"]:
        content, is_error = event["error"], True
    else:
        blocks = event["response"].get("content", [])
        content = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        is_error = bool(event["response"].get("isError"))
    return {
        "type": "tool_result",
        "tool_use_id": event["request"]["tool_use_id"],
        "content": content,
        "is_error": is_error,
    }


def _assistant_content(event: dict) -> list[dict]:
    """A model reply in the shared format: Claude's content blocks as they came; OpenAI's
    message converted to the same text and tool_use blocks."""
    if event["provider"] != OPENAI:
        return event["response"].get("content", [])
    message = event["response"]["choices"][0]["message"]
    text = [{"type": "text", "text": message["content"]}] if message.get("content") else []
    return text + [
        {
            "type": "tool_use",
            "id": call["id"],
            "name": call["function"]["name"],
            "input": json.loads(call["function"]["arguments"] or "{}"),
        }
        for call in message.get("tool_calls") or []
    ]


def step_details(events: list[dict]) -> dict:
    """What the conversation doesn't hold, for the report's Trace: each step's (model
    call's) tokens, duration and stop reason, in order, and each tool call's duration
    by its tool_use id."""
    steps = []
    for event in events:
        if event["kind"] == "model_call" and event["response"] is not None:
            tokens = response_tokens(event["provider"], event["response"])
            steps.append(
                {
                    "input_tokens": tokens[0],
                    "output_tokens": tokens[1],
                    "duration_ms": event["duration_ms"],
                    "stop_reason": response_stop(event["provider"], event["response"]),
                }
            )
    tool_ms = {
        event["request"]["tool_use_id"]: event["duration_ms"] for event in events if event["kind"] == "tool_call"
    }
    return {"steps": steps, "tool_ms": tool_ms}


def conversation(prompt: str, events: list[dict]) -> list[dict]:
    """The agent's conversation in the one format sql_capture, the report and `logs` read:
    the prompt, each model reply, and each batch of tool results as a user turn."""
    trace: list[dict] = [{"role": "user", "content": prompt}]
    for event in events:
        if event["kind"] == "model_call" and event["response"] is not None:
            trace.append({"role": "assistant", "content": _assistant_content(event)})
        elif event["kind"] == "tool_call":
            if trace[-1]["role"] == "user" and isinstance(trace[-1]["content"], list):
                trace[-1]["content"].append(_tool_result(event))
            else:
                trace.append({"role": "user", "content": [_tool_result(event)]})
    return trace


def agent_answer(events: list[dict], max_tool_steps: int) -> tuple[str, bool]:
    """(the agent's final answer, whether it ran out of steps). The answer is the
    text of its last reply; a last reply still asking for tools means the loop ran out."""
    replies = [e for e in events if e["kind"] == "model_call" and e["response"] is not None]
    if not replies or _wants_tools(replies[-1]):
        return (
            f"[honest-agent error] Exceeded max_tool_steps={max_tool_steps} without a final answer -- "
            "the agent was still requesting tools on the last step. See agent_trace for detail.",
            True,
        )
    last = replies[-1]
    return response_text(last["provider"], last["response"]).strip(), False


def _end(event: dict) -> datetime:
    return event["started_at"] + timedelta(milliseconds=event["duration_ms"] or 0)


def _read(con, result_id: str) -> tuple[dict, dict, list[dict]]:
    run_cols = ["run_id", "agent_name", "model", "judge_model", "settings"]
    eval_cols = ["result_id", "run_id", "eval_id", "definition", "started_at"]
    eval_row = con.execute(f"select {', '.join(eval_cols)} from raw.evals where result_id = ?", [result_id]).fetchone()
    if eval_row is None:
        raise ValueError(f"No raw record for result {result_id}")
    evaluation = dict(zip(eval_cols, eval_row, strict=True))
    run_row = con.execute(f"select {', '.join(run_cols)} from raw.runs where run_id = ?", [evaluation["run_id"]])
    run = dict(zip(run_cols, run_row.fetchone(), strict=True))
    event_cols = ["seq", "kind", "provider", "started_at", "duration_ms", "request", "response", "error"]
    events = [
        dict(zip(event_cols, row, strict=True))
        for row in con.execute(
            f"select {', '.join(event_cols)} from raw.events where result_id = ? order by seq", [result_id]
        ).fetchall()
    ]
    for event in events:
        for key in ("request", "response"):
            event[key] = json.loads(event[key]) if event[key] is not None else None
    return run, evaluation, events


def recorded_answer(con, result_id: str) -> tuple[str, bool]:
    """The agent's answer as recorded so far, for `run` to grade: (answer, ran out of steps)."""
    run, _, events = _read(con, result_id)
    agent_events = [e for e in events if e["kind"] in ("model_call", "tool_call")]
    return agent_answer(agent_events, json.loads(run["settings"])["max_tool_steps"])


def derive_result(con, result_id: str) -> Derived:
    """One result's derived rows, from its raw record alone."""
    run, evaluation, events = _read(con, result_id)
    if any(e["kind"] == "eval_error" for e in events):
        raise ValueError(f"Result {result_id} stopped with an error; it has nothing to derive")
    settings = json.loads(run["settings"])
    definition = EvalDefinition(**json.loads(evaluation["definition"]))

    agent_events = [e for e in events if e["kind"] in ("model_call", "tool_call")]
    answer, hit_step_limit = agent_answer(agent_events, settings["max_tool_steps"])
    trace = conversation(definition.prompt, agent_events)

    grading = next((e for e in events if e["kind"] == "grading_call"), None)
    reply = response_text(grading["provider"], grading["response"]) if grading else None
    grade = score(
        definition.grading_method,
        answer,
        definition.expected_answer,
        reply,
        definition.tolerance,
        definition.tolerance_percent,
    )

    sql_calls = extract_sql_calls(trace, definition.sql_fields, settings.get("ignore_tools", []))
    # Only SQL the agent sent and that ran counts toward provenance: a query that
    # errored read nothing, and SQL a tool generated (e.g. Cortex Analyst) may never have run.
    provenance = check_provenance(
        [call["sql"] for call in sql_calls if not call["is_error"] and not call["generated"]],
        definition.expected_sources,
        definition.expected_database,
        definition.expected_schema,
    )

    agent_tokens = [
        response_tokens(e["provider"], e["response"])
        for e in agent_events
        if e["kind"] == "model_call" and e["response"] is not None
    ]
    grading_tokens = response_tokens(grading["provider"], grading["response"]) if grading else (0, 0)
    latency_ms = (
        int((max(_end(e) for e in agent_events) - agent_events[0]["started_at"]).total_seconds() * 1000)
        if agent_events
        else None
    )
    row: dict[str, Any] = {
        # -- results --
        "result_id": result_id,
        "run_id": evaluation["run_id"],
        "run_timestamp": evaluation["started_at"].strftime(_TIME),
        "finished_at": max((_end(e) for e in events), default=evaluation["started_at"]).strftime(_TIME),
        "eval_id": definition.eval_id,
        "eval_title": definition.title,
        "prompt": definition.prompt,
        "category": definition.category,
        "tags": definition.tags,
        "expected_answer": definition.expected_answer,
        "agent_answer": answer,
        "tools_used": [e["request"]["name"] for e in agent_events if e["kind"] == "tool_call"],
        "accuracy_score": grade.score,
        "accuracy_method": definition.grading_method,
        # The model that graded the answer; `contains` uses none.
        "grading_model": run["judge_model"] if grading else None,
        "accuracy_rationale": grade.rationale,
        "extracted_answer": grade.extracted_answer,
        "accuracy_tolerance": definition.tolerance,
        "accuracy_tolerance_percent": definition.tolerance_percent,
        "accuracy_min_score": definition.accuracy_min_score,
        "provenance_score": provenance.score,
        "queried_sources": [source._asdict() for source in provenance.queried_sources],
        "expected_sources": definition.expected_sources,
        "expected_database": definition.expected_database,
        "expected_schema": definition.expected_schema,
        # No threshold for a check that didn't happen (see check_provenance).
        "provenance_min_score": definition.provenance_min_score if provenance.score is not None else None,
        "model_name": run["model"],
        "agent_backend": "mcp",
        "agent_name": run["agent_name"],
        "latency_ms": latency_ms,
        # One step is one model call and the tool calls it asks for.
        "steps": sum(1 for e in agent_events if e["kind"] == "model_call"),
        "max_steps": settings["max_tool_steps"],
        "hit_step_limit": hit_step_limit,
        "agent_input_tokens": sum(t[0] for t in agent_tokens),
        "agent_output_tokens": sum(t[1] for t in agent_tokens),
        "grading_input_tokens": grading_tokens[0],
        "grading_output_tokens": grading_tokens[1],
        "derived_at": datetime.now(timezone.utc).strftime(_TIME),
        "honest_agent_version": honest_agent_version(),
        # -- traces --
        "agent_trace": json.dumps(trace),
        "step_details": json.dumps(step_details(agent_events)),
        # -- tool_calls (expanded into one row per call by storage.py) --
        "sql_calls": sql_calls,
    }
    return Derived(row, provenance.unparsed)
