"""The model providers honest-agent can use, for both the agent under test and the
grader: Anthropic (Claude) or OpenAI (GPT). The provider is inferred from the model
name, so a run only needs the API key for the providers its models come from.

Imports of the `anthropic`/`openai` SDKs stay inside constructors, so neither is
needed unless a model from that provider is actually used.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

ANTHROPIC = "anthropic"
OPENAI = "openai"
API_KEY_ENV = {ANTHROPIC: "ANTHROPIC_API_KEY", OPENAI: "OPENAI_API_KEY"}
_OPENAI_PREFIXES = ("gpt-", "chatgpt-", "o1", "o3", "o4")


def provider_for(model: str) -> str:
    """OpenAI for GPT/o-series names (gpt-5.4-mini, o4-mini, ...), Anthropic otherwise."""
    return OPENAI if model.lower().startswith(_OPENAI_PREFIXES) else ANTHROPIC


class Judge(Protocol):
    """A single prompt-in call, which is all grading needs. Returns the provider's
    response object as-is: the run records it raw, and derive.py reads it back."""

    async def complete(self, prompt: str, model: str, max_tokens: int) -> Any: ...


class AnthropicJudge:
    def __init__(self, client: Any = None):
        if client is None:
            import anthropic

            client = anthropic.AsyncAnthropic()
        self._client = client

    async def complete(self, prompt: str, model: str, max_tokens: int) -> Any:
        return await self._client.messages.create(
            model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}]
        )


class OpenAIJudge:
    def __init__(self, client: Any = None):
        self._client = client or openai_client()

    async def complete(self, prompt: str, model: str, max_tokens: int) -> Any:
        # No output cap here: on reasoning models (gpt-5.x, o-series) the cap also
        # counts hidden reasoning tokens, so a small one can leave the answer empty.
        # Grading prompts ask for a one-line JSON object, so the output stays short.
        return await self._client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])


def response_text(provider: str, response: dict) -> str:
    """The text of a recorded model response (the JSON raw.events keeps), for either provider."""
    if provider == OPENAI:
        return response["choices"][0]["message"].get("content") or ""
    return "".join(block.get("text", "") for block in response.get("content", []) if block.get("type") == "text")


def response_tokens(provider: str, response: dict) -> tuple[int, int]:
    """(input, output) tokens of a recorded model response, for either provider."""
    usage = response.get("usage") or {}
    if provider == OPENAI:
        return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    return usage.get("input_tokens", 0), usage.get("output_tokens", 0)


def make_judge(provider: str) -> Judge:
    return OpenAIJudge() if provider == OPENAI else AnthropicJudge()


def openai_client() -> Any:
    import openai

    return openai.AsyncOpenAI()


# Used when --model isn't given: a small, cheap model from whichever provider has a key.
DEFAULT_MODELS = {ANTHROPIC: "claude-haiku-4-5", OPENAI: "gpt-5.4-mini"}


def default_model(environ: Mapping[str, str]) -> str | None:
    """Claude's default when ANTHROPIC_API_KEY is set (including when both keys are),
    else OpenAI's when OPENAI_API_KEY is set, else None."""
    for provider in (ANTHROPIC, OPENAI):
        if environ.get(API_KEY_ENV[provider]):
            return DEFAULT_MODELS[provider]
    return None
