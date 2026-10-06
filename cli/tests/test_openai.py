"""OpenAI support with fake clients -- nothing here calls a real API."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace as NS

from click.testing import CliRunner

from honest_agent.cli import main
from honest_agent.llm import ANTHROPIC, OPENAI, OpenAIJudge, provider_for
from honest_agent.openai_agent_runner import OpenAIMCPAgentClient
from honest_agent.sql_capture import extract_sql_calls


def test_provider_is_inferred_from_the_model_name():
    for model in ["gpt-5.4-mini", "GPT-4o", "o4-mini", "o3", "chatgpt-4o-latest"]:
        assert provider_for(model) == OPENAI, model
    for model in ["claude-haiku-4-5-20251001", "claude-sonnet-5", "opus"]:
        assert provider_for(model) == ANTHROPIC, model


def _completion(content=None, tool_calls=None, prompt_tokens=10, completion_tokens=5):
    message = NS(content=content, tool_calls=tool_calls)
    return NS(choices=[NS(message=message)], usage=NS(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens))


class _FakeCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(json.loads(json.dumps(kwargs)))
        return self._responses.pop(0)


def _fake_openai(*responses):
    return NS(chat=NS(completions=_FakeCompletions(responses)))


def test_openai_judge_returns_text_and_token_usage():
    client = _fake_openai(_completion('{"score": 1.0}', prompt_tokens=30, completion_tokens=8))

    assert asyncio.run(OpenAIJudge(client).complete("grade this", model="gpt-5.4-mini", max_tokens=200)) == (
        '{"score": 1.0}',
        30,
        8,
    )


class _FakeMCP:
    def __init__(self):
        self.calls = []

    async def list_tools(self):
        tool = NS(name="execute_query", description="Run SQL", input_schema={"type": "object", "properties": {}})
        return NS(tools=[tool])

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return NS(content=[NS(type="text", text="order_count\n2297")], is_error=False)


def _tool_call(sql: str):
    return NS(id="call_1", function=NS(name="execute_query", arguments=json.dumps({"sql": sql})))


def test_openai_agent_runs_tools_and_records_the_shared_trace_format():
    sql = "select count(*) from orders where year(o_orderdate) = 1996"
    openai = _fake_openai(
        _completion(None, [_tool_call(sql)], prompt_tokens=100, completion_tokens=20),
        _completion("**2297**", prompt_tokens=150, completion_tokens=10),
    )
    mcp = _FakeMCP()

    result = asyncio.run(OpenAIMCPAgentClient(mcp, model="gpt-5.4-mini", client=openai).run("How many orders?"))

    assert result.answer == "**2297**"
    assert (result.input_tokens, result.output_tokens) == (250, 30)
    assert result.tools_used == ["execute_query"]
    assert mcp.calls == [("execute_query", {"sql": sql})]
    assert result.raw_trace == [
        {"role": "user", "content": "How many orders?"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "call_1", "name": "execute_query", "input": {"sql": sql}}],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": "order_count\n2297", "is_error": False}
            ],
        },
        {"role": "assistant", "content": [{"type": "text", "text": "**2297**"}]},
    ]
    # Provenance scoring reads SQL from this trace, exactly as it does for Claude.
    assert extract_sql_calls(result.raw_trace, {"execute_query": "sql"}) == [
        {"tool_name": "execute_query", "sql": sql, "is_error": False}
    ]
    # The second request carried the tool result back to OpenAI in its own format.
    second = openai.chat.completions.calls[1]["messages"]
    assert second[-1] == {"role": "tool", "tool_call_id": "call_1", "content": "order_count\n2297"}


def test_openai_agent_reports_the_turn_limit():
    openai = _fake_openai(_completion(None, [_tool_call("select 1")]))

    result = asyncio.run(
        OpenAIMCPAgentClient(_FakeMCP(), model="gpt-5.4-mini", max_tool_turns=1, client=openai).run("?")
    )

    assert result.hit_turn_limit
    assert result.answer.startswith("[honest-agent error] Exceeded max_tool_turns=1")


def _invoke_run(args, env):
    Path("evals").mkdir()
    return CliRunner().invoke(
        main,
        ["run", "--evals-dir", "evals", "--mcp-command", "python server.py", *args],
        env={
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
            "HONEST_AGENT_MODEL": "",
            "HONEST_AGENT_JUDGE_MODEL": "",
            **env,
        },
    )


def test_an_openai_only_run_needs_only_the_openai_key(fake_run, in_tmp_dir):
    result = _invoke_run(["--model", "gpt-5.4-mini"], {"OPENAI_API_KEY": "test"})

    assert result.exit_code == 0, result.output


def test_a_missing_key_names_the_provider_it_is_for(fake_run, in_tmp_dir):
    result = _invoke_run(["--model", "gpt-5.4-mini", "--judge-model", "claude-haiku-4-5"], {"OPENAI_API_KEY": "test"})

    assert result.exit_code != 0
    assert "ANTHROPIC_API_KEY not set" in result.output


def test_without_model_an_openai_only_user_gets_the_openai_default(fake_run, in_tmp_dir):
    result = _invoke_run([], {"OPENAI_API_KEY": "test"})

    assert result.exit_code == 0, result.output
    assert (fake_run["model"], fake_run["judge_model"]) == ("gpt-5.4-mini", "gpt-5.4-mini")
    assert "No --model given; using gpt-5.4-mini (OPENAI_API_KEY is set)" in result.output


def test_without_model_claude_is_the_default_when_both_keys_are_set(fake_run, in_tmp_dir):
    result = _invoke_run([], {"OPENAI_API_KEY": "test", "ANTHROPIC_API_KEY": "test"})

    assert result.exit_code == 0, result.output
    assert fake_run["model"] == "claude-haiku-4-5"


def test_honest_agent_model_sets_the_default_model(fake_run, in_tmp_dir):
    result = _invoke_run([], {"OPENAI_API_KEY": "test", "HONEST_AGENT_MODEL": "gpt-5.4"})

    assert result.exit_code == 0, result.output
    assert fake_run["model"] == "gpt-5.4"


def test_without_any_api_key_run_says_which_keys_it_accepts(fake_run, in_tmp_dir):
    result = _invoke_run([], {})

    assert result.exit_code != 0
    assert "Add ANTHROPIC_API_KEY (Claude) or OPENAI_API_KEY (GPT)" in result.output
