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
import time
from typing import Any

from .agent_runner import AgentClient, AgentRunResult, plain_content


def build_mcp_client(
    command: str | None = None,
    url: str | None = None,
    bearer_token: str | None = None,
    cwd: str | None = None,
):
    """Builds an (unconnected) mcp.Client.

    Pass exactly one of:
      - `command`: a shell command launching a local MCP server over stdio,
        e.g. "python mcp_server/server.py", started in `cwd` if given.
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
        # The MCP SDK deliberately does NOT inherit the parent process's full
        # environment for a stdio-launched server (it merges a minimal default
        # set with whatever `env=` is passed here) -- without this, any server
        # that needs a credential via an env var (MOTHERDUCK_TOKEN, etc.) fails
        # to authenticate even though the CLI's own process has it (e.g. from
        # .env via load_dotenv()).
        return Client(StdioServerParameters(command=parts[0], args=parts[1:], env=dict(os.environ), cwd=cwd))

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
    """Sources its tools from a live, already-connected `mcp.Client`."""

    def __init__(self, mcp_client, model: str = "claude-haiku-4-5-20251001", max_tool_turns: int = 5):
        import anthropic

        self._anthropic = anthropic.AsyncAnthropic()
        self._mcp = mcp_client
        self._model = model
        self._max_tool_turns = max_tool_turns
        self._tools_cache: list[dict] | None = None

    async def _list_tools(self) -> list[dict]:
        if self._tools_cache is None:
            result = await self._mcp.list_tools()
            self._tools_cache = [_mcp_tool_to_anthropic_schema(t) for t in result.tools]
        return self._tools_cache

    async def run(self, prompt: str) -> AgentRunResult:
        start = time.monotonic()
        available_tools = await self._list_tools()
        messages: list[dict] = [{"role": "user", "content": prompt}]
        tools_used: list[str] = []
        response = None
        input_tokens = 0
        output_tokens = 0
        hit_turn_limit = False

        for _ in range(self._max_tool_turns):
            response = await self._anthropic.messages.create(
                model=self._model,
                max_tokens=1024,
                tools=available_tools,
                messages=messages,
            )
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens
            tool_calls = [block for block in response.content if block.type == "tool_use"]
            if not tool_calls:
                # Final, text-only turn -- append it so `raw_trace` captures the
                # agent's actual stated answer, not just what led up to it.
                messages.append({"role": "assistant", "content": plain_content(response.content)})
                break

            messages.append({"role": "assistant", "content": plain_content(response.content)})
            tool_results = []
            for call in tool_calls:
                tools_used.append(call.name)
                result = await self._mcp.call_tool(call.name, call.input)
                text = "\n".join(block.text for block in result.content if getattr(block, "type", None) == "text")
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": text,
                        "is_error": result.is_error,
                    }
                )
            messages.append({"role": "user", "content": tool_results})
        else:
            # The `for` loop's `else` runs only when the loop completes without
            # hitting `break` -- i.e. `max_tool_turns` was exhausted and Claude
            # was still requesting tools on the last turn. The tool_use/
            # tool_result turns above are still recorded in `messages`, but
            # there was no further `messages.create` call to let Claude respond
            # to that last result, so there's no real final answer to report.
            hit_turn_limit = True

        final_text = "".join(block.text for block in (response.content if response else []) if block.type == "text")
        if hit_turn_limit:
            final_text = (
                f"[honest-agent error] Exceeded max_tool_turns={self._max_tool_turns} without a final answer -- "
                "the agent was still requesting tools on the last turn. See agent_trace for detail."
            )
        latency_ms = int((time.monotonic() - start) * 1000)

        return AgentRunResult(
            answer=final_text.strip(),
            tools_used=tools_used,
            raw_trace=messages,
            model_name=self._model,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            hit_turn_limit=hit_turn_limit,
        )
