"""Builds raw records (raw.py) for tests: a run and its evals recorded through the real
RunRecorder, with responses shaped like the SDKs' (as dicts, which to_jsonable keeps)."""

from __future__ import annotations

import asyncio

from honest_agent.eval_loader import EvalDefinition
from honest_agent.raw import RunRecorder
from honest_agent.storage import connect

SETTINGS = {"max_tool_turns": 5, "max_tokens": 1024, "mcp": {"command": "python server.py"}, "ignore_tools": []}


def definition(**overrides) -> EvalDefinition:
    values = dict(
        eval_id="q1",
        prompt="What is 2+2?",
        category="math",
        expected_answer="4",
        grading_method="contains",
        expected_sources=[],
        tags=["smoke"],
    )
    values.update(overrides)
    return EvalDefinition(**values)


def claude_reply(*blocks: dict, input_tokens: int = 10, output_tokens: int = 5) -> dict:
    return {
        "content": list(blocks),
        "stop_reason": "tool_use" if any(b["type"] == "tool_use" for b in blocks) else "end_turn",
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def text(words: str) -> dict:
    return {"type": "text", "text": words}


def tool_use(call_id: str, name: str, arguments: dict) -> dict:
    return {"type": "tool_use", "id": call_id, "name": name, "input": arguments}


def mcp_result(words: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": words}], "isError": is_error}


def model_call(reply: dict, provider: str = "anthropic") -> tuple:
    return ("model_call", provider, {"model": "claude-test", "messages": []}, reply)


def tool_call(call_id: str, name: str, arguments: dict, result: dict) -> tuple:
    return ("tool_call", "mcp", {"tool_use_id": call_id, "name": name, "arguments": arguments}, result)


def grading_call(reply_text: str, provider: str = "anthropic") -> tuple:
    return ("grading_call", provider, {"model": "claude-judge", "prompt": "..."}, claude_reply(text(reply_text)))


async def _returns(value):
    return value


def record(
    results_path: str,
    events: list[tuple],
    *,
    run_id: str = "run_1",
    result_id: str = "r1",
    eval_definition: EvalDefinition | None = None,
    settings: dict | None = None,
) -> None:
    """Records one eval (and its run, the first time) with the given events, in order."""
    con = connect(results_path)
    try:
        recorder = RunRecorder(con)
        if not con.execute("select count(*) from raw.runs where run_id = ?", [run_id]).fetchone()[0]:
            recorder.start_run(
                run_id,
                agent_name="demo",
                target="demo",
                model="claude-test",
                judge_model="claude-judge",
                settings=settings or SETTINGS,
                tools_offered=[{"name": "query_warehouse", "description": "Run SQL", "inputSchema": {}}],
            )
        evaluation = recorder.start_eval(result_id, run_id, eval_definition or definition())
        for kind, provider, request, response in events:
            asyncio.run(evaluation.call(kind, provider, request, _returns(response)))
    finally:
        con.close()
