"""The model providers honest-agent can use, for both the agent under test and the
grader: Anthropic (Claude) or OpenAI (GPT), and for llm_judge evals also a decision
model (TypeSafe's Jev, OpenAI's Decisions API, Google's Gemini Decisions). The provider
is inferred from the model name, so a run only needs the API key for the providers its
models come from.

Imports of the providers' SDKs stay inside constructors, so none is needed unless a
model from that provider is actually used.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol

ANTHROPIC = "anthropic"
OPENAI = "openai"
# Decision models: they answer a yes/no question with a probability, never with text, so
# they can judge an answer (llm_judge) but not pull a value out of it (extract_match).
TYPESAFE = "typesafe"
OPENAI_DECISIONS = "openai_decisions"
GOOGLE = "google"
DECISION_PROVIDERS = (TYPESAFE, OPENAI_DECISIONS, GOOGLE)
API_KEY_ENV = {
    ANTHROPIC: "ANTHROPIC_API_KEY",
    OPENAI: "OPENAI_API_KEY",
    TYPESAFE: "TYPESAFE_API_KEY",
    OPENAI_DECISIONS: "OPENAI_API_KEY",
    GOOGLE: "GEMINI_API_KEY",
}
# Google's SDK also reads GOOGLE_API_KEY (and prefers it when both are set).
_OTHER_KEY_ENV = {GOOGLE: ("GOOGLE_API_KEY",)}
_OPENAI_PREFIXES = ("gpt-", "chatgpt-", "o1", "o3", "o4")
# gpt-6-luna is both a chat model and the Decisions API's model, so the Decisions one is
# written with this prefix; plain gpt-6-luna stays the chat model.
OPENAI_DECISIONS_PREFIX = "decision:"


def provider_for(model: str) -> str:
    """The provider behind a model name: TypeSafe for jev-*, Google for gemini-decision-*,
    OpenAI's Decisions API for decision:<model>, OpenAI for GPT/o-series names
    (gpt-5.4-mini, o4-mini, ...), Anthropic otherwise."""
    name = model.lower()
    if name.startswith("jev-"):
        return TYPESAFE
    if name.startswith("gemini-decision"):
        return GOOGLE
    if name.startswith(OPENAI_DECISIONS_PREFIX):
        return OPENAI_DECISIONS
    return OPENAI if name.startswith(_OPENAI_PREFIXES) else ANTHROPIC


def is_decision_model(model: str) -> bool:
    """Whether `model` is a decision model (it answers yes/no with a probability)."""
    return provider_for(model) in DECISION_PROVIDERS


# TypeSafe's aliases move to each new release; jev-1.14.0 and the like stay put.
_ALIASES = ("jev-latest", "jev-preview")


def is_alias(model: str) -> bool:
    """Whether `model` is a vendor alias whose model can change between runs."""
    return model.lower() in _ALIASES


def api_key_set(provider: str, environ: Mapping[str, str]) -> bool:
    """Whether a key `provider`'s SDK reads is set."""
    return any(environ.get(name) for name in (API_KEY_ENV[provider], *_OTHER_KEY_ENV.get(provider, ())))


def api_key_name(provider: str) -> str:
    """The key to name in messages: `GEMINI_API_KEY (or GOOGLE_API_KEY)` for Google."""
    others = _OTHER_KEY_ENV.get(provider)
    return f"{API_KEY_ENV[provider]} (or {' or '.join(others)})" if others else API_KEY_ENV[provider]


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


# The one question a decision model answers, under this name, about the llm_judge
# prompt's question, expected answer and given answer (grading.judge_state).
DECISION_QUESTION_NAME = "correct"


class DecisionJudge(Protocol):
    """A yes/no question about `state`, answered with a probability. Returns the
    provider's response object as-is, like Judge: the run records it raw, and derive.py
    reads the probability back (decision_answer)."""

    async def decide(self, state: str, question: str, model: str) -> Any: ...


class TypeSafeDecisionJudge:
    def __init__(self, client: Any = None):
        if client is None:
            import typesafe_sdk

            client = typesafe_sdk.AsyncTypeSafeClient()  # reads TYPESAFE_API_KEY
        self._client = client

    async def decide(self, state: str, question: str, model: str) -> Any:
        return await self._client.system_one(
            state=state,
            questions={DECISION_QUESTION_NAME: {"type": "noul", "instructions": question}},
            model=model,
        )


class OpenAIDecisionJudge:
    def __init__(self, client: Any = None):
        self._client = client or openai_client()

    async def decide(self, state: str, question: str, model: str) -> Any:
        return await self._client.decisions.create(
            model=model.removeprefix(OPENAI_DECISIONS_PREFIX),
            input=state,
            questions=[{"type": "predicate", "name": DECISION_QUESTION_NAME, "instructions": question}],
        )


class GeminiDecisionJudge:
    def __init__(self, client: Any = None):
        if client is None:
            from google import genai

            # Decisions are only on the v1beta API; the SDK defaults to v1.
            client = genai.Client(http_options={"api_version": "v1beta"}).aio
        self._client = client

    async def decide(self, state: str, question: str, model: str) -> Any:
        return await self._client.decisions.create(
            model=model if model.startswith("models/") else f"models/{model}",
            input=state,
            questions={DECISION_QUESTION_NAME: {"type": "noul", "instructions": question}},
        )


def decision_answer(provider: str, response: dict) -> tuple[float | None, float | None]:
    """(P(yes), confidence) from a recorded decision response; confidence only where the
    provider reports one on a yes/no question (Google). P(yes) is None when the question
    got no answer, or OpenAI's Decisions API declined it (a `refusal`)."""
    if provider == OPENAI_DECISIONS:
        answer = next((a for a in response.get("answers") or [] if a.get("name") == DECISION_QUESTION_NAME), {})
        return answer.get("probability"), None
    answer = (response.get("answers") or {}).get(DECISION_QUESTION_NAME) or {}
    return answer.get("noul"), answer.get("confidence")


def served_model(provider: str, response: dict) -> str | None:
    """The model that answered, named the way the config names it (it can differ from an
    alias asked for); None when the provider doesn't say (Google). OpenAI's response
    leaves out our decision: prefix, so it's added back."""
    if provider == OPENAI_DECISIONS and response.get("model"):
        return OPENAI_DECISIONS_PREFIX + response["model"]
    return response.get("model") if provider == TYPESAFE else None


def response_text(provider: str, response: dict) -> str:
    """The text of a recorded model response (the JSON raw.events keeps), for any
    provider; a decision model's answers as JSON, since it writes no text."""
    if provider in DECISION_PROVIDERS:
        return json.dumps(response.get("answers"))
    if provider == OPENAI:
        return response["choices"][0]["message"].get("content") or ""
    return "".join(block.get("text", "") for block in response.get("content", []) if block.get("type") == "text")


def response_tokens(provider: str, response: dict) -> tuple[int, int]:
    """(input, output) tokens of a recorded model response, for either provider. Input
    counts every prompt token, cached or not, so runs with and without caching compare."""
    usage = response.get("usage") or {}
    if provider == OPENAI:
        return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    if provider == GOOGLE:
        return usage.get("total_input_tokens") or 0, usage.get("total_output_tokens") or 0
    if provider in (TYPESAFE, OPENAI_DECISIONS):
        return usage.get("input_tokens") or 0, usage.get("output_tokens") or 0
    # Anthropic's input_tokens leaves out the tokens written to or read from the cache.
    cached = (usage.get("cache_creation_input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
    return (usage.get("input_tokens") or 0) + cached, usage.get("output_tokens", 0)


def response_cache_tokens(provider: str, response: dict) -> tuple[int, int]:
    """(read, written) prompt tokens of a recorded model response that came from or went to
    the provider's cache. Reads cost a fraction of input; Anthropic charges extra for
    writes, OpenAI doesn't report them (0). Decision calls are priced as plain input."""
    if provider in DECISION_PROVIDERS:
        return 0, 0
    usage = response.get("usage") or {}
    if provider == OPENAI:
        return (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0, 0
    return usage.get("cache_read_input_tokens") or 0, usage.get("cache_creation_input_tokens") or 0


def response_stop(provider: str, response: dict) -> str | None:
    """Why a recorded model response stopped, in Anthropic's terms for either provider:
    "tool_use" (it asked for tools), "end_turn" (it answered), or the provider's own reason.
    None for a decision model: it answers in one step and is never cut off."""
    if provider in DECISION_PROVIDERS:
        return None
    if provider == OPENAI:
        reason = (response.get("choices") or [{}])[0].get("finish_reason")
        return {"tool_calls": "tool_use", "stop": "end_turn"}.get(reason, reason)
    return response.get("stop_reason")


def make_judge(provider: str) -> Judge | DecisionJudge:
    judges = {
        OPENAI: OpenAIJudge,
        TYPESAFE: TypeSafeDecisionJudge,
        OPENAI_DECISIONS: OpenAIDecisionJudge,
        GOOGLE: GeminiDecisionJudge,
    }
    return judges.get(provider, AnthropicJudge)()


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


# Each SDK's base class for an API error (and, for TypeSafe, for any error it raises).
_PROVIDER_ERRORS = (
    ("anthropic", "APIError"),
    ("openai", "APIError"),
    ("typesafe_sdk", "TypeSafeError"),
    ("google.genai._interactions_errors", "GeminiNextGenAPIClientError"),
)
_PROVIDER_NAMES = (("openai", "OpenAI"), ("typesafe_sdk", "TypeSafe"), ("google", "Google"), ("", "Anthropic"))


def provider_error(exc: BaseException) -> str | None:
    """A provider's error for a model call (rejected, unauthorized, rate-limited,
    unreachable) as one line, or None when `exc` isn't one."""
    import importlib

    kinds = []
    for module, kind in _PROVIDER_ERRORS:
        try:
            kinds.append(getattr(importlib.import_module(module), kind))
        except ImportError:
            pass
    if not isinstance(exc, tuple(kinds)):
        return None
    module = type(exc).__module__
    name = next(label for prefix, label in _PROVIDER_NAMES if module.startswith(prefix))
    body = getattr(exc, "body", None)
    error = body.get("error", body) if isinstance(body, dict) else None
    message = (error.get("message") if isinstance(error, dict) else None) or getattr(exc, "message", None)
    # TypeSafe's errors call it `status`; Google's `status` is a word, so only an int counts.
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    status = status if isinstance(status, int) else None
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
    """Whether the grading model is from a lower tier than the agent's, same provider.
    Decision models aren't ranked against the LLMs they grade."""
    if provider_for(grading_model) != provider_for(model) or is_decision_model(grading_model):
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
