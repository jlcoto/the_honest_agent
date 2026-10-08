from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

import click
from click.core import ParameterSource
from dotenv import find_dotenv, load_dotenv

from . import notify as notify_mod
from . import report as report_mod
from . import serve as serve_mod
from .agent_runner import AgentClient
from .config_file import (
    CONFIG_FILE_NAME,
    Config,
    ConfigError,
    Target,
    find_config_file,
    load_config,
    missing_config_hint,
)
from .derive import derive_result, recorded_answer
from .eval_loader import EvalDefinition, filter_by_tags, load_evals
from .grading import GRADING_MAX_TOKENS, grading_prompt
from .llm import API_KEY_ENV, OPENAI, Judge, default_model, make_judge, provider_for
from .raw import RunRecorder, read_records
from .storage import (
    RESULTS_TOKEN_ENV,
    connect,
    export_to_s3_parquet,
    is_motherduck,
    motherduck_database,
    read_all_results,
    results_exist,
    write_derived,
)
from .thresholds import failing_rows

DEFAULT_RESULTS_PATH = "./honest_agent_results/results.duckdb"
_RESULTS_PATH_HELP = (
    "Local DuckDB file where results are stored (created on first `run`), or a MotherDuck "
    f"database as md:<name>, opened with {RESULTS_TOKEN_ENV}."
)
DEFAULT_REPORT_DIR = "honest_agent_report"
DEFAULT_MAX_TOOL_STEPS = 5
_REPORT_DIR_HELP = "Report folder (web UI + data/report.json)."


@click.group()
@click.option(
    "--env-file",
    envvar="HONEST_AGENT_ENV_FILE",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Load settings and API keys from this file instead of the .env found from the current directory "
    "(or its parents). Variables already set in your shell take precedence.",
)
@click.option(
    "--config-file",
    envvar="HONEST_AGENT_CONFIG_FILE",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help=f"Read settings and targets from this file instead of the {CONFIG_FILE_NAME} "
    "found from the current directory (or its parents).",
)
@click.pass_context
def main(ctx: click.Context, env_file: str | None, config_file: str | None):
    """honest-agent: run LLM evals against an agent, grade them, and store the results."""
    # usecwd: look from where the command runs, not from where honest-agent is installed --
    # otherwise a tool or editable install would find some other project's .env, or none.
    load_dotenv(env_file or find_dotenv(usecwd=True))
    ctx.obj = Path(config_file) if config_file else find_config_file(Path.cwd())


def _config(ctx: click.Context) -> Config | None:
    path = ctx.find_root().obj
    if path is None:
        return None
    try:
        return load_config(path)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc


def _results_path(ctx: click.Context, results_path: str | None) -> str:
    """--results-path, else the config file's results_path, else the default."""
    if results_path is None:
        config = _config(ctx)
        results_path = (config and config.results_path) or DEFAULT_RESULTS_PATH
    if is_motherduck(results_path):
        if "token" in results_path.lower():
            raise click.ClickException(
                f"Don't put a token in results_path; set {RESULTS_TOKEN_ENV} in .env instead, "
                "so it stays out of config files and shell history."
            )
        try:
            motherduck_database(results_path)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        if not os.environ.get(RESULTS_TOKEN_ENV):
            raise click.ClickException(
                f"{RESULTS_TOKEN_ENV} is not set. Results in MotherDuck ({results_path}) are opened with it: "
                "a read/write token for a service account, not the motherduck target's MOTHERDUCK_TOKEN."
            )
    return results_path


def _from_layers(ctx: click.Context, param: str, value, target: Target | None, key: str | None = None):
    """Applies flag > environment variable > config file > built-in default to one setting.
    `value` is what Click resolved (flag, env var, or its own default); the file only fills in
    when Click fell back to its default. An env var beating the file gets a note, so a stale
    variable in .env never overrides a target silently."""
    file_value = target.settings.get(key or param) if target else None
    source = ctx.get_parameter_source(param)
    if file_value is None or source is ParameterSource.COMMANDLINE:
        return value
    if source is ParameterSource.ENVIRONMENT:
        if value != file_value:
            click.echo(
                f"Note: {_envvar(ctx, param)} from the environment overrides target {target.name!r} "
                f"({key or param} in {CONFIG_FILE_NAME})."
            )
        return value
    return file_value


def _envvar(ctx: click.Context, param: str) -> str:
    return next(p.envvar for p in ctx.command.params if p.name == param)


async def _eval_loop(
    agent: AgentClient,
    definitions: list[EvalDefinition],
    judge: Judge,
    judge_model: str,
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
            prompt = grading_prompt(definition.grading_method, answer, definition.expected_answer, definition.prompt)
            if prompt is not None:
                request = {"model": judge_model, "max_tokens": GRADING_MAX_TOKENS, "prompt": prompt}
                await record.call(
                    "grading_call",
                    provider_for(judge_model),
                    request,
                    judge.complete(prompt, model=judge_model, max_tokens=GRADING_MAX_TOKENS),
                )
            derived = derive_result(con, result_id)
        except Exception as exc:
            record.eval_error(exc)
            raise
        write_derived(con, [derived.row])
        for sql in derived.unparsed:
            click.echo(f"    WARNING: couldn't parse this SQL, so it doesn't count toward provenance: {sql[:80]!r}")
        rows.append(derived.row)
    return rows


def _resolve_server(
    ctx: click.Context,
    command: str | None,
    url: str | None,
    bearer_token: str | None,
    target: Target | None,
) -> tuple[str | None, str | None, str | None]:
    """Picks the MCP server (stdio command or HTTP URL) and its bearer token from the first
    layer that names a server: flags, then environment variables, then the config file's
    target. The token follows the server it was set up for: a target's token comes from its
    `bearer_token_env`, and MCP_BEARER_TOKEN only applies to a server set by flag or env var --
    so a token for one vendor is never sent to another target's server. A --mcp-bearer-token
    flag still wins everywhere."""
    sources = {"command": ctx.get_parameter_source("mcp_command"), "url": ctx.get_parameter_source("mcp_url")}
    file_command = target.settings.get("mcp_command") if target else None
    file_url = target.settings.get("mcp_url") if target else None

    for layer in (ParameterSource.COMMANDLINE, ParameterSource.ENVIRONMENT):
        layer_command = command if sources["command"] is layer else None
        layer_url = url if sources["url"] is layer else None
        if not (layer_command or layer_url):
            continue
        if layer_command and layer_url:
            if layer is ParameterSource.COMMANDLINE:
                raise click.ClickException("Pass either --mcp-command (stdio) or --mcp-url (HTTP), not both.")
            raise click.ClickException(
                "Both MCP_COMMAND and MCP_URL are set in the environment (or .env). "
                "Pass --mcp-command or --mcp-url to choose one."
            )
        if layer is ParameterSource.ENVIRONMENT and (file_command or file_url):
            name = "MCP_COMMAND" if layer_command else "MCP_URL"
            click.echo(f"Note: {name} from the environment overrides target {target.name!r}'s MCP server.")
        return layer_command, layer_url, bearer_token

    if not (file_command or file_url):
        hint = missing_config_hint(Path.cwd()) if _config(ctx) is None else ""
        raise click.ClickException(
            f"--mcp-command or --mcp-url is required (or a target with mcp_command/mcp_url in {CONFIG_FILE_NAME})."
            + hint
        )
    if ctx.get_parameter_source("mcp_bearer_token") is ParameterSource.COMMANDLINE:
        return file_command, file_url, bearer_token
    token_env = target.settings.get("bearer_token_env")
    if token_env is None:
        return file_command, file_url, None
    if not os.environ.get(token_env):
        raise click.ClickException(
            f"{token_env} is not set. Target {target.name!r} reads its bearer token from it (bearer_token_env). "
            "Add it to .env or export it."
        )
    return file_command, file_url, os.environ[token_env]


def _resolve_agent_name(explicit: str | None, connected_client) -> str:
    """`--agent-name` wins; otherwise the name the MCP server reported during the handshake."""
    return explicit or connected_client.server_info.name


async def _run_async(
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
    mcp_cwd: str | None,
    mcp_env: list[str],
    judge_model: str,
) -> None:
    try:
        definitions = load_evals(evals_dir)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if not definitions:
        raise click.ClickException(f"No evals found in {evals_dir}")

    definitions = filter_by_tags(definitions, select=select, exclude=exclude)
    if not definitions:
        raise click.ClickException(f"No evals matched --select {select!r} --exclude {exclude!r}")

    from .anthropic_agent_runner import MAX_TOKENS, AnthropicMCPAgentClient
    from .mcp_client import build_mcp_client, describe_connection_error

    judge = make_judge(provider_for(judge_model))
    run_id = str(uuid.uuid4())
    click.echo(f"Starting eval run {run_id} ({len(definitions)} eval{'' if len(definitions) == 1 else 's'})...")

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
    # deliberately NOT caught here -- see _eval_loop.
    try:
        connected = await mcp_client.__aenter__()
    except Exception as exc:
        raise click.ClickException(
            "Could not establish the MCP connection -- no evals were run, nothing was graded.\n"
            f"{describe_connection_error(exc)}"
        ) from exc
    con = connect(results_path)
    try:
        agent_name = _resolve_agent_name(agent_name, connected)
        click.echo(f"Evaluating agent: {agent_name}")
        tools = (await connected.list_tools()).tools
        openai_agent = provider_for(model) == OPENAI
        recorder = RunRecorder(con)
        recorder.start_run(
            run_id,
            agent_name=agent_name,
            target=target,
            model=model,
            judge_model=judge_model,
            settings={
                "max_tool_steps": max_tool_steps,
                "max_tokens": None if openai_agent else MAX_TOKENS,
                "mcp": {"url": mcp_url} if mcp_url else {"command": mcp_command},
                "ignore_tools": ignore_tools,
            },
            tools_offered=tools,
        )
        if openai_agent:
            from .openai_agent_runner import OpenAIMCPAgentClient

            agent = OpenAIMCPAgentClient(connected, model=model, tools=tools, max_tool_steps=max_tool_steps)
        else:
            agent = AnthropicMCPAgentClient(connected, model=model, tools=tools, max_tool_steps=max_tool_steps)
        click.echo(f"Model: {model} · judge model: {judge_model}")
        rows = await _eval_loop(agent, definitions, judge, judge_model, run_id, recorder, con)
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


@main.command()
@click.option(
    "--target",
    "-t",
    default=None,
    help=f"Target (agent) from {CONFIG_FILE_NAME} to evaluate. Defaults to its default_target.",
)
@click.option(
    "--evals-dir",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help="Directory of eval YAML files. Defaults to the target's evals_dir, else ./evals.",
)
@click.option("--results-path", default=None, help=_RESULTS_PATH_HELP)
@click.option(
    "--model",
    envvar="HONEST_AGENT_MODEL",
    default=None,
    help="Model to evaluate (the agent under test): a Claude model, or an OpenAI one (gpt-*, o3, o4-mini, ...). "
    "Only the API key for its provider is needed. Defaults to claude-haiku-4-5 if ANTHROPIC_API_KEY is set, "
    "else gpt-5.4-mini if OPENAI_API_KEY is set.",
)
@click.option(
    "--judge-model",
    envvar="HONEST_AGENT_JUDGE_MODEL",
    default=None,
    help="Model that grades extract_match/llm_judge evals. Defaults to --model. A fixed judge across "
    "runs keeps comparisons between agent models fair.",
)
@click.option(
    "--max-tool-steps",
    type=click.IntRange(min=1),
    default=DEFAULT_MAX_TOOL_STEPS,
    help="Max steps per eval before giving up: each step is one model API call and the tool calls it asks for. "
    "If Claude is still requesting tools when this is hit, that eval fails with a clear error "
    "instead of silently returning an empty answer.",
)
@click.option(
    "--mcp-command",
    envvar="MCP_COMMAND",
    default=None,
    help="Shell command launching a local MCP server over stdio, "
    'e.g. "python mcp_server/server.py". Mutually exclusive with --mcp-url; when given on the '
    "command line, it overrides an MCP_URL set in the environment.",
)
@click.option(
    "--mcp-url",
    envvar="MCP_URL",
    default=None,
    help="URL of a remote MCP server's streamable-HTTP endpoint. Mutually exclusive with "
    "--mcp-command; when given on the command line, it overrides an MCP_COMMAND set in the "
    "environment.",
)
@click.option(
    "--mcp-bearer-token",
    envvar="MCP_BEARER_TOKEN",
    default=None,
    help="[--mcp-url only] Bearer token sent as the Authorization header.",
)
@click.option(
    "--mcp-env",
    multiple=True,
    metavar="NAME",
    help="[--mcp-command only] Environment variable the local MCP server needs, e.g. MOTHERDUCK_TOKEN. "
    "Repeat for several. The server gets only these plus a minimal environment (PATH, HOME, ...), "
    "never the rest of .env. Defaults to the target's mcp_env.",
)
@click.option(
    "--agent-name",
    envvar="HONEST_AGENT_AGENT_NAME",
    default=None,
    help="Label for the agent being evaluated (e.g. snowflake, motherduck), stored with every result "
    "so reports can filter by agent. Defaults to the target's agent_name or name, else the name the "
    "MCP server reports about itself.",
)
@click.option(
    "--select",
    "-s",
    default=None,
    help="Only run evals matching this tag selector, dbt-`--select`-style: space-separated "
    "groups are OR'd, comma-separated tags within a group are AND'd, e.g. "
    "'--select \"smoke,provenance motherduck\"' runs evals tagged both smoke AND "
    "provenance, OR tagged motherduck. A `tag:` prefix (e.g. `tag:smoke`) is accepted but optional.",
)
@click.option(
    "--exclude",
    default=None,
    help="Skip evals matching this tag selector (same syntax as --select), applied after --select.",
)
@click.pass_context
def run(
    ctx: click.Context,
    target: str | None,
    evals_dir: str | None,
    results_path: str | None,
    model: str | None,
    judge_model: str | None,
    max_tool_steps: int,
    mcp_command: str | None,
    mcp_url: str | None,
    mcp_bearer_token: str | None,
    mcp_env: tuple[str, ...],
    agent_name: str | None,
    select: str | None,
    exclude: str | None,
):
    """Run every eval, grade the answers, and write results to storage."""
    config = _config(ctx)
    if config is None and target is not None:
        raise click.ClickException(
            f"--target {target} needs a {CONFIG_FILE_NAME}, and none was found." + missing_config_hint(Path.cwd())
        )
    try:
        chosen = config.target(target) if config and config.targets else None
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    if chosen:
        click.echo(f"Target: {chosen.name} ({config.path})")

    # Without targets, the file's top-level model/judge_model/max_tool_steps still apply.
    layer = chosen or (Target("config", config.shared) if config else None)
    model = _from_layers(ctx, "model", model, layer)
    judge_model = _from_layers(ctx, "judge_model", judge_model, layer)
    max_tool_steps = _from_layers(ctx, "max_tool_steps", max_tool_steps, layer)
    evals_dir = evals_dir or (chosen and chosen.settings.get("evals_dir")) or "evals"
    if not Path(evals_dir).is_dir():
        raise click.ClickException(f"Evals folder {evals_dir} not found. Pass --evals-dir or set evals_dir.")
    if chosen:
        # A target names the agent: its agent_name, else the target's own name.
        named = Target(chosen.name, {"agent_name": chosen.settings.get("agent_name") or chosen.name})
        agent_name = _from_layers(ctx, "agent_name", agent_name, named)

    if not model:
        model = default_model(os.environ)
        if model is None:
            raise click.ClickException(
                "No model API key set. Add ANTHROPIC_API_KEY (Claude) or OPENAI_API_KEY (GPT) to .env, or export it."
            )
        click.echo(f"No --model given; using {model} ({API_KEY_ENV[provider_for(model)]} is set).")
    judge_model = judge_model or model
    providers = {provider_for(model), provider_for(judge_model)}
    missing = [API_KEY_ENV[p] for p in sorted(providers) if not os.environ.get(API_KEY_ENV[p])]
    if missing:
        raise click.ClickException(
            f"{' and '.join(missing)} not set. `honest-agent run` needs the API key for the provider of "
            f"--model ({model}) and --judge-model ({judge_model}). Export it or add it to .env."
        )
    mcp_command, mcp_url, mcp_bearer_token = _resolve_server(ctx, mcp_command, mcp_url, mcp_bearer_token, chosen)
    # A target's mcp_command runs from the config file's folder, wherever `run` is started.
    from_target = chosen is not None and mcp_command is not None and mcp_command == chosen.settings.get("mcp_command")
    mcp_cwd = str(config.path.parent) if from_target else None
    # Like its token, a target's mcp_env belongs to its own server.
    env_names = list(mcp_env) or (chosen.settings.get("mcp_env", []) if from_target else [])
    unset = [name for name in env_names if name not in os.environ]
    if unset:
        raise click.ClickException(
            f"{', '.join(unset)} not set, but the MCP server needs it (mcp_env). Add it to .env or export it."
        )

    asyncio.run(
        _run_async(
            evals_dir=Path(evals_dir).resolve(),
            results_path=_results_path(ctx, results_path),
            model=model,
            max_tool_steps=max_tool_steps,
            mcp_command=mcp_command,
            mcp_url=mcp_url,
            mcp_bearer_token=mcp_bearer_token,
            select=select,
            exclude=exclude,
            agent_name=agent_name,
            target=chosen.name if chosen else None,
            ignore_tools=chosen.settings.get("ignore_tools", []) if chosen else [],
            mcp_cwd=mcp_cwd,
            mcp_env=env_names,
            judge_model=judge_model,
        )
    )


@main.command()
@click.option("--results-path", default=None, help=_RESULTS_PATH_HELP)
@click.option("--out", default=DEFAULT_REPORT_DIR, type=click.Path(file_okay=False), help=_REPORT_DIR_HELP)
@click.pass_context
def report(ctx: click.Context, results_path: str | None, out: str):
    """Write the report (web UI + data from all stored results) to a folder."""
    results_path = _results_path(ctx, results_path)
    try:
        report_mod.generate(results_path, Path(out))
    except (FileNotFoundError, report_mod.ReportFolderError) as e:
        raise click.ClickException(str(e)) from e
    click.echo(f"Wrote {out}/. View it with `honest-agent serve --out {out}`.")


@main.command()
@click.option("--out", default=DEFAULT_REPORT_DIR, type=click.Path(exists=True, file_okay=False), help=_REPORT_DIR_HELP)
@click.option("--port", default=8000, type=int)
@click.option("--open-browser/--no-open-browser", default=True)
def serve(out: str, port: int, open_browser: bool):
    """Serve a generated report folder locally, the same way `dbt docs serve` does."""
    click.echo(f"Serving {out}/ at http://127.0.0.1:{port}/ (Ctrl+C to stop)")
    serve_mod.serve(Path(out), port, open_browser=open_browser)


@main.command()
@click.option(
    "--target",
    default=None,
    help=f"Target (agent) from {CONFIG_FILE_NAME} to alert on. Defaults to its default_target.",
)
@click.option("--results-path", default=None, help=_RESULTS_PATH_HELP)
@click.option("--webhook-url", envvar="SLACK_WEBHOOK_URL", default=None)
@click.option(
    "--report-url",
    envvar="HONEST_AGENT_REPORT_URL",
    default=None,
    help="Where the report is published, so the alert links to each failing eval.",
)
@click.pass_context
def notify(
    ctx: click.Context, target: str | None, results_path: str | None, webhook_url: str | None, report_url: str | None
):
    """Send a Slack alert if the target's most recent run had any eval below its threshold."""
    results_path = _results_path(ctx, results_path)
    if not webhook_url:
        raise click.ClickException("No Slack webhook URL. Pass --webhook-url or set SLACK_WEBHOOK_URL.")
    config = _config(ctx)
    if config is None and target is not None:
        raise click.ClickException(
            f"--target {target} needs a {CONFIG_FILE_NAME}, and none was found." + missing_config_hint(Path.cwd())
        )
    try:
        chosen = config.target(target) if config and config.targets else None
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    # Without targets there's one agent to alert on: whichever ran last.
    agent_name = (chosen.settings.get("agent_name") or chosen.name) if chosen else None
    notify_mod.notify_on_failures(results_path, webhook_url, agent_name, report_url)


@main.command()
@click.option("--results-path", default=None, help=_RESULTS_PATH_HELP)
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
@click.pass_context
def export(ctx: click.Context, results_path: str | None, s3_path: str, run_id: str | None):
    """Export stored results to S3 as Parquet -- entirely optional; nothing else requires this."""
    results_path = _results_path(ctx, results_path)
    written = export_to_s3_parquet(results_path, s3_path, run_id=run_id)
    click.echo(f"Exported to {written}")


@main.command()
@click.option("--results-path", default=None, help=_RESULTS_PATH_HELP)
@click.option("--run-id", default=None, help="Only rebuild this run.")
@click.pass_context
def rebuild(ctx: click.Context, results_path: str | None, run_id: str | None):
    """Re-derive results, SQL calls and traces from the raw record of past runs, after a
    change to how honest-agent scores or reads them. Calls no model: it costs nothing and
    uses each run's own settings and eval definitions. Runs recorded before honest-agent
    kept raw records, and evals stopped by an error, are left as they are."""
    from .raw import has_raw_layer

    results_path = _results_path(ctx, results_path)
    if not results_exist(results_path):
        raise click.ClickException(f"No results file at {results_path}.")
    con = connect(results_path)
    try:
        if not has_raw_layer(con):
            raise click.ClickException("This results file has no raw records yet; nothing to rebuild.")
        # An eval stopped by an error has nothing to derive, as during the run.
        clauses = ["not exists (select 1 from raw.events v where v.result_id = e.result_id and v.kind = 'eval_error')"]
        params = []
        if run_id:
            clauses.append("e.run_id = ?")
            params.append(run_id)
        query = f"select e.result_id from raw.evals e where {' and '.join(clauses)} order by e.started_at"
        result_ids = [row[0] for row in con.execute(query, params).fetchall()]
        for result_id in result_ids:
            write_derived(con, [derive_result(con, result_id).row])
        runs = {row[0] for row in con.execute("select distinct run_id from raw.evals").fetchall()}
    finally:
        con.close()
    if run_id and not result_ids:
        raise click.ClickException(f"No raw records for run {run_id}.")
    click.echo(f"Rebuilt {len(result_ids)} result(s) from {1 if run_id else len(runs)} run(s) in {results_path}.")


@main.command()
@click.option("--results-path", default=None, help=_RESULTS_PATH_HELP)
@click.option("--run-id", default=None, help="Only show logs for this run.")
@click.option("--eval-id", default=None, help="Only show logs for this eval id.")
@click.option("--json", "as_json", is_flag=True, help="Print the raw records as JSON, exactly as stored.")
@click.pass_context
def logs(ctx: click.Context, results_path: str | None, run_id: str | None, eval_id: str | None, as_json: bool):
    """Print what each matching eval sent and received, call by call, as recorded: every
    model call, tool call and grading call with its request, response and timing. Scores
    and SQL summaries are in the report (`honest-agent report`)."""
    results_path = _results_path(ctx, results_path)
    records = read_records(results_path, run_id=run_id, eval_id=eval_id)
    if as_json:
        click.echo(json.dumps(records, indent=2, default=str))
        return
    if not records:
        derived = [
            r
            for r in read_all_results(results_path)
            if (run_id is None or r["run_id"] == run_id) and (eval_id is None or r["eval_id"] == eval_id)
        ]
        if derived:
            click.echo(
                "These results were recorded before honest-agent kept raw records, so there is no log "
                "to show. See them in the report (`honest-agent report`)."
            )
        else:
            click.echo("No matching logs found.")
        return

    def pretty(value: str | None) -> str:
        return json.dumps(json.loads(value), indent=2) if value is not None else "null"

    for record in records:
        run, evaluation = record["run"], record["eval"]
        click.echo(
            f"=== eval {evaluation['eval_id']} (run {evaluation['run_id']}, result {evaluation['result_id']}) ==="
        )
        click.echo(
            f"{run['agent_name']} · {run['model']} · judge {run['judge_model']} · started {evaluation['started_at']}"
        )
        for event in record["events"]:
            provider = f" ({event['provider']})" if event["provider"] else ""
            click.echo(f"--- #{event['seq']} {event['kind']}{provider} · {event['duration_ms']} ms")
            if event["request"] is not None:
                click.echo(f"request: {pretty(event['request'])}")
            if event["response"] is not None:
                click.echo(f"response: {pretty(event['response'])}")
            if event["error"]:
                click.echo(f"error: {event['error']}")
        click.echo()


if __name__ == "__main__":
    main()
