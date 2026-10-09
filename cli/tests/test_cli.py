"""Covers the CLI commands that need no model or MCP server: `logs` and `rebuild` read
and re-derive raw records built through the real recorder (tests/recorded.py), and
the run loop is driven by a scripted agent and judge."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from click.testing import CliRunner
from recorded import claude_reply, definition, model_call, record, text, tool_call, tool_use

from honest_agent.cli import main
from honest_agent.grading import UNREADABLE_REPLY
from honest_agent.raw import RunRecorder, read_records
from honest_agent.runner import eval_loop, resolve_agent_name
from honest_agent.storage import connect, read_all_results, read_traces, write_run_results

SQL = "select count(*) from agent_quiz_demo.public.orders"


def test_logs_prints_each_recorded_call_as_stored(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(
        path,
        [
            model_call(claude_reply(tool_use("t1", "query_warehouse", {"sql": SQL}))),
            tool_call("t1", "query_warehouse", {"sql": SQL}, {"content": [text("2297")], "isError": False}),
            model_call(claude_reply(text("2297"))),
        ],
    )

    result = CliRunner().invoke(main, ["logs", "--results-path", path])

    assert result.exit_code == 0, result.output
    assert "=== eval q1 (run run_1, result r1) ===" in result.output
    assert "--- #0 model_call (anthropic)" in result.output
    assert "--- #1 tool_call (mcp)" in result.output
    assert '"stop_reason": "tool_use"' in result.output
    assert "Accuracy" not in result.output  # scores live in the report


def test_logs_never_prints_raw_control_characters(tmp_path: Path):
    """Text from models and tools can carry terminal escape codes (a clipboard write, a
    screen rewrite); logs shows them escaped (as JSON does), so the terminal doesn't act on them."""
    path = str(tmp_path / "results.duckdb")
    planted = "2297\x1b]52;c;ZWNobyBoaQ==\x07\r\x9b2J"
    record(path, [model_call(claude_reply(text(planted)))])

    output = CliRunner().invoke(main, ["logs", "--results-path", path]).output

    assert "\\u001b]52" in output
    assert not any(char in output for char in "\x1b\x07\r\x9b")


def test_logs_json_prints_the_records_as_stored(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(path, [model_call(claude_reply(text("4")))])

    result = CliRunner().invoke(main, ["logs", "--results-path", path, "--json"])

    (rec,) = json.loads(result.output)
    assert json.loads(rec["events"][0]["response"])["content"] == [text("4")]


def test_logs_for_results_recorded_before_the_raw_layer_points_to_the_report(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    write_run_results(path, "run_1", [{"result_id": "r1", "run_id": "run_1", "eval_id": "q1", "sql_calls": []}])

    result = CliRunner().invoke(main, ["logs", "--results-path", path])

    assert "before honest-agent kept raw records" in result.output


def test_logs_reports_no_matching_logs(in_tmp_dir):
    result = CliRunner().invoke(main, ["logs", "--results-path", "results.duckdb"])

    assert result.exit_code == 0, result.output
    assert "No matching logs found." in result.output


def test_rebuild_re_derives_past_results_from_their_raw_record(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(path, [model_call(claude_reply(text("4")))])
    # A stale derived row, as if scored by older rules.
    write_run_results(path, "run_1", [{"result_id": "r1", "run_id": "run_1", "eval_id": "q1", "accuracy_score": 0.0}])

    result = CliRunner().invoke(main, ["rebuild", "--results-path", path])

    assert result.exit_code == 0, result.output
    assert "Rebuilt 1 result(s) from 1 run(s)" in result.output
    (row,) = read_all_results(path)
    assert (row["accuracy_score"], row["agent_answer"]) == (1.0, "4")
    assert json.loads(read_traces(path)[0]["agent_trace"])[-1] == {"role": "assistant", "content": [text("4")]}


def test_rebuild_leaves_results_without_a_raw_record_alone(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    record(path, [model_call(claude_reply(text("4")))])
    write_run_results(
        path, "old_run", [{"result_id": "old", "run_id": "old_run", "eval_id": "q1", "accuracy_score": 0.5}]
    )

    CliRunner().invoke(main, ["rebuild", "--results-path", path])

    by_id = {r["result_id"]: r for r in read_all_results(path)}
    assert by_id["old"]["accuracy_score"] == 0.5


def test_agent_name_defaults_to_the_mcp_server_name():
    from types import SimpleNamespace

    connected = SimpleNamespace(server_info=SimpleNamespace(name="mcp-server-motherduck"))
    assert resolve_agent_name(None, connected) == "mcp-server-motherduck"
    assert resolve_agent_name("motherduck", connected) == "motherduck"


def _run_capturing_mcp_target(fake_run, args: list[str], env: dict[str, str]):
    Path("evals").mkdir()
    result = CliRunner().invoke(main, ["run", "--evals-dir", "evals", *args], env={"ANTHROPIC_API_KEY": "test", **env})
    return result, {"mcp_command": fake_run.get("mcp_command"), "mcp_url": fake_run.get("mcp_url")}


def test_explicit_mcp_command_overrides_mcp_url_from_env(fake_run, in_tmp_dir):
    result, target = _run_capturing_mcp_target(
        fake_run, ["--mcp-command", "uvx mcp-server-motherduck"], {"MCP_URL": "https://remote/mcp"}
    )

    assert result.exit_code == 0, result.output
    assert target == {"mcp_command": "uvx mcp-server-motherduck", "mcp_url": None}


def test_explicit_mcp_url_overrides_mcp_command_from_env(fake_run, in_tmp_dir):
    result, target = _run_capturing_mcp_target(
        fake_run, ["--mcp-url", "https://remote/mcp"], {"MCP_COMMAND": "python server.py"}
    )

    assert result.exit_code == 0, result.output
    assert target == {"mcp_command": None, "mcp_url": "https://remote/mcp"}


def test_both_mcp_flags_given_explicitly_is_an_error(fake_run, in_tmp_dir):
    result, _ = _run_capturing_mcp_target(
        fake_run, ["--mcp-command", "python server.py", "--mcp-url", "https://remote/mcp"], {}
    )

    assert result.exit_code != 0
    assert "not both" in result.output


def test_both_mcp_targets_only_in_env_is_an_error(fake_run, in_tmp_dir):
    result, _ = _run_capturing_mcp_target(
        fake_run, [], {"MCP_COMMAND": "python server.py", "MCP_URL": "https://remote/mcp"}
    )

    assert result.exit_code != 0
    assert "Pass --mcp-command or --mcp-url to choose one" in result.output


def test_duplicate_eval_id_is_a_clean_cli_error(in_tmp_dir):
    Path("evals").mkdir()
    Path("evals/a.yml").write_text(
        "evals:\n  - id: q_dup\n    prompt: one\n    expected_answer: '1'\n"
        "  - id: q_dup\n    prompt: two\n    expected_answer: '2'\n"
    )
    result = CliRunner().invoke(
        main,
        ["run", "--evals-dir", "evals", "--mcp-command", "python server.py"],
        env={"ANTHROPIC_API_KEY": "test"},
    )

    assert result.exit_code == 1
    assert "Error: Duplicate eval id 'q_dup' in a.yml (lines 2 and 5)" in result.output
    assert "Traceback" not in result.output


def _run_capturing_models(fake_run, args: list[str]):
    Path("evals").mkdir()
    result = CliRunner().invoke(
        main,
        ["run", "--evals-dir", "evals", "--mcp-command", "python server.py", *args],
        env={"ANTHROPIC_API_KEY": "test", "HONEST_AGENT_JUDGE_MODEL": ""},
    )
    assert result.exit_code == 0, result.output
    return {"model": fake_run["model"], "judge_model": fake_run["judge_model"]}


def test_judge_model_defaults_to_the_agent_model(fake_run, in_tmp_dir):
    assert _run_capturing_models(fake_run, ["--model", "claude-sonnet-5"]) == {
        "model": "claude-sonnet-5",
        "judge_model": "claude-sonnet-5",
    }


def test_judge_model_can_differ_from_the_agent_model(fake_run, in_tmp_dir):
    models = _run_capturing_models(fake_run, ["--model", "claude-sonnet-5", "--judge-model", "claude-haiku-4-5"])

    assert models == {"model": "claude-sonnet-5", "judge_model": "claude-haiku-4-5"}


class _ScriptedAgent:
    """An agent that makes exactly these calls through the recorder, as a real runner does."""

    def __init__(self, calls: list[tuple]):
        self._calls = calls

    async def run(self, prompt, record):
        for kind, provider, request, response in self._calls:
            await record.call(kind, provider, request, _returns(response))


class _ScriptedJudge:
    def __init__(self, reply: str):
        self._reply = reply

    async def complete(self, prompt, model, max_tokens, schema):
        return claude_reply(text(self._reply))


async def _returns(value):
    return value


def _run_loop(path: str, agent, judge, definitions) -> list[dict]:
    con = connect(path)
    try:
        recorder = RunRecorder(con)
        recorder.start_run(
            "run_1",
            agent_name="demo",
            target="demo",
            model="claude-test",
            judge_model="claude-judge",
            settings={"max_tool_steps": 5, "max_tokens": 1024, "mcp": {}, "ignore_tools": []},
            tools_offered=[],
        )
        return asyncio.run(eval_loop(agent, definitions, judge, "claude-judge", "run_1", recorder, con))
    finally:
        con.close()


def test_a_run_records_every_call_and_derives_its_results(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    agent = _ScriptedAgent(
        [
            model_call(claude_reply(tool_use("t1", "query_warehouse", {"sql": SQL}))),
            tool_call("t1", "query_warehouse", {"sql": SQL}, {"content": [text("2297")], "isError": False}),
            model_call(claude_reply(text("There were 2,297 orders."))),
        ]
    )
    evals = [definition(grading_method="extract_match", expected_answer="2297", expected_sources=["orders"])]

    (row,) = _run_loop(path, agent, _ScriptedJudge('{"extracted_answer": "2297"}'), evals)

    assert (row["accuracy_score"], row["provenance_score"], row["extracted_answer"]) == (1.0, 1.0, "2297")
    assert [r["accuracy_score"] for r in read_all_results(path)] == [1.0]  # written as the eval ended
    (rec,) = read_records(path)
    assert [e["kind"] for e in rec["events"]] == ["model_call", "tool_call", "model_call", "grading_call"]
    grading_request = json.loads(rec["events"][3]["request"])
    assert "There were 2,297 orders." in grading_request["prompt"]
    assert grading_request["schema"]["required"] == ["extracted_answer"]


def test_an_unreadable_grading_reply_fails_only_that_eval(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    agent = _ScriptedAgent([model_call(claude_reply(text("2297")))])
    evals = [definition(grading_method="llm_judge", expected_answer="2297")]

    rows = _run_loop(path, agent, _ScriptedJudge("not json"), evals)

    assert [r["accuracy_score"] for r in rows] == [0.0]
    assert rows[0]["accuracy_rationale"].startswith(UNREADABLE_REPLY)
    (rec,) = read_records(path)
    assert [e["kind"] for e in rec["events"]] == ["model_call", "grading_call"]


class _FailingJudge:
    async def complete(self, prompt, model, max_tokens, schema):
        raise RuntimeError("the grading API is down")


def test_an_eval_that_fails_is_recorded_before_the_run_stops(tmp_path: Path):
    path = str(tmp_path / "results.duckdb")
    agent = _ScriptedAgent([model_call(claude_reply(text("2297")))])
    evals = [definition(grading_method="llm_judge", expected_answer="2297")]

    try:
        _run_loop(path, agent, _FailingJudge(), evals)
        raise AssertionError("expected the failing grading call to stop the run")
    except RuntimeError:
        pass

    (rec,) = read_records(path)
    assert [e["kind"] for e in rec["events"]] == ["model_call", "grading_call", "eval_error"]
    assert read_all_results(path) == []


_LS_EVALS = """
evals:
  - category: sales
    tags: [smoke]
    tests:
      - {id: revenue_1997, prompt: p, expected_answer: "1"}
      - {title: Average order total, prompt: p, expected_answer: "2", tags: [smoke, slow]}
  - category: customers
    tests:
      - {id: top_segment, prompt: p, expected_answer: BUILDING}
"""


def test_ls_lists_ids_categories_and_tags(tmp_path: Path):
    (tmp_path / "evals.yml").write_text(_LS_EVALS)

    result = CliRunner().invoke(main, ["ls", "--evals-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "revenue_1997         sales      smoke",
        "average_order_total  sales      smoke, slow",  # the id made from the title
        "top_segment          customers",
    ]


def test_ls_takes_the_same_selectors_as_run(tmp_path: Path):
    (tmp_path / "evals.yml").write_text(_LS_EVALS)

    result = CliRunner().invoke(
        main, ["ls", "--evals-dir", str(tmp_path), "--select", "tag:smoke top_segment", "--exclude", "tag:slow"]
    )

    assert [line.split()[0] for line in result.output.splitlines()] == ["revenue_1997", "top_segment"]


def test_ls_names_a_selector_that_matches_nothing(tmp_path: Path):
    (tmp_path / "evals.yml").write_text(_LS_EVALS)

    result = CliRunner().invoke(main, ["ls", "--evals-dir", str(tmp_path), "--select", "revenue_1996"])

    assert result.exit_code != 0
    assert "No eval has id 'revenue_1996'" in result.output
