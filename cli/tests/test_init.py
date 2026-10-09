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
    # server 2 (Snowflake), the URL, default target name, model 2 (OpenAI), results 2 (MotherDuck), default db
    result = _init(input=f"2\n{SNOWFLAKE_URL}\n\n2\n2\n\n")

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
