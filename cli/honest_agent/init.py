"""`honest-agent init`: writes the starter files of a new project, like `dbt init`.

Three files, each only if it doesn't exist yet: `honest_agent_config.yml` (one target),
`evals/first_eval.yml` (a placeholder eval) and `.env` (the variable names the setup
needs, values empty except the server URL the user typed). Account URLs go into `.env`
and the config reads them with `{{ env_var() }}`, so the config can be committed. `init`
never asks for a secret and never edits `.gitignore`; it says what to add instead.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import click

REPO = "https://github.com/jlcoto/the_honest_agent/blob/main"
CONFIG_DOCS = f"{REPO}/example_project/README.md#the-config-file"
EVAL_DOCS = f"{REPO}/example_project/README.md#writing-evals"
HOSTING_DOCS = f"{REPO}/docs/hosting.md"

# key: (menu label, default target name, URL already known, a hint for the URL prompt)
SERVERS = {
    "local": ("a local command", "local", None, None),
    "snowflake": (
        "Snowflake managed MCP",
        "snowflake",
        None,
        "https://<account>.snowflakecomputing.com/api/v2/databases/<db>/schemas/<schema>/mcp-servers/<server>",
    ),
    "motherduck": ("MotherDuck", "motherduck", "https://api.motherduck.com/mcp", None),
    "url": ("another URL", "agent", None, "https://..."),
}
PROVIDERS = {"anthropic": ("Anthropic (Claude)", "ANTHROPIC_API_KEY"), "openai": ("OpenAI", "OPENAI_API_KEY")}
RESULTS = {"local": "here, a local file", "motherduck": "MotherDuck", "s3": "a file in S3"}
RESULTS_TOKEN_ENV = "HONEST_AGENT_RESULTS_TOKEN"


@dataclass
class Answers:
    server: str  # a key of SERVERS
    target: str
    provider: str  # a key of PROVIDERS
    results: str  # a key of RESULTS
    mcp_command: str | None = None
    mcp_url: str | None = None
    results_db: str = "honest_agent_results"


@dataclass
class Written:
    created: list[str]
    skipped: list[str]
    env_to_fill: list[str]  # .env variables left for the user to fill in


def env_prefix(target: str) -> str:
    """`snowflake_dev` -> `SNOWFLAKE_DEV`: the prefix of a target's variables in .env."""
    return re.sub(r"[^A-Z0-9]+", "_", target.upper()).strip("_") or "AGENT"


def config_text(answers: Answers) -> str:
    prefix = env_prefix(answers.target)
    lines = [
        "# honest-agent settings: one target per agent you evaluate, like the targets in a dbt profile.",
        "# Secrets stay in .env, and so do account URLs: {{ env_var('NAME') }} reads them from there.",
        f"# Every setting: {CONFIG_DOCS}",
        "",
        f"default_target: {answers.target}",
    ]
    if answers.results == "motherduck":
        lines.append(f"results_path: md:{answers.results_db}   # opened with {RESULTS_TOKEN_ENV} from .env")
    lines += [
        "# model: claude-haiku-4-5   # optional; without it, the model follows the API key in .env",
        "",
        "targets:",
        f"  {answers.target}:",
    ]
    if answers.server == "local":
        lines += [
            f"    mcp_command: {json.dumps(answers.mcp_command)}",
            "    # mcp_env: [SOME_TOKEN]   # variables from .env the server needs; it gets only these",
        ]
    else:
        lines += [
            f"    mcp_url: \"{{{{ env_var('{prefix}_MCP_URL') }}}}\"",
            f"    bearer_token_env: {prefix}_MCP_TOKEN   # names the variable in .env, never the token",
        ]
    if answers.server == "motherduck":
        lines.append("    max_tool_steps: 10   # it explores databases and tables before it queries")
    lines.append("    evals_dir: evals")
    return "\n".join(lines) + "\n"


def env_entries(answers: Answers) -> list[tuple[str, str, str]]:
    """(comment, variable, value) for each variable the setup needs."""
    label, key_var = PROVIDERS[answers.provider]
    entries = [(f"The model's API key ({label})", key_var, "")]
    if answers.server != "local":
        prefix = env_prefix(answers.target)
        entries.append((f"The {answers.target} target's MCP server", f"{prefix}_MCP_URL", answers.mcp_url or ""))
        entries.append(("", f"{prefix}_MCP_TOKEN", ""))
    if answers.results == "motherduck":
        entries.append(
            (
                "MotherDuck only: a read/write token of a service account that holds only the results",
                RESULTS_TOKEN_ENV,
                "",
            )
        )
    return entries


def env_text(answers: Answers) -> str:
    lines = ["# Secrets and account URLs honest-agent reads. Keep this file out of git."]
    for comment, name, value in env_entries(answers):
        if comment:
            lines += ["", f"# {comment}"]
        lines.append(f"{name}={value}")
    return "\n".join(lines) + "\n"


EVAL_TEXT = f"""version: 1

# Your first eval. Replace each TODO: a question your agent should answer from
# your data, the answer you know is right, and the tables it should read to get it.
# More: {EVAL_DOCS}

evals:
  - category: first
    grading:
      method: extract_match   # compares the value in the answer with expected_answer
      min_score: 0.8
    provenance:
      min_score: 0.7          # did the agent's SQL read expected_sources?
    tests:
      - title: TODO a short name for this question
        prompt: >
          TODO a question your agent should answer from your data, e.g.
          How many orders were placed last year? Give me just the number.
        expected_answer: "TODO the answer you know is right"
        provenance:
          expected_sources: [TODO_table_name]
"""


def write_project(folder: Path, answers: Answers) -> Written:
    """Writes the three files into `folder`, skipping any that already exist."""
    files = {
        "honest_agent_config.yml": config_text(answers),
        "evals/first_eval.yml": EVAL_TEXT,
        ".env": env_text(answers),
    }
    created, skipped = [], []
    for name, text in files.items():
        path = folder / name
        if path.exists():
            skipped.append(name)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        created.append(name)
    to_fill = [name for _, name, value in env_entries(answers) if not value] if ".env" in created else []
    return Written(created, skipped, to_fill)


def missing_ignores(folder: Path) -> list[str]:
    """In a git repository, the paths that should be git-ignored but aren't. Empty outside git."""

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True)

    try:
        if git("rev-parse", "--is-inside-work-tree").returncode != 0:
            return []
        return [path for path in (".env", "honest_agent_report/") if git("check-ignore", "-q", path).returncode != 0]
    except FileNotFoundError:  # no git installed
        return []


def s3_note(results_path: str = "honest_agent_results/results.duckdb") -> str:
    return (
        "Results in S3: honest-agent won't copy them to S3 for you. Run the first line before each run, "
        "the second after (the very first time, only the second):\n"
        f"  aws s3 cp s3://<bucket>/results/results.duckdb.gz {results_path}.gz"
        f" && gunzip -t {results_path}.gz && gunzip -f {results_path}.gz\n"
        f"  gzip -c {results_path} | aws s3 cp - s3://<bucket>/results/results.duckdb.gz\n"
        f"The bucket, its permissions and CI: {HOSTING_DOCS}"
    )


EXAMPLE_FOLDER = "honest-agent-example"
EXAMPLE_FILES = Path(__file__).parent / "example"


def seed_tpch(path: Path) -> None:
    """DuckDB's TPC-H sample data at scale 0.01 (15,000 orders), written to `path`. The
    `tpch` extension downloads once, so the first time needs the network."""
    import duckdb

    con = duckdb.connect(str(path))
    try:
        con.execute("install tpch")
        con.execute("load tpch")
        con.execute("call dbgen(sf = 0.01)")
    finally:
        con.close()


def example_config_text(provider: str) -> str:
    import shlex
    import sys

    from .llm import DEFAULT_MODELS

    model = DEFAULT_MODELS[provider]
    command = f"{shlex.quote(sys.executable)} -m honest_agent.demo_server warehouse.duckdb"
    return (
        "\n".join(
            [
                "# The honest-agent example: a demo agent over DuckDB's TPC-H sample data. See README.md.",
                "",
                "default_target: demo",
                f"model: {model}   # a cheap model keeps a run at a few cents",
                "max_tool_steps: 8   # the agent explores the tables before it queries",
                "",
                "targets:",
                "  demo:",
                "    # honest-agent's demo MCP server, started with honest-agent's own Python. Demo only:",
                "    # not for real data. After reinstalling honest-agent, run `init --example` again.",
                f"    mcp_command: {json.dumps(command)}",
                "    # Where a bare table name like `orders` runs: DuckDB names the database after",
                "    # the file and starts in schema main. Lets provenance check where tables live.",
                "    default_database: warehouse",
                "    default_schema: main",
                "    evals_dir: evals",
            ]
        )
        + "\n"
    )


def write_example(folder: Path, provider: str) -> None:
    """Creates `folder` with the example: config, evals, README, .env and a seeded warehouse.
    Refuses an existing folder, so a demo target never lands in a real project."""
    import shutil

    if folder.exists():
        raise FileExistsError(f"{folder} already exists. Remove it or run `init --example` elsewhere.")
    folder.mkdir(parents=True)
    try:
        seed_tpch(folder / "warehouse.duckdb")
    except Exception:
        shutil.rmtree(folder)
        raise
    (folder / "evals").mkdir()
    shutil.copy(EXAMPLE_FILES / "evals.yml", folder / "evals" / "example_evals.yml")
    shutil.copy(EXAMPLE_FILES / "README.md", folder / "README.md")
    (folder / "honest_agent_config.yml").write_text(example_config_text(provider))
    label, key_var = PROVIDERS[provider]
    (folder / ".env").write_text(f"# The model's API key ({label}). Keep this file out of git.\n{key_var}=\n")


# The questions and messages of `honest-agent init` (the CLI command only passes its flags).


# The setup skill for coding agents (Agent Skills format, agentskills.io), copied into a
# project only when the user asks: `.agents/skills/` is read by most coding agents
# (Codex, Cursor, Copilot, Gemini CLI, ...), `.claude/skills/` by Claude Code.
SKILL_NAME = "honest-agent-setup"
SKILL_SOURCE = Path(__file__).parent / "skill" / SKILL_NAME
SKILL_FOLDERS = (".agents/skills", ".claude/skills")
ASK_FOR_SKILL = "Continue the setup with a coding agent? (It helps connect your MCP server and write your first evals.)"


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("honest-agent")
    except PackageNotFoundError:
        return "unknown"


def _with_header(skill_md: str) -> str:
    """SKILL.md with a line under its frontmatter saying who wrote it and not to edit it."""
    _start, frontmatter, body = skill_md.split("---\n", 2)
    note = (
        f"> Written by honest-agent {_version()}. Don't edit: `honest-agent init --with-skill` replaces this folder.\n"
    )
    return f"---\n{frontmatter}---\n\n{note}{body}"


def write_skill(folder: Path) -> tuple[list[str], bool]:
    """Copies the setup skill into `folder`'s skill folders, replacing any copy there (the
    files are honest-agent's, not the user's). Returns the folders written and whether a
    copy was replaced."""
    written, replaced = [], False
    for base in SKILL_FOLDERS:
        target = folder / base / SKILL_NAME
        if target.exists():
            replaced = True
            shutil.rmtree(target)
        shutil.copytree(SKILL_SOURCE, target)
        skill_md = target / "SKILL.md"
        skill_md.write_text(_with_header(skill_md.read_text()))
        written.append(f"{base}/{SKILL_NAME}/")
    return written, replaced


def skill_note(written: list[str], replaced: bool) -> str:
    """What `init` prints after writing the skill: where it is and how to use it."""
    verb = "Replaced the setup skill with this version's" if replaced else "Added the setup skill"
    return (
        f"{verb} in {' and '.join(written)}.\n"
        "  To use it, open your coding agent in this folder and ask it to set up honest-agent;\n"
        f"  or point it at {SKILL_FOLDERS[0]}/{SKILL_NAME}/SKILL.md. For a tool that reads AGENTS.md,\n"
        f'  you can add: "To set up honest-agent, follow {SKILL_FOLDERS[0]}/{SKILL_NAME}/SKILL.md."'
    )


def _choose(question: str, options: dict[str, str], given: str | None, default: str, no_input: bool) -> str:
    """A numbered menu, e.g. `1) Claude  2) OpenAI  [1]:`; a flag's value or --no-input skips it."""
    if given is not None:
        return given
    if no_input:
        return default
    keys = list(options)
    menu = "  ".join(f"{i}) {options[key]}" for i, key in enumerate(keys, 1))
    pick = click.prompt(f"{question}\n  {menu}", type=click.IntRange(1, len(keys)), default=keys.index(default) + 1)
    return keys[pick - 1]


def _ask(question: str, given: str | None, default: str | None, no_input: bool, flag: str) -> str:
    """Free text the user knows best (a URL, a command); required unless it has a default."""
    if given:
        return given
    if no_input:
        if default:
            return default
        raise click.ClickException(f"{flag} is required with --no-input.")
    return click.prompt(question, default=default)


def prompt_example(model_provider: str | None, no_input: bool, with_skill: bool = False) -> None:
    providers = {key: label for key, (label, _var) in PROVIDERS.items()}
    provider = _choose("Which model runs the agent?", providers, model_provider, "anthropic", no_input)
    folder = Path.cwd() / EXAMPLE_FOLDER
    click.echo(f"Creating {EXAMPLE_FOLDER}/ and seeding DuckDB's TPC-H sample data...")
    try:
        write_example(folder, provider)
    except FileExistsError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        raise click.ClickException(
            f"Couldn't seed the sample data ({exc}). DuckDB downloads its tpch extension the first "
            "time, so this needs the network."
        ) from exc
    key_var = PROVIDERS[provider][1]
    if with_skill:  # never asked here: the example is already set up
        click.echo(skill_note(*write_skill(folder)))
    click.echo(
        f"\nCreated {EXAMPLE_FOLDER}/: a demo agent over sample data, and six evals.\n"
        "The demo MCP server is for trying honest-agent only, not for real data.\n"
        f"\nNext:\n  1. cd {EXAMPLE_FOLDER}\n"
        f"  2. Add your API key to .env: {key_var}\n"
        "  3. honest-agent run      (a few cents)\n"
        "  4. honest-agent report, then honest-agent serve\n"
        "README.md there says what each eval shows, and which ones are meant to fail."
    )


def prompt_project(
    *,
    server: str | None,
    mcp_command: str | None,
    mcp_url: str | None,
    target_name: str | None,
    model_provider: str | None,
    results: str | None,
    results_db: str | None,
    no_input: bool,
    with_skill: bool = False,
) -> None:
    """`honest-agent init`: asks what isn't given by a flag, writes the files, says what's next.
    Adds the setup skill with --with-skill, or when asked and the user doesn't say no."""
    servers = {key: label for key, (label, *_rest) in SERVERS.items()}
    server = _choose("Which MCP server does your agent use?", servers, server, "local", no_input)
    _label, default_target, known_url, url_hint = SERVERS[server]
    if server == "local":
        mcp_command = _ask("Command that starts the MCP server", mcp_command, None, no_input, "--mcp-command")
    else:
        prompt = "MCP server URL" + (f" ({url_hint})" if url_hint and not known_url else "")
        mcp_url = _ask(prompt, mcp_url, known_url, no_input, "--mcp-url")
    target = target_name or (default_target if no_input else click.prompt("Target name", default=default_target))
    providers = {key: label for key, (label, _var) in PROVIDERS.items()}
    provider = _choose("Which model runs the agent?", providers, model_provider, "anthropic", no_input)
    results = _choose("Where should results live?", RESULTS, results, "local", no_input)
    if results == "motherduck":
        results_db = _ask("MotherDuck database for results", results_db, "honest_agent_results", no_input, "")

    answers = Answers(
        server=server,
        target=target,
        provider=provider,
        results=results,
        mcp_command=mcp_command,
        mcp_url=mcp_url,
        results_db=results_db or "honest_agent_results",
    )
    folder = Path.cwd()
    written = write_project(folder, answers)
    click.echo("")
    if written.created:
        click.echo(f"Created {', '.join(written.created)}")
    for name in written.skipped:
        click.echo(f"Skipped {name}: it already exists, so it was left as it is.")
    if ".env" in written.skipped:
        names = ", ".join(name for _, name, _value in env_entries(answers))
        click.echo(f"  Make sure .env has: {names}")
    missing = missing_ignores(folder)
    if missing:
        click.echo("Add to .gitignore:\n" + "\n".join(f"  {path}" for path in missing))
    if results == "s3":
        click.echo("\n" + s3_note())
    if not with_skill and not no_input:
        with_skill = click.confirm(f"\n{ASK_FOR_SKILL}", default=True)
    if with_skill:
        click.echo("\n" + skill_note(*write_skill(folder)))
    steps = []
    if written.env_to_fill:
        steps.append(f"Fill in .env: {', '.join(written.env_to_fill)}")
    steps.append("Edit evals/first_eval.yml: your question, its answer, the tables it reads")
    steps.append("honest-agent run")
    click.echo("\nNext:\n" + "\n".join(f"  {i}. {step}" for i, step in enumerate(steps, 1)))
