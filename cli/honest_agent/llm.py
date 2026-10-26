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


# How much a model thinks before it answers, for the agent (`effort`) and the judge
# (`grading_effort`). The three levels both providers accept on their current models;
# Anthropic's API calls it `effort`, OpenAI's `reasoning_effort`.
EFFORTS = ("low", "medium", "high")

# Models known to reject an effort setting, so a run stops before the first call instead
# of failing in it: Claude Haiku 4.5 and Sonnet 4.5 take only a thinking budget (which
# honest-agent doesn't send), Claude 3 models neither, and OpenAI's models that don't
# reason (GPT-4.x, GPT-4o, ChatGPT) have no reasoning_effort.
_NO_EFFORT_PREFIXES = ("claude-haiku-4-5", "claude-sonnet-4-5", "claude-3", "gpt-4", "chatgpt-")


def effort_unsupported(model: str) -> bool:
    """Whether `model` is known to reject an effort setting."""
    return model.lower().startswith(_NO_EFFORT_PREFIXES)


def effort_params(provider: str, effort: str | None) -> dict:
    """The request parameters that set `effort` for `provider`; none when it's unset, so
    the provider's default applies."""
    if effort is None:
        return {}
    return {"reasoning_effort": effort} if provider == OPENAI else {"output_config": {"effort": effort}}


class Judge(Protocol):
    """A single prompt-in call, which is all grading needs, with the reply constrained to
    `schema` (a JSON schema). Returns the provider's response object as-is: the run
    records it raw, and derive.py reads the reply's text back."""

    async def complete(
        self, prompt: str, model: str, max_tokens: int, schema: dict, effort: str | None = None
    ) -> Any: ...


class AnthropicJudge:
    def __init__(self, client: Any = None):
        if client is None:
            import anthropic

            client = anthropic.AsyncAnthropic()
        self._client = client

    async def complete(self, prompt: str, model: str, max_tokens: int, schema: dict, effort: str | None = None) -> Any:
        # Structured output: the reply is a text block holding JSON that matches `schema`.
        # Thinking counts toward max_tokens, so a low effort also keeps the verdict in it.
        output_config: dict = {"format": {"type": "json_schema", "schema": schema}}
        if effort is not None:
            output_config["effort"] = effort
        return await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_config=output_config,
        )


class OpenAIJudge:
    def __init__(self, client: Any = None):
        self._client = client or openai_client()

    async def complete(self, prompt: str, model: str, max_tokens: int, schema: dict, effort: str | None = None) -> Any:
        # No output cap here: on reasoning models (gpt-5.x, o-series) the cap also
        # counts hidden reasoning tokens, so a small one can leave the answer empty.
        # Grading prompts ask for a one-line JSON object, so the output stays short.
        return await self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": {"name": "grade", "strict": True, "schema": schema}},
            **effort_params(OPENAI, effort),
        )


def response_text(provider: str, response: dict) -> str:
    """The text of a recorded model response (the JSON raw.events keeps), for either provider."""
    if provider == OPENAI:
        return response["choices"][0]["message"].get("content") or ""
    return "".join(block.get("text", "") for block in response.get("content", []) if block.get("type") == "text")


def response_tokens(provider: str, response: dict) -> tuple[int, int]:
    """(input, output) tokens of a recorded model response, for either provider. Input
    counts every prompt token, cached or not, so runs with and without caching compare."""
    usage = response.get("usage") or {}
    if provider == OPENAI:
        return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    # Anthropic's input_tokens leaves out the tokens written to or read from the cache.
    cached = (usage.get("cache_creation_input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
    return (usage.get("input_tokens") or 0) + cached, usage.get("output_tokens", 0)


def response_cache_tokens(provider: str, response: dict) -> tuple[int, int]:
    """(read, written) prompt tokens of a recorded model response that came from or went to
    the provider's cache. Reads cost a fraction of input; Anthropic charges extra for
    writes, OpenAI doesn't report them (0)."""
    usage = response.get("usage") or {}
    if provider == OPENAI:
        return (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0, 0
    return usage.get("cache_read_input_tokens") or 0, usage.get("cache_creation_input_tokens") or 0


def response_stop(provider: str, response: dict) -> str | None:
    """Why a recorded model response stopped, in Anthropic's terms for either provider:
    "tool_use" (it asked for tools), "end_turn" (it answered), or the provider's own reason."""
    if provider == OPENAI:
        reason = (response.get("choices") or [{}])[0].get("finish_reason")
        return {"tool_calls": "tool_use", "stop": "end_turn"}.get(reason, reason)
    return response.get("stop_reason")


def make_judge(provider: str) -> Judge:
    return OpenAIJudge() if provider == OPENAI else AnthropicJudge()


def openai_client() -> Any:
    import openai

    return openai.AsyncOpenAI()


# Used when --model isn't given: a small, cheap model from whichever provider has a key.
DEFAULT_MODELS = {ANTHROPIC: "claude-haiku-5-5", OPENAI: "gpt-5.4-mini"}

# OpenAI's GPT-6 models can't think and call tools in one request on Chat Completions, the
# API honest-agent uses; they need the Responses API. So they can't be the agent yet. They
# can grade: grading calls no tools.
_NO_AGENT_PREFIXES = ("gpt-6",)


def agent_unsupported(model: str) -> bool:
    """Whether `model` can't be the agent yet (see _NO_AGENT_PREFIXES)."""
    return model.lower().startswith(_NO_AGENT_PREFIXES)


def provider_error(exc: BaseException) -> str | None:
    """A provider's error for a model call (rejected, unauthorized, rate-limited,
    unreachable) as one line, or None when `exc` isn't one."""
    kinds = []
    for module in ("anthropic", "openai"):
        try:
            kinds.append(__import__(module).APIError)
        except ImportError:
            pass
    if not isinstance(exc, tuple(kinds)):
        return None
    name = "OpenAI" if type(exc).__module__.startswith("openai") else "Anthropic"
    body = getattr(exc, "body", None)
    error = body.get("error", body) if isinstance(body, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    status = getattr(exc, "status_code", None)
    return f"{name} {f'rejected a model call (HTTP {status})' if status else 'could not be reached'}: {message or exc}"


# Used when --grading-model isn't given: a stronger model than the default agent, from the
# agent's own provider (so one API key is enough). Never the agent's model by default: a
# model grading its own answers tends to favour them.
DEFAULT_GRADING_MODELS = {ANTHROPIC: "claude-sonnet-5-5", OPENAI: "gpt-6.1-sol"}
# The default judge's effort: grading against an expected answer needs little thinking.
DEFAULT_GRADING_EFFORT = "low"


def default_grading_model(model: str) -> str:
    """The default judge for an agent running `model`."""
    return DEFAULT_GRADING_MODELS[provider_for(model)]


# A rough capability rank by model tier, within one provider, from words in the name. Only
# tiers the providers present as steps up; a name with none of them has no rank, and
# models from two providers aren't compared.
_TIERS = {
    ANTHROPIC: (("haiku", 1), ("sonnet", 2), ("opus", 3), ("fable", 4), ("mythos", 4)),
    OPENAI: (("nano", 0), ("mini", 1), ("luna", 1), ("sol", 2), ("astra", 3)),
}


def tier(model: str) -> int | None:
    """`model`'s tier within its provider (Haiku < Sonnet < Opus; Luna < Sol < Astra), or
    None when the name doesn't say."""
    name = model.lower()
    return next((rank for word, rank in _TIERS[provider_for(model)] if word in name), None)


def looks_less_capable(grading_model: str, model: str) -> bool:
    """Whether the grading model is from a lower tier than the agent's, same provider."""
    if provider_for(grading_model) != provider_for(model):
        return False
    judge, agent = tier(grading_model), tier(model)
    return judge is not None and agent is not None and judge < agent


def default_model(environ: Mapping[str, str]) -> str | None:
    """Claude's default when ANTHROPIC_API_KEY is set (including when both keys are),
    else OpenAI's when OPENAI_API_KEY is set, else None."""
    for provider in (ANTHROPIC, OPENAI):
        if environ.get(API_KEY_ENV[provider]):
            return DEFAULT_MODELS[provider]
    return None
