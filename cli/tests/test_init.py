import subprocess
from pathlib import Path

from click.testing import CliRunner

from honest_agent.cli import main
from honest_agent.config_file import load_config
from honest_agent.eval_loader import load_evals

SNOWFLAKE_URL = "https://acme.snowflakecomputing.com/api/v2/databases/sales/schemas/public/mcp-servers/agent"


def _init(*args: str, input: str | None = None):
    return CliRunner().invoke(main, ["init", *args], input=input)


def test_no_input_writes_a_local_project_that_loads(in_tmp_dir: Path):
    result = _init("--no-input", "--mcp-command", "uv run python server.py")

    assert result.exit_code == 0, result.output
    assert "Created honest_agent_config.yml, evals/first_eval.yml, .env" in result.output
    target = load_config(in_tmp_dir / "honest_agent_config.yml").target(None)
    assert target.name == "local"
    assert target.settings["mcp_command"] == "uv run python server.py"
    assert target.settings["evals_dir"] == str(in_tmp_dir / "evals")
    assert [e.title for e in load_evals(in_tmp_dir / "evals")] == ["TODO a short name for this question"]
    assert (in_tmp_dir / ".env").read_text().count("=") == 1  # only ANTHROPIC_API_KEY=
    assert "Fill in .env: ANTHROPIC_API_KEY" in result.output


def test_prompts_put_a_snowflake_url_in_env_and_read_it_with_env_var(in_tmp_dir: Path, monkeypatch):
    # server 2 (Snowflake), the URL, default target name, model 2 (OpenAI), results 2 (MotherDuck), default db,
    # no setup skill
    result = _init(input=f"2\n{SNOWFLAKE_URL}\n\n2\n2\n\nn\n")

    assert result.exit_code == 0, result.output
    env = (in_tmp_dir / ".env").read_text()
    assert f"SNOWFLAKE_MCP_URL={SNOWFLAKE_URL}" in env
    assert "OPENAI_API_KEY=" in env and "ANTHROPIC_API_KEY" not in env
    assert "# MotherDuck only" in env and "HONEST_AGENT_RESULTS_TOKEN=" in env
    config_text = (in_tmp_dir / "honest_agent_config.yml").read_text()
    assert "acme" not in config_text  # the account stays out of the committed file
    monkeypatch.setenv("SNOWFLAKE_MCP_URL", SNOWFLAKE_URL)
    config = load_config(in_tmp_dir / "honest_agent_config.yml")
    assert config.results_path == "md:honest_agent_results"
    assert config.target(None).settings["mcp_url"] == SNOWFLAKE_URL
    assert config.target(None).settings["bearer_token_env"] == "SNOWFLAKE_MCP_TOKEN"
    assert "OPENAI_API_KEY, SNOWFLAKE_MCP_TOKEN, HONEST_AGENT_RESULTS_TOKEN" in result.output


def test_a_target_name_sets_its_variables_prefix(in_tmp_dir: Path):
    result = _init("--no-input", "--server", "snowflake", "--mcp-url", SNOWFLAKE_URL, "--target-name", "snowflake-dev")

    assert result.exit_code == 0, result.output
    assert "SNOWFLAKE_DEV_MCP_URL=" in (in_tmp_dir / ".env").read_text()
    assert "default_target: snowflake-dev" in (in_tmp_dir / "honest_agent_config.yml").read_text()


def test_motherduck_prefills_its_url(in_tmp_dir: Path):
    result = _init("--no-input", "--server", "motherduck")

    assert result.exit_code == 0, result.output
    assert "MOTHERDUCK_MCP_URL=https://api.motherduck.com/mcp" in (in_tmp_dir / ".env").read_text()


def test_existing_files_are_never_overwritten(in_tmp_dir: Path):
    (in_tmp_dir / ".env").write_text("ANTHROPIC_API_KEY=real-key\n")

    result = _init("--no-input", "--mcp-command", "x")

    assert result.exit_code == 0, result.output
    assert (in_tmp_dir / ".env").read_text() == "ANTHROPIC_API_KEY=real-key\n"
    assert "Skipped .env: it already exists" in result.output
    assert "Make sure .env has: ANTHROPIC_API_KEY" in result.output


def test_s3_results_print_the_copy_commands(in_tmp_dir: Path):
    result = _init("--no-input", "--mcp-command", "x", "--results", "s3")

    assert result.exit_code == 0, result.output
    assert "honest-agent won't copy them to S3 for you" in result.output
    assert "aws s3 cp" in result.output and "docs/hosting.md" in result.output
    assert "results_path" not in (in_tmp_dir / "honest_agent_config.yml").read_text()


def test_no_input_needs_the_servers_command_or_url(in_tmp_dir: Path):
    result = _init("--no-input", "--server", "snowflake")

    assert result.exit_code != 0
    assert "--mcp-url is required with --no-input" in result.output


def test_in_git_it_lists_what_to_ignore_without_editing_gitignore(in_tmp_dir: Path):
    subprocess.run(["git", "init", "-q"], check=True)
    (in_tmp_dir / ".gitignore").write_text(".env\n")

    result = _init("--no-input", "--mcp-command", "x")

    assert "Add to .gitignore:\n  honest_agent_report/\n" in result.output
    assert (in_tmp_dir / ".gitignore").read_text() == ".env\n"


def test_example_creates_its_own_folder_with_evals_that_load(in_tmp_dir: Path, monkeypatch):
    import honest_agent.init as init_mod

    seeded = []
    monkeypatch.setattr(init_mod, "seed_tpch", lambda path: seeded.append(path) or path.write_text(""))

    result = _init("--example", "--no-input")

    assert result.exit_code == 0, result.output
    folder = in_tmp_dir / "honest-agent-example"
    assert seeded == [folder / "warehouse.duckdb"]
    target = load_config(folder / "honest_agent_config.yml").target(None)
    assert target.name == "demo"
    assert "-m honest_agent.demo_server warehouse.duckdb" in target.settings["mcp_command"]
    assert target.settings["model"] == "claude-haiku-4-5"
    assert target.settings["max_tool_steps"] == 8
    assert (target.settings["default_database"], target.settings["default_schema"]) == ("warehouse", "main")
    evals = load_evals(folder / "evals")
    assert len(evals) == 6 and {e.grading_method for e in evals} == {"contains", "extract_match", "llm_judge"}
    assert (folder / ".env").read_text().endswith("ANTHROPIC_API_KEY=\n")
    assert "fails provenance" in (folder / "README.md").read_text()
    assert "not for real data" in result.output


def test_example_never_writes_into_an_existing_folder(in_tmp_dir: Path):
    (in_tmp_dir / "honest-agent-example").mkdir()

    result = _init("--example", "--no-input")

    assert result.exit_code != 0
    assert "already exists" in result.output


def test_example_with_openai_uses_its_cheap_model(in_tmp_dir: Path, monkeypatch):
    import honest_agent.init as init_mod

    monkeypatch.setattr(init_mod, "seed_tpch", lambda path: path.write_text(""))

    result = _init("--example", "--no-input", "--model-provider", "openai")

    assert result.exit_code == 0, result.output
    folder = in_tmp_dir / "honest-agent-example"
    assert load_config(folder / "honest_agent_config.yml").shared["model"] == "gpt-5.4-mini"
    assert "OPENAI_API_KEY=" in (folder / ".env").read_text()


def test_model_provider_takes_the_company_name(in_tmp_dir: Path, monkeypatch):
    """`anthropic`, like ANTHROPIC_API_KEY and the provider names honest-agent records."""
    import honest_agent.init as init_mod

    monkeypatch.setattr(init_mod, "seed_tpch", lambda path: path.write_text(""))

    result = _init("--example", "--no-input", "--model-provider", "anthropic")

    assert result.exit_code == 0, result.output
    folder = in_tmp_dir / "honest-agent-example"
    assert load_config(folder / "honest_agent_config.yml").shared["model"] == "claude-haiku-4-5"


def test_the_model_name_is_not_a_provider(in_tmp_dir: Path):
    result = _init("--no-input", "--mcp-command", "x", "--model-provider", "claude")

    assert result.exit_code != 0
    assert "'claude' is not one of 'anthropic', 'openai'" in result.output


def _skill_folders(folder: Path) -> list[Path]:
    return [folder / base / "honest-agent-setup" / "SKILL.md" for base in (".agents/skills", ".claude/skills")]


def test_init_asks_for_the_setup_skill_and_yes_is_the_default(in_tmp_dir: Path):
    # server 1 (local), its command, default target, default model, default results, Enter at the skill question
    result = _init(input="1\nuv run python server.py\n\n\n\n\n")

    assert result.exit_code == 0, result.output
    assert "Continue the setup with a coding agent?" in result.output
    assert "Added the setup skill in .agents/skills/honest-agent-setup/ and .claude/skills/honest-agent-setup/" in (
        result.output
    )
    for skill_md in _skill_folders(in_tmp_dir):
        text = skill_md.read_text()
        assert text.startswith("---\nname: honest-agent-setup\n")
        assert "> Written by honest-agent " in text and "Don't edit" in text


def test_saying_no_adds_nothing_for_coding_agents(in_tmp_dir: Path):
    result = _init(input="1\nuv run python server.py\n\n\n\nn\n")

    assert result.exit_code == 0, result.output
    assert not (in_tmp_dir / ".agents").exists() and not (in_tmp_dir / ".claude").exists()


def test_no_input_adds_the_skill_only_with_the_flag(in_tmp_dir: Path):
    _init("--no-input", "--mcp-command", "x")
    assert not (in_tmp_dir / ".agents").exists()

    (in_tmp_dir / "honest_agent_config.yml").unlink()
    result = _init("--no-input", "--mcp-command", "x", "--with-skill")

    assert result.exit_code == 0, result.output
    assert all(path.exists() for path in _skill_folders(in_tmp_dir))


def test_with_skill_on_an_existing_project_only_adds_or_replaces_the_skill(in_tmp_dir: Path):
    (in_tmp_dir / "honest_agent_config.yml").write_text("targets: {}\n")
    stale = in_tmp_dir / ".agents/skills/honest-agent-setup/old_notes.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("from an older version")

    result = _init("--with-skill")

    assert result.exit_code == 0, result.output
    assert "Replaced the setup skill with this version's" in result.output
    assert not stale.exists()  # the whole folder is replaced
    assert all(path.exists() for path in _skill_folders(in_tmp_dir))
    assert (in_tmp_dir / "honest_agent_config.yml").read_text() == "targets: {}\n"
    assert not (in_tmp_dir / ".env").exists()  # no project questions, no other files


def test_the_example_never_asks_but_takes_the_flag(in_tmp_dir: Path, monkeypatch):
    import honest_agent.init as init_mod

    monkeypatch.setattr(init_mod, "seed_tpch", lambda path: path.write_text(""))

    result = _init("--example", input="\n")  # interactive: only the model question is asked
    assert result.exit_code == 0, result.output
    assert "coding agent" not in result.output
    assert not (in_tmp_dir / "honest-agent-example" / ".agents").exists()

    import shutil

    shutil.rmtree(in_tmp_dir / "honest-agent-example")
    result = _init("--example", "--no-input", "--with-skill")
    assert result.exit_code == 0, result.output
    assert all(path.exists() for path in _skill_folders(in_tmp_dir / "honest-agent-example"))


def test_the_packaged_skill_follows_the_agent_skills_spec():
    """agentskills.io: `name` matches the folder (lowercase, digits, hyphens, at most 64),
    `description` at most 1024 characters, and every file SKILL.md points to exists."""
    import re

    import yaml

    from honest_agent.init import SKILL_NAME, SKILL_SOURCE

    _start, frontmatter, body = (SKILL_SOURCE / "SKILL.md").read_text().split("---\n", 2)
    meta = yaml.safe_load(frontmatter)
    assert meta["name"] == SKILL_NAME == SKILL_SOURCE.name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", meta["name"]) and len(meta["name"]) <= 64
    assert 0 < len(meta["description"]) <= 1024
    for reference in re.findall(r"`(references/[^`]+)`", body):
        assert (SKILL_SOURCE / reference).is_file(), reference


def test_the_skills_eval_example_loads(tmp_path: Path):
    """The YAML example the skill teaches from is a valid eval file."""
    import re

    from honest_agent.init import SKILL_SOURCE

    text = (SKILL_SOURCE / "references" / "writing-evals.md").read_text()
    (tmp_path / "evals.yml").write_text(re.search(r"```yaml\n(.*?)```", text, re.DOTALL).group(1))

    evals = {e.eval_id: e for e in load_evals(tmp_path)}
    assert set(evals) == {"revenue_last_month", "top_customers"}
    assert evals["top_customers"].grading_method == "llm_judge"
    assert evals["revenue_last_month"].tolerance_percent == 0.01
