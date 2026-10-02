"""The model providers agent-quiz can use, for both the agent under test and the
grader: Anthropic (Claude) or OpenAI (GPT). The provider is inferred from the model
name, so a run only needs the API key for the providers its models come from.

Imports of the `anthropic`/`openai` SDKs stay inside constructors, so neither is
needed unless a model from that provider is actually used.
"""

from __future__ import annotations

from typing import Any, Protocol

ANTHROPIC = "anthropic"
OPENAI = "openai"
API_KEY_ENV = {ANTHROPIC: "ANTHROPIC_API_KEY", OPENAI: "OPENAI_API_KEY"}
_OPENAI_PREFIXES = ("gpt-", "chatgpt-", "o1", "o3", "o4")


def provider_for(model: str) -> str:
    """OpenAI for GPT/o-series names (gpt-5.4-mini, o4-mini, ...), Anthropic otherwise."""
    return OPENAI if model.lower().startswith(_OPENAI_PREFIXES) else ANTHROPIC


class Judge(Protocol):
    """A single prompt-in, text-out call, which is all grading needs."""

    async def complete(self, prompt: str, model: str, max_tokens: int) -> tuple[str, int, int]:
        """Returns (text, input_tokens, output_tokens)."""
        ...


class AnthropicJudge:
    def __init__(self, client: Any = None):
        if client is None:
            import anthropic

            client = anthropic.AsyncAnthropic()
        self._client = client

    async def complete(self, prompt: str, model: str, max_tokens: int) -> tuple[str, int, int]:
        response = await self._client.messages.create(
            model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}]
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return text, response.usage.input_tokens, response.usage.output_tokens


class OpenAIJudge:
    def __init__(self, client: Any = None):
        self._client = client or openai_client()

    async def complete(self, prompt: str, model: str, max_tokens: int) -> tuple[str, int, int]:
        # No output cap here: on reasoning models (gpt-5.x, o-series) the cap also
        # counts hidden reasoning tokens, so a small one can leave the answer empty.
        # Grading prompts ask for a one-line JSON object, so the output stays short.
        response = await self._client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}]
        )
        text = response.choices[0].message.content or ""
        return text, response.usage.prompt_tokens, response.usage.completion_tokens


def make_judge(provider: str) -> Judge:
    return OpenAIJudge() if provider == OPENAI else AnthropicJudge()


def require_openai_sdk() -> Any:
    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "OpenAI models need the openai package: pip install 'agent-quiz[openai]' (or `uv sync --extra openai`)."
        ) from exc
    return openai


def openai_client() -> Any:
    return require_openai_sdk().AsyncOpenAI()
