"""OpenAI support with fake clients -- nothing here calls a real API."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace as NS

from click.testing import CliRunner

from honest_agent.agent_runner import to_jsonable
from honest_agent.cli import main
from honest_agent.llm import ANTHROPIC, OPENAI, OpenAIJudge, provider_for, response_text, response_tokens
from honest_agent.openai_agent_runner import OpenAIMCPAgentClient


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


def test_the_openai_judge_returns_the_response_as_is_and_it_reads_back():
    client = _fake_openai(_completion('{"score": 1.0}', prompt_tokens=30, completion_tokens=8))

    response = asyncio.run(OpenAIJudge(client).complete("grade this", model="gpt-5.4-mini", max_tokens=200))
    recorded = to_jsonable(response)

    assert response_text(OPENAI, recorded) == '{"score": 1.0}'
    assert response_tokens(OPENAI, recorded) == (30, 8)
    assert response_tokens(ANTHROPIC, {"usage": {"input_tokens": 12, "output_tokens": 3}}) == (12, 3)


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


class _Recorder:
    """Stands in for raw.EvalRecorder: keeps what each call was recorded with."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def call(self, kind, provider, request, pending):
        self.calls.append((kind, provider, json.loads(json.dumps(request))))
        return await pending


def test_openai_agent_records_each_call_and_sends_tool_results_back():
    sql = "select count(*) from orders where year(o_orderdate) = 1996"
    openai = _fake_openai(_completion(None, [_tool_call(sql)]), _completion("**2297**"))
    mcp, recorder = _FakeMCP(), _Recorder()
    tools = asyncio.run(mcp.list_tools()).tools

    asyncio.run(OpenAIMCPAgentClient(mcp, model="gpt-5.4-mini", tools=tools, client=openai).run("How many?", recorder))

    assert [(kind, provider) for kind, provider, _ in recorder.calls] == [
        ("model_call", "openai"),
        ("tool_call", "mcp"),
        ("model_call", "openai"),
    ]
    assert mcp.calls == [("execute_query", {"sql": sql})]
    assert recorder.calls[1][2] == {"tool_use_id": "call_1", "name": "execute_query", "arguments": {"sql": sql}}
    # The second request carried the tool result back to OpenAI in its own format; the
    # record keeps only that new message, since earlier events hold the rest.
    sent = openai.chat.completions.calls[1]["messages"]
    assert sent[-1] == {"role": "tool", "tool_call_id": "call_1", "content": "order_count\n2297"}
    assert recorder.calls[2][2]["messages"] == [sent[-1]]


def test_openai_agent_stops_at_max_tool_turns():
    openai = _fake_openai(_completion(None, [_tool_call("select 1")]))
    recorder = _Recorder()

    asyncio.run(
        OpenAIMCPAgentClient(_FakeMCP(), model="gpt-5.4-mini", tools=[], max_tool_turns=1, client=openai).run(
            "?", recorder
        )
    )

    assert [kind for kind, _, _ in recorder.calls] == ["model_call", "tool_call"]


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
