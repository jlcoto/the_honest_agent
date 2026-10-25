"""Runs an eval run: loads the evals, connects to the agent's MCP server, runs and grades each
eval while recording every call (raw layer), and writes the results. The CLI (`honest-agent run`)
resolves the settings and calls `run_evals`; anything else can call it the same way.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import click

from .agent_runner import AgentClient
from .derive import CUT_OFF_ANSWER, derive_result, recorded_answer
from .eval_loader import (
    EvalDefinition,
    SelectorError,
    load_evals,
    nothing_selected,
    number_format_warnings,
    select_evals,
)
from .grading import GRADING_MAX_TOKENS, GRADING_SCHEMAS, NOT_GRADED, grading_prompt
from .llm import OPENAI, Judge, make_judge, provider_for
from .raw import RunRecorder
from .sql_guard import ReadOnlySQL
from .storage import connect, write_derived
from .thresholds import failing_rows


class RunError(Exception):
    """A run that can't start or go on, for a reason the user can fix; the CLI shows its message."""


async def eval_loop(
    agent: AgentClient,
    definitions: list[EvalDefinition],
    judge: Judge,
    grading_model: str,
    run_id: str,
    recorder: RunRecorder,
    con,
) -> list[dict]:
    """Runs and grades each eval, recording every call as it returns (raw layer), then
    derives the eval's results from that record and writes them before the next one."""
    rows: list[dict] = []
    for definition in definitions:
        click.echo(f"  - {definition.eval_id}: {definition.prompt!r}")
        result_id = str(uuid.uuid4())
        record = recorder.start_eval(result_id, run_id, definition)
        try:
            await agent.run(definition.prompt, record)
            answer, hit_turn_limit = recorded_answer(con, result_id)
            if hit_turn_limit:
                click.echo(f"    WARNING: {definition.eval_id} hit the step limit without a final answer.")
            elif answer.startswith(CUT_OFF_ANSWER):
                click.echo(f"    WARNING: {definition.eval_id}: {answer}")
            prompt = grading_prompt(definition.grading_method, answer, definition.expected_answer, definition.prompt)
            if prompt is not None:
                schema = GRADING_SCHEMAS[definition.grading_method]
                request = {"model": grading_model, "max_tokens": GRADING_MAX_TOKENS, "prompt": prompt, "schema": schema}
                await record.call(
                    "grading_call",
                    provider_for(grading_model),
                    request,
                    judge.complete(prompt, model=grading_model, max_tokens=GRADING_MAX_TOKENS, schema=schema),
                )
            derived = derive_result(con, result_id)
        except Exception as exc:
            record.eval_error(exc)
            raise
        write_derived(con, [derived.row])
        if (derived.row.get("accuracy_rationale") or "").startswith(NOT_GRADED):
            click.echo(f"    WARNING: {definition.eval_id}: {derived.row['accuracy_rationale']}")
        for sql in derived.unparsed:
            click.echo(f"    WARNING: couldn't parse this SQL, so it doesn't count toward provenance: {sql[:80]!r}")
        rows.append(derived.row)
    return rows


def resolve_agent_name(explicit: str | None, connected_client) -> str:
    """`--agent-name` wins; otherwise the name the MCP server reported during the handshake."""
    return explicit or connected_client.server_info.name


async def run_evals(
    *,
    evals_dir: Path,
    results_path: str,
    model: str,
    max_tool_steps: int,
    mcp_command: str | None,
    mcp_url: str | None,
    mcp_bearer_token: str | None,
    select: str | None,
    exclude: str | None,
    agent_name: str | None,
    target: str | None,
    ignore_tools: list[str],
    default_database: str | None,
    default_schema: str | None,
    mcp_cwd: str | None,
    mcp_env: list[str],
    grading_model: str,
) -> int:
    """Runs the selected evals and stores the results; returns how many fell below
    their thresholds (`run` exits 1 when any did)."""
    try:
        definitions = load_evals(evals_dir)
    except ValueError as exc:
        raise RunError(str(exc)) from exc
    if not definitions:
        raise RunError(f"No evals found in {evals_dir}")

    try:
        definitions = select_evals(definitions, select=select, exclude=exclude)
    except SelectorError as exc:
        raise RunError(str(exc)) from exc
    if not definitions:
        raise RunError(nothing_selected(select, exclude))

    from .anthropic_agent_runner import MAX_TOKENS, AnthropicMCPAgentClient
    from .mcp_client import build_mcp_client, describe_connection_error

    judge = make_judge(provider_for(grading_model))
    run_id = str(uuid.uuid4())
    click.echo(f"Starting eval run {run_id} ({len(definitions)} eval{'' if len(definitions) == 1 else 's'})...")
    for warning in number_format_warnings(definitions):
        click.echo(f"    WARNING: {warning}")

    mcp_client = build_mcp_client(
        command=mcp_command, url=mcp_url, bearer_token=mcp_bearer_token, cwd=mcp_cwd, env_names=mcp_env
    )
    # Deliberately split from the eval loop below: a failure *here* means
    # the MCP handshake itself never completed (wrong token, unreachable
    # server, server crashed on startup, ...) -- every eval would fail
    # identically for a reason that has nothing to do with the agent, so
    # this fails the whole run loudly instead of grading N unusable
    # results. A tool call failing *during* an eval (bad SQL, a query the
    # agent got wrong) is a different, legitimate grading failure and is
    # deliberately NOT caught here -- see eval_loop.
    try:
        connected = await mcp_client.__aenter__()
    except Exception as exc:
        raise RunError(
            "Could not establish the MCP connection -- no evals were run, nothing was graded.\n"
            f"{describe_connection_error(exc)}"
        ) from exc
    con = connect(results_path)
    try:
        agent_name = resolve_agent_name(agent_name, connected)
        click.echo(f"Evaluating agent: {agent_name}")
        tools = (await connected.list_tools()).tools
        # Instructions the server sends when it connects; Claude's clients put them in the
        # model's context, so the agent under test gets them too.
        instructions = getattr(connected, "instructions", None) or None
        openai_agent = provider_for(model) == OPENAI
        recorder = RunRecorder(con)
        recorder.start_run(
            run_id,
            agent_name=agent_name,
            target=target,
            model=model,
            judge_model=grading_model,  # the raw layer's column keeps its first name
            settings={
                "max_tool_steps": max_tool_steps,
                "max_tokens": None if openai_agent else MAX_TOKENS,
                "mcp": {"url": mcp_url} if mcp_url else {"command": mcp_command},
                "ignore_tools": ignore_tools,
                "default_database": default_database,
                "default_schema": default_schema,
                "server_instructions": instructions,
            },
            tools_offered=tools,
        )
        # SQL that isn't a read never reaches the server (sql_guard.py).
        sql_fields = {tool: field for d in definitions for tool, field in d.sql_fields.items()}
        tool_caller = ReadOnlySQL(connected, sql_fields, ignore_tools)
        if openai_agent:
            from .openai_agent_runner import OpenAIMCPAgentClient

            agent = OpenAIMCPAgentClient(
                tool_caller,
                model=model,
                tools=tools,
                max_tool_steps=max_tool_steps,
                instructions=instructions,
                cache_key=f"honest-agent-{run_id}",
            )
        else:
            agent = AnthropicMCPAgentClient(
                tool_caller, model=model, tools=tools, max_tool_steps=max_tool_steps, instructions=instructions
            )
        click.echo(f"Model: {model} · grading model: {grading_model}")
        rows = await eval_loop(agent, definitions, judge, grading_model, run_id, recorder, con)
    finally:
        con.close()
        await mcp_client.__aexit__(None, None, None)

    click.echo(f"Wrote {len(rows)} result(s) to {results_path}")

    failures = failing_rows(rows)
    if failures:
        click.echo(f"{len(failures)}/{len(rows)} eval(s) below threshold this run:")
        for f in failures:
            bits = []
            if not f["accuracy_pass"]:
                bits.append(f"accuracy {f['accuracy_score']:.2f} < {f['accuracy_min_score']}")
            if not f["provenance_pass"]:
                bits.append(f"provenance {f['provenance_score']:.2f} < {f['provenance_min_score']}")
            click.echo(f"  - {f['eval_id']}: {', '.join(bits)}")
    else:
        click.echo("All evals met their thresholds.")

    click.echo(f"Run {run_id} complete. Next: `honest-agent report` / `honest-agent notify`.")
    return len(failures)
