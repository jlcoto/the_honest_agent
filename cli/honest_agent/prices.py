"""What a run's model calls cost, estimated as token counts × the providers' published
prices. The table below is kept by hand and ships with each release (checked against the
providers' pricing pages at release time; CONTRIBUTING.md has the step), so a run never
downloads anything. `prices:` in honest_agent_config.yml adds models or overrides these.

A run saves the prices of its two models in its settings (raw layer), so its cost stays
what it was when it ran, through a `rebuild` and after this table changes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass

from .llm import response_cache_tokens, response_tokens

PRICES_AS_OF = "2026-10-28"


@dataclass(frozen=True)
class Price:
    """USD per million tokens. Input is the prompt tokens neither read from nor written to
    the cache. Above `long_above` prompt tokens, a call is priced at `long` instead, all of
    it (Claude Haiku 5.5 above 100k, for one)."""

    input: float
    output: float
    cache_read: float
    cache_write: float
    long_above: int | None = None
    long: Price | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: Mapping) -> Price:
        long = d.get("long")
        return Price(**{**d, "long": Price.from_dict(long) if long else None})


def _long(above: int, input: float, output: float, cache_read: float, cache_write: float) -> dict:
    return {"long_above": above, "long": Price(input, output, cache_read, cache_write)}


# USD per million tokens: input, output, cache read, cache write (Claude's 5-minute write;
# OpenAI's cache writes aren't in its usage reports, see below). From
# https://platform.claude.com/docs/en/about-claude/pricing and
# https://developers.openai.com/api/docs/pricing, standard tier, as of PRICES_AS_OF.
# Claude's cache reads vary by model (0.025x to 0.1x input); its writes are 1.25x.
BUILT_IN: dict[str, Price] = {
    "claude-haiku-5-5": Price(0.10, 0.50, 0.01, 0.125, **_long(100_000, 0.50, 2.50, 0.05, 0.625)),
    "claude-sonnet-5-5": Price(2.00, 10.00, 0.10, 2.50),
    "claude-opus-5-5": Price(4.00, 20.00, 0.20, 5.00),
    "claude-fable-5-1": Price(10.00, 50.00, 0.25, 12.50),
    "claude-fable-5": Price(10.00, 50.00, 1.00, 12.50),
    "claude-sonnet-5": Price(2.00, 10.00, 0.20, 2.50),
    "claude-opus-5": Price(5.00, 25.00, 0.50, 6.25),
    "claude-opus-4-8": Price(5.00, 25.00, 0.50, 6.25),
    "claude-opus-4-7": Price(5.00, 25.00, 0.50, 6.25),
    "claude-opus-4-6": Price(5.00, 25.00, 0.50, 6.25),
    "claude-sonnet-4-6": Price(3.00, 15.00, 0.30, 3.75),
    "claude-opus-4-5": Price(5.00, 25.00, 0.50, 6.25),
    "claude-sonnet-4-5": Price(3.00, 15.00, 0.30, 3.75),
    "claude-haiku-4-5": Price(1.00, 5.00, 0.10, 1.25),
    # OpenAI: input, output, cached input; long prompts are those over 272k input tokens.
    "gpt-6-luna": Price(0.10, 0.50, 0.01, 0.0, **_long(272_000, 0.20, 0.75, 0.02, 0.0)),
    "gpt-6.1-sol": Price(2.00, 10.00, 0.10, 0.0, **_long(272_000, 4.00, 15.00, 0.20, 0.0)),
    "gpt-6.1-terra": Price(1.00, 5.00, 0.05, 0.0, **_long(272_000, 2.00, 7.50, 0.10, 0.0)),
    "gpt-6-sol": Price(2.00, 10.00, 0.20, 0.0, **_long(272_000, 4.00, 15.00, 0.40, 0.0)),
    "gpt-6-astra": Price(10.00, 50.00, 1.00, 0.0, **_long(272_000, 20.00, 75.00, 2.00, 0.0)),
    "gpt-5.6-sol": Price(4.00, 20.00, 0.40, 0.0, **_long(272_000, 8.00, 30.00, 0.80, 0.0)),
    "gpt-5.6-terra": Price(2.00, 12.00, 0.20, 0.0, **_long(272_000, 4.00, 18.00, 0.40, 0.0)),
    "gpt-5.6-luna": Price(0.20, 1.20, 0.02, 0.0, **_long(272_000, 0.40, 1.80, 0.04, 0.0)),
    "gpt-5.5": Price(5.00, 30.00, 0.50, 0.0, **_long(272_000, 10.00, 45.00, 1.00, 0.0)),
    "gpt-5.4": Price(2.50, 15.00, 0.25, 0.0, **_long(272_000, 5.00, 22.50, 0.50, 0.0)),
    "gpt-5.4-mini": Price(0.75, 4.50, 0.075, 0.0),
    "gpt-5.4-nano": Price(0.20, 1.25, 0.02, 0.0),
    "gpt-5.2": Price(1.75, 14.00, 0.175, 0.0),
    "gpt-5.1": Price(1.25, 10.00, 0.125, 0.0),
    "gpt-5": Price(1.25, 10.00, 0.125, 0.0),
    "gpt-5-mini": Price(0.25, 2.00, 0.025, 0.0),
    "gpt-5-nano": Price(0.05, 0.40, 0.005, 0.0),
    "gpt-4.1": Price(2.00, 8.00, 0.50, 0.0),
    "gpt-4.1-mini": Price(0.40, 1.60, 0.10, 0.0),
    "gpt-4o": Price(2.50, 10.00, 1.25, 0.0),
    "gpt-4o-mini": Price(0.15, 0.60, 0.075, 0.0),
    "o4-mini": Price(1.10, 4.40, 0.275, 0.0),
    "o3": Price(2.00, 8.00, 0.50, 0.0),
}

CUSTOM_PRICE_KEYS = ("input", "output", "cache_read", "cache_write")

# A date or snapshot on the end of a model id: claude-haiku-4-5-20251001, gpt-4o-2024-08-06.
_SNAPSHOT = re.compile(r"-(\d{8}|\d{4}-\d{2}-\d{2})$")


def base_model(model: str) -> str:
    """`model` lowercased, without a snapshot date: the name prices are listed under."""
    return _SNAPSHOT.sub("", model.lower())


def custom_price(values: Mapping) -> Price:
    """A `prices:` entry from the config file (already checked): a cache price left out is
    priced as input."""
    return Price(
        input=values["input"],
        output=values["output"],
        cache_read=values.get("cache_read", values["input"]),
        cache_write=values.get("cache_write", values["input"]),
    )


def price_for(model: str, custom: Mapping[str, Mapping] | None = None) -> tuple[Price | None, str | None]:
    """`model`'s price and where it came from ("config" or "built-in"), or (None, None).
    The config's entries win; names match ignoring case and a snapshot date."""
    name = base_model(model)
    for key, values in (custom or {}).items():
        if base_model(key) == name:
            return custom_price(values), "config"
    if name in BUILT_IN:
        return BUILT_IN[name], "built-in"
    return None, None


def call_cost(price: Price, provider: str, response: dict) -> float:
    """USD for one recorded model call."""
    prompt, output = response_tokens(provider, response)  # prompt counts cached tokens too
    read, written = response_cache_tokens(provider, response)
    if price.long_above is not None and price.long is not None and prompt > price.long_above:
        price = price.long
    uncached = max(prompt - read - written, 0)
    return (
        uncached * price.input + read * price.cache_read + written * price.cache_write + output * price.output
    ) / 1_000_000


def usd(amount: float) -> str:
    """$0.025 under a dollar (cents would hide the difference between runs), $3.12 above."""
    if amount == 0:
        return "$0"
    if amount < 0.001:
        return "< $0.001"
    return f"${amount:.3f}" if amount < 1 else f"${amount:,.2f}"
