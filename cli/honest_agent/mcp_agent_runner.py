"""An AgentClient backed by a live MCP server, for the case where the agent
employees actually use is connected via MCP.

This intentionally does *not* take a `tools`/tool_executors argument --
tools are listed from the live MCP server at run time, so `tools_used` (and
provenance's SQL-source checking) reflects exactly what a real MCP-connected
agent can call, not a locally re-implemented stand-in whose behavior could
drift out of sync with the real tool.

Imports of `mcp` are kept inside functions so commands that don't need it
(`report`, `notify`, `export`, `logs`) don't pay its import cost.
"""

from __future__ import annotations

import os
import shlex
from typing import TYPE_CHECKING, Any

from .agent_runner import AgentClient, plain_content

if TYPE_CHECKING:
    from .raw import EvalRecorder

# Output cap per model turn. A turn cut off by it shows stop_reason "max_tokens" in its
# recorded response.
MAX_TOKENS = 1024


def build_mcp_client(
    command: str | None = None,
    url: str | None = None,
    bearer_token: str | None = None,
    cwd: str | None = None,
    env_names: list[str] | None = None,
):
    """Builds an (unconnected) mcp.Client.

    Pass exactly one of:
      - `command`: a shell command launching a local MCP server over stdio,
        e.g. "python mcp_server/server.py", started in `cwd` if given. The server
        gets only the MCP SDK's minimal environment (PATH, HOME, ...) plus the
        variables named in `env_names` -- never the rest of .env, so a
        third-party server can't read the model API keys or other secrets.
      - `url`: a remote MCP server's streamable-HTTP endpoint, e.g.
        "https://mcp.internal.example.com/mcp". `bearer_token`, if given, is
        sent as an `Authorization: Bearer <token>` header on every request.

    Connect it with `async with build_mcp_client(...) as client: ...`.
    """
    if command and url:
        raise ValueError("Pass either --mcp-command (stdio) or --mcp-url (HTTP), not both.")
    if not command and not url:
        raise ValueError("MCP backend selected but neither --mcp-command nor --mcp-url was given.")
    if command and not shlex.split(command):
        raise ValueError("--mcp-command was empty.")

    # Validation above doesn't need `mcp` importable; only the actual client
    # construction does, so error messages stay clear even without the extra
    # installed, and this function's validation is unit-testable without it.
    from mcp import Client, StdioServerParameters

    if command:
        parts = shlex.split(command)
        from mcp.client.stdio import get_default_environment

        env = {**get_default_environment(), **{name: os.environ[name] for name in env_names or []}}
        return Client(StdioServerParameters(command=parts[0], args=parts[1:], env=env, cwd=cwd))

    if bearer_token:
        import httpx2
        from mcp.client.streamable_http import streamable_http_client

        http_client = httpx2.AsyncClient(headers={"Authorization": f"Bearer {bearer_token}"})
        return Client(streamable_http_client(url, http_client=http_client))
    return Client(url)


def _mcp_tool_to_anthropic_schema(tool: Any) -> dict:
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema,
    }


class MCPAgentClient(AgentClient):
    """Claude as the agent, with the tools of a live, already-connected `mcp.Client`."""

    def __init__(self, mcp_client, model: str, tools: list, max_tool_turns: int = 5):
        import anthropic

        self._anthropic = anthropic.AsyncAnthropic()
        self._mcp = mcp_client
        self._model = model
        self._tools = [_mcp_tool_to_anthropic_schema(t) for t in tools]
        self._max_tool_turns = max_tool_turns

    async def run(self, prompt: str, record: EvalRecorder) -> None:
        messages: list[dict] = [{"role": "user", "content": prompt}]
        already_recorded = 0  # messages earlier events hold: past requests, and responses
        # When the loop runs out of turns while Claude still asks for tools, there is no
        # final answer; derive.py reads that from the last recorded response.
        for _ in range(self._max_tool_turns):
            request = {
                "model": self._model,
                "max_tokens": MAX_TOKENS,
                "tools": [tool["name"] for tool in self._tools],  # in full in raw.runs.tools_offered
                "messages": messages[already_recorded:],
            }
            response = await record.call(
                "model_call",
                "anthropic",
                request,
                self._anthropic.messages.create(
                    model=self._model, max_tokens=MAX_TOKENS, tools=self._tools, messages=messages
                ),
            )
            messages.append({"role": "assistant", "content": plain_content(response.content)})
            already_recorded = len(messages)  # the reply just appended is that call's response
            tool_calls = [block for block in response.content if block.type == "tool_use"]
            if not tool_calls:
                return

            tool_results = []
            for call in tool_calls:
                result = await record.call(
                    "tool_call",
                    "mcp",
                    {"tool_use_id": call.id, "name": call.name, "arguments": call.input},
                    self._mcp.call_tool(call.name, call.input),
                )
                text = "\n".join(block.text for block in result.content if getattr(block, "type", None) == "text")
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": call.id, "content": text, "is_error": result.is_error}
                )
            messages.append({"role": "user", "content": tool_results})
