"""AgentClients that evaluate an OpenAI model (GPT) against a live MCP server -- the
same loop as AnthropicMCPAgentClient (anthropic_agent_runner.py), on OpenAI's APIs
instead of Anthropic's. OpenAIResponsesAgentClient, on the Responses API, runs every
OpenAI model: the ones that think by default (GPT-5.6, GPT-6) can call tools only there.
OpenAIMCPAgentClient, on Chat Completions, is no longer used for OpenAI's own models; it
stays for the endpoints that speak only Chat Completions.

Every call is recorded as OpenAI sent and returned it (raw.py); derive.py turns
the record into the one conversation format the rest of honest-agent reads, so
nothing downstream needs to know which provider ran the eval.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .agent_runner import AgentClient
from .llm import OPENAI_CHAT, OPENAI_RESPONSES, effort_params, openai_client

if TYPE_CHECKING:
    from .raw import EvalRecorder


def _mcp_tool_to_openai_schema(tool: Any) -> dict:
    return {
        "type": "function",
        "function": {"name": tool.name, "description": tool.description or "", "parameters": tool.input_schema},
    }


def _mcp_tool_to_responses_schema(tool: Any) -> dict:
    # Not strict: strict mode needs every property required and no others allowed, which
    # MCP input schemas aren't written for. Left out, the API tries to make it strict.
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description or "",
        "parameters": tool.input_schema,
        "strict": False,
    }


def _input_item(item: Any) -> dict:
    """A response's output item as the input item that sends it back, unchanged: the
    fields OpenAI returned, as the SDK itself would send them (a reasoning item keeps
    its encrypted_content)."""
    return item.model_dump(mode="json", exclude_unset=True)


class OpenAIResponsesAgentClient(AgentClient):
    """GPT as the agent on the Responses API, with the tools of a live, already-connected
    `mcp.Client`. Nothing is stored at OpenAI between steps (`store: false`): each call
    sends the whole conversation, the model's reasoning included as OpenAI returned it
    (encrypted), which reasoning models need back with the tool results."""

    def __init__(
        self,
        mcp_client,
        model: str,
        tools: list,
        max_tool_steps: int = 5,
        instructions: str | None = None,
        cache_key: str | None = None,
        effort: str | None = None,
        client: Any = None,
    ):
        self._openai = client or openai_client()
        self._mcp = mcp_client
        self._model = model
        self._tools = [_mcp_tool_to_responses_schema(t) for t in tools]
        self._max_tool_steps = max_tool_steps
        # The server's instructions, sent as the system message like a chat client would.
        self._optional: dict = {"instructions": instructions} if instructions else {}
        # OpenAI caches a repeated prompt start by itself; one key per run keeps a run's
        # calls on the same cache.
        if cache_key:
            self._optional["prompt_cache_key"] = cache_key
        # Unset: nothing is sent, and the model runs at its own default effort.
        self._effort = effort
        self._optional |= effort_params(OPENAI_RESPONSES, effort)

    async def run(self, prompt: str, record: EvalRecorder) -> None:
        items: list[dict] = [{"role": "user", "content": prompt}]
        already_recorded = 0  # items earlier events hold: past requests, and responses
        for _ in range(self._max_tool_steps):
            # No max_output_tokens: it also counts reasoning tokens, so a cap can cut off
            # the answer itself.
            request = {
                "model": self._model,
                "tools": [tool["name"] for tool in self._tools],  # in full in raw.runs.tools_offered
                "input": items[already_recorded:],
            }
            if "instructions" in self._optional:
                request["system"] = "server instructions"  # in full in raw.runs.settings
            if self._effort:
                request["effort"] = self._effort
            response = await record.call(
                "model_call",
                OPENAI_RESPONSES,
                request,
                self._openai.responses.create(
                    model=self._model, input=items, tools=self._tools, store=False, **self._optional
                ),
            )
            # Every output item goes back in order (reasoning, messages, function calls):
            # reasoning dropped or moved can be lost to the model.
            items += [_input_item(item) for item in response.output]
            already_recorded = len(items)  # the items just added are that call's response
            calls = [item for item in response.output if item.type == "function_call"]
            # A response cut off is the reply (derive.py reports it): its calls' arguments
            # can be cut off too.
            if not calls or response.status == "incomplete":
                return

            for call in calls:
                arguments = json.loads(call.arguments or "{}")
                result = await record.call(
                    "tool_call",
                    "mcp",
                    {"tool_use_id": call.call_id, "name": call.name, "arguments": arguments},
                    self._mcp.call_tool(call.name, arguments),
                )
                result_text = "\n".join(
                    block.text for block in result.content if getattr(block, "type", None) == "text"
                )
                items.append({"type": "function_call_output", "call_id": call.call_id, "output": result_text})


class OpenAIMCPAgentClient(AgentClient):
    """GPT as the agent on Chat Completions, with the tools of a live, already-connected
    `mcp.Client`. Not used for OpenAI's own models (OpenAIResponsesAgentClient is): the
    ones that think can't call tools here with an effort set."""

    def __init__(
        self,
        mcp_client,
        model: str,
        tools: list,
        max_tool_steps: int = 5,
        instructions: str | None = None,
        cache_key: str | None = None,
        effort: str | None = None,
        client: Any = None,
    ):
        self._openai = client or openai_client()
        self._mcp = mcp_client
        self._model = model
        self._tools = [_mcp_tool_to_openai_schema(t) for t in tools]
        self._max_tool_steps = max_tool_steps
        # The server's instructions, sent as the system message like a chat client would.
        self._system = [{"role": "system", "content": instructions}] if instructions else []
        # OpenAI caches a repeated prompt start by itself; one key per run keeps a run's
        # calls on the same cache.
        self._optional = {"prompt_cache_key": cache_key} if cache_key else {}
        # Unset: nothing is sent, and the model runs at the provider's default effort.
        self._effort = effort
        self._optional |= effort_params(OPENAI_CHAT, effort)

    async def run(self, prompt: str, record: EvalRecorder) -> None:
        chat: list[dict] = [{"role": "user", "content": prompt}]
        already_recorded = 0  # messages earlier events hold: past requests, and responses
        for _ in range(self._max_tool_steps):
            # No max_completion_tokens: on reasoning models it also counts hidden
            # reasoning tokens, so a cap can cut off the answer itself.
            request = {
                "model": self._model,
                "tools": [tool["function"]["name"] for tool in self._tools],  # in full in raw.runs.tools_offered
                "messages": chat[already_recorded:],
            }
            if self._system:
                request["system"] = "server instructions"  # in full in raw.runs.settings
            if self._effort:
                request["effort"] = self._effort
            response = await record.call(
                "model_call",
                OPENAI_CHAT,
                request,
                self._openai.chat.completions.create(
                    model=self._model, messages=self._system + chat, tools=self._tools, **self._optional
                ),
            )
            message = response.choices[0].message
            calls = message.tool_calls or []
            chat.append(
                {
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.function.name, "arguments": call.function.arguments},
                        }
                        for call in calls
                    ]
                    or None,
                }
            )
            already_recorded = len(chat)  # the reply just appended is that call's response
            if not calls:
                return

            for call in calls:
                arguments = json.loads(call.function.arguments or "{}")
                result = await record.call(
                    "tool_call",
                    "mcp",
                    {"tool_use_id": call.id, "name": call.function.name, "arguments": arguments},
                    self._mcp.call_tool(call.function.name, arguments),
                )
                result_text = "\n".join(
                    block.text for block in result.content if getattr(block, "type", None) == "text"
                )
                chat.append({"role": "tool", "tool_call_id": call.id, "content": result_text})
