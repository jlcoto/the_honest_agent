from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import click
from dotenv import load_dotenv

from . import notify as notify_mod
from . import report as report_mod
from . import serve as serve_mod
from .agent_runner import AgentClient
from .grading import grade_accuracy
from .provenance import score_provenance
from .quiz_loader import QuizDefinition, filter_by_tags, load_quizzes
from .sql_capture import extract_sql_calls
from .storage import export_to_s3_parquet, read_agent_logs, read_all_results, read_tool_calls, write_run_results
from .thresholds import failing_rows

# picks up a .env from the cwd or any parent directory (e.g. the repo root's), if
# one exists -- never overrides variables already set in the environment.
load_dotenv()

DEFAULT_RESULTS_PATH = "./agent_quiz_results/results.duckdb"
_RESULTS_PATH_HELP = "Local DuckDB file where results are stored (created on first `run`)."
DEFAULT_REPORT_DIR = "agent_quiz_report"
_REPORT_DIR_HELP = "Report folder (web UI + data/report.json)."


@click.group()
def main():
    """agent-quiz: run LLM quizzes against an agent, grade them, and store the results."""


async def _quiz_loop(
    agent: AgentClient,
    definitions: list[QuizDefinition],
    judge_client,
    model: str,
    run_id: str,
) -> list[dict]:
    rows: list[dict] = []
    for definition in definitions:
        click.echo(f"  - {definition.quiz_id}: {definition.prompt!r}")
        result = await agent.run(definition.prompt)
        if result.hit_turn_limit:
            click.echo(f"    WARNING: {definition.quiz_id} hit the tool-turn limit without a final answer.")

        accuracy_score, rationale, grading_input_tokens, grading_output_tokens = await grade_accuracy(
            definition.grading_method,
            result.answer,
            definition.expected_answer,
            definition.prompt,
            client=judge_client,
            model=model,
            tolerance=definition.tolerance,
            tolerance_percent=definition.tolerance_percent,
        )
        sql_calls = extract_sql_calls(result.raw_trace, definition.sql_fields)
        provenance_score = score_provenance(
            [call["sql"] for call in sql_calls],
            definition.expected_sources,
            definition.expected_database,
            definition.expected_schema,
        )
        result_id = str(uuid.uuid4())

        rows.append(
            {
                # -- results --
                "result_id": result_id,
                "run_id": run_id,
                "run_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "quiz_id": definition.quiz_id,
                "prompt": definition.prompt,
                "category": definition.category,
                "tags": definition.tags,
                "expected_answer": definition.expected_answer,
                "agent_answer": result.answer,
                "tools_used": result.tools_used,
                "accuracy_score": accuracy_score,
                "accuracy_method": definition.grading_method,
                "accuracy_rationale": rationale,
                "accuracy_min_score": definition.accuracy_min_score,
                "provenance_score": provenance_score,
                "expected_sources": definition.expected_sources,
                "expected_database": definition.expected_database,
                "expected_schema": definition.expected_schema,
                "provenance_min_score": definition.provenance_min_score,
                "model_name": result.model_name,
                "agent_backend": "mcp",
                "latency_ms": result.latency_ms,
                "agent_input_tokens": result.input_tokens,
                "agent_output_tokens": result.output_tokens,
                "grading_input_tokens": grading_input_tokens,
                "grading_output_tokens": grading_output_tokens,
                # -- agent_logs --
                "agent_trace": json.dumps(result.raw_trace),
                # -- tool_calls (expanded into one row per call by storage.py) --
                "sql_calls": sql_calls,
            }
        )
    return rows


def _describe_mcp_connection_error(exc: BaseException) -> str:
    """MCP handshake failures typically arrive wrapped in nested
    (Base)ExceptionGroups (anyio task groups) -- unwrap them so the actual
    reason (e.g. an auth error from the server) is visible instead of just
    "unhandled errors in a TaskGroup". Duck-typed on `.exceptions` rather
    than `isinstance(exc, BaseExceptionGroup)` since that builtin doesn't
    exist before Python 3.11, one version above this package's own floor.
    """
    nested = getattr(exc, "exceptions", None)
    if nested:
        return "; ".join(_describe_mcp_connection_error(e) for e in nested)
    return str(exc)


async def _run_async(
    quizzes_dir_p: Path,
    results_path: str,
    model: str,
    max_tool_turns: int,
    mcp_command: str | None,
    mcp_url: str | None,
    mcp_bearer_token: str | None,
    select: str | None,
    exclude: str | None,
) -> None:
    definitions = load_quizzes(quizzes_dir_p)
    if not definitions:
        raise click.ClickException(f"No quizzes found in {quizzes_dir_p}")

    definitions = filter_by_tags(definitions, select=select, exclude=exclude)
    if not definitions:
        raise click.ClickException(f"No quizzes matched --select {select!r} --exclude {exclude!r}")

    import anthropic

    from .mcp_agent_runner import MCPAgentClient, build_mcp_client

    judge_client = anthropic.AsyncAnthropic()
    run_id = str(uuid.uuid4())
    click.echo(f"Starting quiz run {run_id} ({len(definitions)} quizzes)...")

    mcp_client = build_mcp_client(command=mcp_command, url=mcp_url, bearer_token=mcp_bearer_token)
    # Deliberately split from the quiz loop below: a failure *here* means
    # the MCP handshake itself never completed (wrong token, unreachable
    # server, server crashed on startup, ...) -- every quiz would fail
    # identically for a reason that has nothing to do with the agent, so
    # this fails the whole run loudly instead of grading N unusable
    # results. A tool call failing *during* a quiz (bad SQL, a query the
    # agent got wrong) is a different, legitimate grading failure and is
    # deliberately NOT caught here -- see _quiz_loop.
    try:
        connected = await mcp_client.__aenter__()
    except Exception as exc:
        raise click.ClickException(
            "Could not establish the MCP connection -- no quizzes were run, nothing was graded.\n"
            f"{_describe_mcp_connection_error(exc)}"
        ) from exc
    try:
        agent = MCPAgentClient(connected, model=model, max_tool_turns=max_tool_turns)
        rows = await _quiz_loop(agent, definitions, judge_client, model, run_id)
    finally:
        await mcp_client.__aexit__(None, None, None)

    written_path = write_run_results(results_path, run_id, rows)
    click.echo(f"Wrote {len(rows)} result(s) to {written_path}")

    failures = failing_rows(rows)
    if failures:
        click.echo(f"{len(failures)}/{len(rows)} quiz(zes) below threshold this run:")
        for f in failures:
            bits = []
            if not f["accuracy_pass"]:
                bits.append(f"accuracy {f['accuracy_score']:.2f} < {f['accuracy_min_score']}")
            if not f["provenance_pass"]:
                bits.append(f"provenance {f['provenance_score']:.2f} < {f['provenance_min_score']}")
            click.echo(f"  - {f['quiz_id']}: {', '.join(bits)}")
    else:
        click.echo("All quizzes met their thresholds.")

    click.echo(f"Run {run_id} complete. Next: `agent-quiz report` / `agent-quiz notify`.")


@main.command()
@click.option(
    "--quizzes-dir",
    default="quizzes",
    type=click.Path(exists=True, file_okay=False),
    help="Directory of quiz YAML files.",
)
@click.option("--results-path", default=DEFAULT_RESULTS_PATH, help=_RESULTS_PATH_HELP)
@click.option("--model", default="claude-haiku-4-5-20251001", help="Claude model to quiz, and to use as the LLM judge.")
@click.option(
    "--max-tool-turns",
    type=click.IntRange(min=1),
    default=5,
    help="Max rounds of tool calls per quiz before giving up (each round is one Claude API call). "
    "If Claude is still requesting tools when this is hit, that quiz fails with a clear error "
    "instead of silently returning an empty answer.",
)
@click.option(
    "--mcp-command",
    envvar="MCP_COMMAND",
    default=None,
    help="Shell command launching a local MCP server over stdio, "
    'e.g. "python mcp_server/server.py". Mutually exclusive with --mcp-url. Requires the '
    "'mcp' extra.",
)
@click.option(
    "--mcp-url",
    envvar="MCP_URL",
    default=None,
    help="URL of a remote MCP server's streamable-HTTP endpoint. "
    "Mutually exclusive with --mcp-command. Requires the 'mcp' extra.",
)
@click.option(
    "--mcp-bearer-token",
    envvar="MCP_BEARER_TOKEN",
    default=None,
    help="[--mcp-url only] Bearer token sent as the Authorization header.",
)
@click.option(
    "--select",
    "-s",
    default=None,
    help="Only run quizzes matching this tag selector, dbt-`--select`-style: space-separated "
    "groups are OR'd, comma-separated tags within a group are AND'd, e.g. "
    "'--select \"smoke,provenance motherduck\"' runs quizzes tagged both smoke AND "
    "provenance, OR tagged motherduck. A `tag:` prefix (e.g. `tag:smoke`) is accepted but optional.",
)
@click.option(
    "--exclude",
    default=None,
    help="Skip quizzes matching this tag selector (same syntax as --select), applied after --select.",
)
def run(
    quizzes_dir: str,
    results_path: str,
    model: str,
    max_tool_turns: int,
    mcp_command: str | None,
    mcp_url: str | None,
    mcp_bearer_token: str | None,
    select: str | None,
    exclude: str | None,
):
    """Run every quiz, grade the answers, and write results to storage."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise click.ClickException(
            "ANTHROPIC_API_KEY is not set. Export it before running `agent-quiz run` "
            "(it's needed both to quiz the agent and, for llm_judge-graded quizzes, to grade it)."
        )
    if not (mcp_command or mcp_url):
        raise click.ClickException("--mcp-command or --mcp-url is required.")

    asyncio.run(
        _run_async(
            Path(quizzes_dir).resolve(),
            results_path,
            model,
            max_tool_turns,
            mcp_command,
            mcp_url,
            mcp_bearer_token,
            select,
            exclude,
        )
    )


@main.command()
@click.option("--results-path", default=DEFAULT_RESULTS_PATH, help=_RESULTS_PATH_HELP)
@click.option("--out", default=DEFAULT_REPORT_DIR, type=click.Path(file_okay=False), help=_REPORT_DIR_HELP)
def report(results_path: str, out: str):
    """Write the report (web UI + data from all stored results) to a folder."""
    try:
        report_mod.generate(results_path, Path(out))
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e
    click.echo(f"Wrote {out}/. View it with `agent-quiz serve --out {out}`.")


@main.command()
@click.option("--out", default=DEFAULT_REPORT_DIR, type=click.Path(exists=True, file_okay=False), help=_REPORT_DIR_HELP)
@click.option("--port", default=8000, type=int)
@click.option("--open-browser/--no-open-browser", default=True)
def serve(out: str, port: int, open_browser: bool):
    """Serve a generated report folder locally, the same way `dbt docs serve` does."""
    click.echo(f"Serving {out}/ at http://127.0.0.1:{port}/ (Ctrl+C to stop)")
    serve_mod.serve(Path(out), port, open_browser=open_browser)


@main.command()
@click.option("--results-path", default=DEFAULT_RESULTS_PATH, help=_RESULTS_PATH_HELP)
@click.option("--webhook-url", envvar="SLACK_WEBHOOK_URL", default=None)
def notify(results_path: str, webhook_url: str | None):
    """Send a Slack alert if the most recent run had any quiz below its threshold."""
    if not webhook_url:
        raise click.ClickException("No Slack webhook URL. Pass --webhook-url or set SLACK_WEBHOOK_URL.")
    notify_mod.notify_on_failures(results_path, webhook_url)


@main.command()
@click.option("--results-path", default=DEFAULT_RESULTS_PATH, help=_RESULTS_PATH_HELP)
@click.option(
    "--s3-path",
    required=True,
    help="s3://bucket/prefix/results.parquet destination. Uses DuckDB's own httpfs extension "
    "(installed automatically) and its standard AWS credential resolution -- no separate S3 "
    "SDK or credential handling here.",
)
@click.option(
    "--run-id",
    default=None,
    help="Export only this run instead of every stored run.",
)
def export(results_path: str, s3_path: str, run_id: str | None):
    """Export stored results to S3 as Parquet -- entirely optional; nothing else requires this."""
    written = export_to_s3_parquet(results_path, s3_path, run_id=run_id)
    click.echo(f"Exported to {written}")


@main.command()
@click.option("--results-path", default=DEFAULT_RESULTS_PATH, help=_RESULTS_PATH_HELP)
@click.option("--run-id", default=None, help="Only show logs for this run.")
@click.option("--quiz-id", default=None, help="Only show logs for this quiz id.")
def logs(results_path: str, run_id: str | None, quiz_id: str | None):
    """Print each matching quiz's agent trace and any captured SQL, for digging into
    *why* a result came out the way it did (as opposed to `report`, which only shows
    scores)."""
    rows = read_agent_logs(results_path, run_id=run_id, quiz_id=quiz_id)
    if not rows:
        click.echo("No matching logs found.")
        return
    # Looked up per row below (not passed through read_agent_logs) so `agent_logs`
    # stays a pure trace table -- `results` already carries the answer/scores.
    results_by_id = {r["result_id"]: r for r in read_all_results(results_path)}
    calls_by_result: dict[str, list[dict]] = {}
    for call_row in read_tool_calls(results_path, run_id=run_id, quiz_id=quiz_id):
        calls_by_result.setdefault(call_row["result_id"], []).append(call_row)

    for row in rows:
        click.echo(f"=== quiz {row['quiz_id']} (run {row['run_id']}, result {row['result_id']}) ===")
        result_row = results_by_id.get(row["result_id"])
        if result_row:
            click.echo(f"Answer: {result_row['agent_answer']}")
            click.echo(
                f"Accuracy: {result_row['accuracy_score']:.2f} (min {result_row['accuracy_min_score']:.2f})  |  "
                f"Provenance: {result_row['provenance_score']:.2f} (min {result_row['provenance_min_score']:.2f})"
            )
        call_rows = calls_by_result.get(row["result_id"], [])
        if call_rows:
            click.echo("Tool calls:")
            for call_row in call_rows:
                click.echo(f"  [{call_row['tool_name']}] ({call_row['type']}) {call_row['payload']}")
        click.echo("Trace:")
        click.echo(json.dumps(json.loads(row["agent_trace"]), indent=2))
        click.echo()


if __name__ == "__main__":
    main()
