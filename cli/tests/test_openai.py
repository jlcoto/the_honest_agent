"""OpenAI support with fake clients -- nothing here calls a real API."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace as NS

from click.testing import CliRunner
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
)

from honest_agent.agent_runner import to_jsonable
from honest_agent.cli import main
from honest_agent.grading import GRADING_SCHEMAS
from honest_agent.llm import (
    ANTHROPIC,
    OPENAI,
    OPENAI_CHAT,
    OPENAI_RESPONSES,
    OpenAIJudge,
    provider_error,
    provider_for,
    recorded_provider,
    response_cache_tokens,
    response_stop,
    response_text,
    response_tokens,
)
from honest_agent.openai_agent_runner import OpenAIMCPAgentClient, OpenAIResponsesAgentClient


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
    reply = {
        "output": [
            {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "gAAAA"},
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": '{"score": 1.0}', "annotations": []}],
            },
        ],
        "status": "completed",
        "usage": {"input_tokens": 30, "output_tokens": 8, "output_tokens_details": {"reasoning_tokens": 4}},
    }
    client = NS(responses=_FakeCompletions([reply]))

    schema = GRADING_SCHEMAS["llm_judge"]
    judge = OpenAIJudge(client)
    response = asyncio.run(judge.complete("grade this", model="gpt-5.4-mini", max_tokens=200, schema=schema))
    recorded = to_jsonable(response)

    (call,) = client.responses.calls
    assert call["input"] == [{"role": "user", "content": "grade this"}]
    assert "reasoning" not in call  # none set: the model's default
    assert call["text"] == {"format": {"type": "json_schema", "name": "grade", "strict": True, "schema": schema}}
    assert call["store"] is False

    assert response_text(OPENAI_RESPONSES, recorded) == '{"score": 1.0}'
    assert response_tokens(OPENAI_RESPONSES, recorded) == (30, 8)
    assert response_stop(OPENAI_RESPONSES, recorded) == "end_turn"
    assert response_tokens(ANTHROPIC, {"usage": {"input_tokens": 12, "output_tokens": 3}}) == (12, 3)


def test_an_old_chat_completions_grading_reply_still_reads():
    recorded = to_jsonable(_completion('{"score": 1.0}', prompt_tokens=30, completion_tokens=8))

    assert response_text(OPENAI_CHAT, recorded) == '{"score": 1.0}'
    assert response_tokens(OPENAI_CHAT, recorded) == (30, 8)


def test_grading_calls_are_recorded_under_the_api_they_go_to():
    assert recorded_provider("gpt-6.1-sol") == OPENAI_RESPONSES
    assert recorded_provider("claude-sonnet-5-5") == ANTHROPIC
    assert recorded_provider("decision:gpt-6-luna") == "openai_decisions"


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


# The Chat Completions agent (OpenAIMCPAgentClient): no longer used for OpenAI's own
# models, kept for endpoints that speak only Chat Completions.


def test_openai_chat_agent_records_each_call_and_sends_tool_results_back():
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


def test_openai_chat_agent_stops_at_max_tool_steps():
    openai = _fake_openai(_completion(None, [_tool_call("select 1")]))
    recorder = _Recorder()

    asyncio.run(
        OpenAIMCPAgentClient(_FakeMCP(), model="gpt-5.4-mini", tools=[], max_tool_steps=1, client=openai).run(
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
            "HONEST_AGENT_GRADING_MODEL": "",
            "HONEST_AGENT_EFFORT": "",
            "HONEST_AGENT_GRADING_EFFORT": "",
            **env,
        },
    )


def test_an_openai_only_run_needs_only_the_openai_key(fake_run, in_tmp_dir):
    result = _invoke_run(["--model", "gpt-5.4-mini"], {"OPENAI_API_KEY": "test"})

    assert result.exit_code == 0, result.output


def test_a_missing_key_names_the_provider_it_is_for(fake_run, in_tmp_dir):
    result = _invoke_run(["--model", "gpt-5.4-mini", "--grading-model", "claude-haiku-4-5"], {"OPENAI_API_KEY": "test"})

    assert result.exit_code != 0
    assert "ANTHROPIC_API_KEY not set" in result.output


def test_without_model_an_openai_only_user_gets_the_openai_default(fake_run, in_tmp_dir):
    result = _invoke_run([], {"OPENAI_API_KEY": "test"})

    assert result.exit_code == 0, result.output
    assert (fake_run["model"], fake_run["graders"]["llm_judge"]) == ("gpt-5.4-mini", "gpt-6.1-sol")
    assert fake_run["grading_effort"] == "low"
    assert "No --model given; using gpt-5.4-mini (OPENAI_API_KEY is set)" in result.output


def test_a_gpt6_model_can_be_the_agent(fake_run, in_tmp_dir):
    result = _invoke_run(["--model", "gpt-6-luna"], {"OPENAI_API_KEY": "test"})

    assert result.exit_code == 0, result.output
    assert fake_run["model"] == "gpt-6-luna"


def test_a_gpt6_model_can_still_grade(fake_run, in_tmp_dir):
    result = _invoke_run(["--model", "gpt-5.4-mini", "--grading-model", "gpt-6-luna"], {"OPENAI_API_KEY": "test"})

    assert result.exit_code == 0, result.output
    assert fake_run["graders"]["llm_judge"] == "gpt-6-luna"


def test_a_providers_error_reads_as_one_line():
    import anthropic
    import httpx2 as httpx  # the HTTP library both SDKs use
    import openai

    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    rejected = openai.BadRequestError(
        "Error code: 400 - {...}",
        response=httpx.Response(400, request=request),
        body={"message": "Function tools with reasoning_effort are not supported.", "type": "invalid_request_error"},
    )
    unauthorized = anthropic.AuthenticationError(
        "Error code: 401",
        response=httpx.Response(401, request=request),
        body={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}},
    )

    assert provider_error(rejected) == (
        "OpenAI rejected a model call (HTTP 400): Function tools with reasoning_effort are not supported."
    )
    assert provider_error(unauthorized) == "Anthropic rejected a model call (HTTP 401): invalid x-api-key"
    assert provider_error(openai.APIConnectionError(request=request)).startswith("OpenAI could not be reached: ")
    assert provider_error(ValueError("not a provider's")) is None


def test_without_model_claude_is_the_default_when_both_keys_are_set(fake_run, in_tmp_dir):
    result = _invoke_run([], {"OPENAI_API_KEY": "test", "ANTHROPIC_API_KEY": "test"})

    assert result.exit_code == 0, result.output
    assert fake_run["model"] == "claude-haiku-5-5"


def test_honest_agent_model_sets_the_default_model(fake_run, in_tmp_dir):
    result = _invoke_run([], {"OPENAI_API_KEY": "test", "HONEST_AGENT_MODEL": "gpt-5.4"})

    assert result.exit_code == 0, result.output
    assert fake_run["model"] == "gpt-5.4"


def test_without_any_api_key_run_says_which_keys_it_accepts(fake_run, in_tmp_dir):
    result = _invoke_run([], {})

    assert result.exit_code != 0
    assert "Add ANTHROPIC_API_KEY (Claude) or OPENAI_API_KEY (GPT)" in result.output


def test_openai_chat_agent_sends_server_instructions_and_a_cache_key():
    openai = _fake_openai(_completion("**2297**"))
    recorder = _Recorder()

    asyncio.run(
        OpenAIMCPAgentClient(
            _FakeMCP(),
            model="gpt-5.4-mini",
            tools=[],
            instructions="Use DuckDB SQL.",
            cache_key="honest-agent-run-1",
            client=openai,
        ).run("How many?", recorder)
    )

    (call,) = openai.chat.completions.calls
    assert call["messages"][0] == {"role": "system", "content": "Use DuckDB SQL."}
    assert call["prompt_cache_key"] == "honest-agent-run-1"
    # The record names the system message; its text is in the run's settings, once.
    assert recorder.calls[0][2]["system"] == "server instructions"
    assert recorder.calls[0][2]["messages"] == [{"role": "user", "content": "How many?"}]


def test_input_tokens_count_cached_ones_and_the_cache_split_is_kept():
    anthropic_usage = {
        "usage": {
            "input_tokens": 100,
            "cache_creation_input_tokens": 2000,
            "cache_read_input_tokens": 14000,
            "output_tokens": 50,
        }
    }
    assert response_tokens(ANTHROPIC, anthropic_usage) == (16100, 50)
    assert response_cache_tokens(ANTHROPIC, anthropic_usage) == (14000, 2000)
    openai_usage = {
        "usage": {"prompt_tokens": 16100, "completion_tokens": 50, "prompt_tokens_details": {"cached_tokens": 14000}}
    }
    assert response_tokens(OPENAI_CHAT, openai_usage) == (16100, 50)
    assert response_cache_tokens(OPENAI_CHAT, openai_usage) == (14000, 0)
    # The Responses API: input_tokens counts cached ones too. Cache writes aren't priced.
    responses_usage = {
        "usage": {
            "input_tokens": 16100,
            "output_tokens": 50,
            "input_tokens_details": {"cached_tokens": 14000, "cache_write_tokens": 2000},
            "output_tokens_details": {"reasoning_tokens": 30},
        }
    }
    assert response_tokens(OPENAI_RESPONSES, responses_usage) == (16100, 50)
    assert response_cache_tokens(OPENAI_RESPONSES, responses_usage) == (14000, 0)
    assert response_cache_tokens(ANTHROPIC, {"usage": {"input_tokens": 1, "output_tokens": 1}}) == (0, 0)


def test_the_openai_judge_sends_its_effort_under_reasoning():
    client = NS(responses=_FakeCompletions([{"output": [], "status": "completed"}]))
    schema = GRADING_SCHEMAS["llm_judge"]
    asyncio.run(OpenAIJudge(client).complete("grade", model="gpt-6.1-sol", max_tokens=200, schema=schema, effort="low"))
    assert client.responses.calls[0]["reasoning"] == {"effort": "low"}


def test_the_chat_agent_sends_its_effort_as_reasoning_effort():
    openai, recorder = _fake_openai(_completion("2297")), _Recorder()
    agent = OpenAIMCPAgentClient(_FakeMCP(), model="gpt-5.4-mini", tools=[], effort="high", client=openai)
    asyncio.run(agent.run("How many?", recorder))
    assert openai.chat.completions.calls[0]["reasoning_effort"] == "high"
    assert recorder.calls[0][2]["effort"] == "high"


# The Responses API agent (OpenAIResponsesAgentClient), which runs every OpenAI model.
# Its fakes return the SDK's own output items, so the items sent back are what the SDK
# would send.


def _function_call(call_id: str, sql: str) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        type="function_call",
        id=f"fc_{call_id}",
        call_id=call_id,
        name="execute_query",
        arguments=json.dumps({"sql": sql}),
        status="completed",
    )


def _reasoning(item_id: str) -> ResponseReasoningItem:
    return ResponseReasoningItem(type="reasoning", id=item_id, summary=[], encrypted_content=f"encrypted-{item_id}")


def _message(words: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        type="message",
        id="msg_1",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text=words, annotations=[])],
    )


def _response(*output, status="completed"):
    return NS(output=list(output), status=status)


def _fake_responses(*responses):
    return NS(responses=_FakeCompletions(responses))


def _run_responses_agent(openai, **options) -> tuple[_Recorder, _FakeMCP]:
    mcp, recorder = _FakeMCP(), _Recorder()
    tools = asyncio.run(mcp.list_tools()).tools
    agent = OpenAIResponsesAgentClient(mcp, model="gpt-6-luna", tools=tools, client=openai, **options)
    asyncio.run(agent.run("How many?", recorder))
    return recorder, mcp


def test_responses_agent_records_each_call_and_sends_tool_results_back():
    sql = "select count(*) from orders where year(o_orderdate) = 1996"
    openai = _fake_responses(_response(_function_call("call_1", sql)), _response(_message("**2297**")))

    recorder, mcp = _run_responses_agent(openai)

    assert [(kind, provider) for kind, provider, _ in recorder.calls] == [
        ("model_call", "openai_responses"),
        ("tool_call", "mcp"),
        ("model_call", "openai_responses"),
    ]
    assert mcp.calls == [("execute_query", {"sql": sql})]
    # The tool call is recorded by its call_id, which its result goes back with.
    assert recorder.calls[1][2] == {"tool_use_id": "call_1", "name": "execute_query", "arguments": {"sql": sql}}
    first, second = openai.responses.calls
    assert first["input"] == [{"role": "user", "content": "How many?"}]
    assert first["store"] is False
    assert first["tools"] == [
        {
            "type": "function",
            "name": "execute_query",
            "description": "Run SQL",
            "parameters": {"type": "object", "properties": {}},
            "strict": False,
        }
    ]
    assert second["input"][1]["type"] == "function_call"
    assert second["input"][-1] == {"type": "function_call_output", "call_id": "call_1", "output": "order_count\n2297"}
    # The record keeps only the new item, since earlier events hold the rest.
    assert recorder.calls[2][2]["input"] == [second["input"][-1]]
    assert recorder.calls[2][2]["tools"] == ["execute_query"]


def test_responses_agent_runs_parallel_calls_in_order_and_answers_each():
    openai = _fake_responses(
        _response(_function_call("call_a", "select 1"), _function_call("call_b", "select 2")),
        _response(_message("1 and 2")),
    )

    recorder, mcp = _run_responses_agent(openai)

    assert mcp.calls == [("execute_query", {"sql": "select 1"}), ("execute_query", {"sql": "select 2"})]
    sent = openai.responses.calls[1]["input"]
    assert [(item.get("type"), item.get("call_id")) for item in sent[1:]] == [
        ("function_call", "call_a"),
        ("function_call", "call_b"),
        ("function_call_output", "call_a"),
        ("function_call_output", "call_b"),
    ]


def test_responses_agent_passes_reasoning_back_unchanged_and_in_order():
    openai = _fake_responses(
        _response(_reasoning("rs_1"), _function_call("call_1", "select 1"), _reasoning("rs_2")),
        _response(_reasoning("rs_3"), _message("1")),
    )

    _run_responses_agent(openai)

    sent = openai.responses.calls[1]["input"]
    assert [item.get("id") for item in sent] == [None, "rs_1", "fc_call_1", "rs_2", None]
    assert sent[1] == {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "encrypted-rs_1"}


def test_responses_agent_sends_effort_only_when_set():
    openai = _fake_responses(_response(_message("2297")))
    recorder, _ = _run_responses_agent(openai, effort="low")
    assert openai.responses.calls[0]["reasoning"] == {"effort": "low"}
    assert "reasoning_effort" not in openai.responses.calls[0]
    assert recorder.calls[0][2]["effort"] == "low"

    openai = _fake_responses(_response(_message("2297")))
    recorder, _ = _run_responses_agent(openai)
    assert "reasoning" not in openai.responses.calls[0]  # the model's own default
    assert "effort" not in recorder.calls[0][2]


def test_responses_agent_sends_server_instructions_and_a_cache_key():
    openai = _fake_responses(_response(_message("2297")))

    recorder, _ = _run_responses_agent(openai, instructions="Use DuckDB SQL.", cache_key="honest-agent-run-1")

    (call,) = openai.responses.calls
    assert call["instructions"] == "Use DuckDB SQL."
    assert call["prompt_cache_key"] == "honest-agent-run-1"
    # The record names the instructions; their text is in the run's settings, once.
    assert recorder.calls[0][2]["system"] == "server instructions"


def test_responses_agent_stops_at_an_incomplete_response_even_with_a_tool_call():
    openai = _fake_responses(_response(_function_call("call_1", "select 1"), status="incomplete"))

    recorder, mcp = _run_responses_agent(openai)

    assert [kind for kind, _, _ in recorder.calls] == ["model_call"]
    assert mcp.calls == []


def test_responses_agent_stops_at_max_tool_steps():
    openai = _fake_responses(_response(_function_call("call_1", "select 1")))

    recorder, _ = _run_responses_agent(openai, max_tool_steps=1)

    assert [kind for kind, _, _ in recorder.calls] == ["model_call", "tool_call"]


def _recorded(*output, status="completed", **response) -> dict:
    return {"output": [to_jsonable(item) for item in output], "status": status, **response}


def test_a_recorded_responses_reply_reads_like_the_others():
    answered = _recorded(_reasoning("rs_1"), _message("It was "), _message("2297."))
    assert response_text(OPENAI_RESPONSES, answered) == "It was 2297."
    assert response_stop(OPENAI_RESPONSES, answered) == "end_turn"

    asked = _recorded(_reasoning("rs_1"), _function_call("call_1", "select 1"))
    assert response_text(OPENAI_RESPONSES, asked) == ""
    assert response_stop(OPENAI_RESPONSES, asked) == "tool_use"

    # Cut off: that wins over the tool call in it, whose arguments can be cut off too.
    cut = _recorded(
        _function_call("call_1", "sel"), status="incomplete", incomplete_details={"reason": "max_output_tokens"}
    )
    assert response_stop(OPENAI_RESPONSES, cut) == "max_output_tokens"
    assert response_stop(OPENAI_RESPONSES, _recorded(status="failed")) == "failed"
