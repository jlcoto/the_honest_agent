"""Estimated cost: the price table, prices from the config file, and the cost of a call."""

from __future__ import annotations

from pathlib import Path

import pytest

from honest_agent.config_file import ConfigError, load_config
from honest_agent.llm import ANTHROPIC, OPENAI
from honest_agent.prices import BUILT_IN, PRICES_AS_OF, Price, call_cost, price_for, usd
from honest_agent.runner import cost_line, saved_prices


def _claude(uncached=0, read=0, written=0, output=0):
    return {
        "usage": {
            "input_tokens": uncached,
            "cache_read_input_tokens": read,
            "cache_creation_input_tokens": written,
            "output_tokens": output,
        }
    }


def test_each_kind_of_token_has_its_own_price():
    haiku = BUILT_IN["claude-haiku-5-5"]
    cost = call_cost(haiku, ANTHROPIC, _claude(uncached=8_000, read=30_000, written=4_000, output=600))
    # 8k × $0.10 + 30k × $0.01 + 4k × $0.125 + 600 × $0.50, per million
    assert cost == pytest.approx(0.0019)


def test_a_long_prompt_is_priced_at_the_long_rate_all_of_it():
    haiku = BUILT_IN["claude-haiku-5-5"]
    short = call_cost(haiku, ANTHROPIC, _claude(uncached=40_000, read=60_000))  # 100k: not over
    long = call_cost(haiku, ANTHROPIC, _claude(uncached=40_000, read=60_001))
    assert short == pytest.approx((40_000 * 0.10 + 60_000 * 0.01) / 1e6)
    assert long == pytest.approx((40_000 * 0.50 + 60_001 * 0.05) / 1e6)


def test_openai_cached_tokens_are_taken_out_of_input_before_pricing():
    luna = BUILT_IN["gpt-6-luna"]
    usage = {"prompt_tokens": 16_100, "completion_tokens": 50, "prompt_tokens_details": {"cached_tokens": 14_000}}
    assert call_cost(luna, OPENAI, {"usage": usage}) == pytest.approx((2_100 * 0.10 + 14_000 * 0.01 + 50 * 0.50) / 1e6)


def test_a_model_id_with_a_date_gets_its_base_models_price():
    assert price_for("claude-haiku-4-5-20251001") == (BUILT_IN["claude-haiku-4-5"], "built-in")
    assert price_for("GPT-4o-2024-08-06")[0] == BUILT_IN["gpt-4o"]
    assert price_for("my-proxy-model") == (None, None)


def test_the_config_file_adds_models_and_overrides_the_table():
    custom = {"my-proxy-model": {"input": 3.0, "output": 15.0}, "Claude-Sonnet-5-5": {"input": 1.8, "output": 9.0}}

    proxy, source = price_for("my-proxy-model", custom)
    assert source == "config"
    assert proxy == Price(3.0, 15.0, 3.0, 3.0)  # cache prices left out: priced as input
    assert price_for("claude-sonnet-5-5", custom) == (Price(1.8, 9.0, 1.8, 1.8), "config")
    assert price_for("claude-haiku-5-5", custom)[1] == "built-in"


def test_prices_in_the_config_file_are_checked(tmp_path: Path):
    path = tmp_path / "honest_agent_config.yml"
    path.write_text("prices:\n  my-proxy-model: {input: 3, output: 15, cache_read: 0.3}\n")
    assert load_config(path).prices == {"my-proxy-model": {"input": 3.0, "output": 15.0, "cache_read": 0.3}}

    for body, message in [
        ("prices:\n  m: {input: 3}\n", "prices.m in honest_agent_config.yml needs output"),
        ("prices:\n  m: {input: 3, output: 15, cached: 1}\n", "Unknown setting(s) in prices.m"),
        ("prices:\n  m: {input: '3', output: 15}\n", "input in prices.m in honest_agent_config.yml must be a number"),
        ("prices:\n  m: {input: -1, output: 15}\n", "must be a number of dollars per million tokens; got -1"),
        ("prices: [m]\n", "prices in honest_agent_config.yml must map model names"),
    ]:
        path.write_text(body)
        with pytest.raises(ConfigError, match=message.replace("(", r"\(").replace(")", r"\)")):
            load_config(path)


def test_a_run_saves_the_prices_of_its_models_and_none_for_a_model_without_one():
    saved = saved_prices("claude-haiku-5-5", "my-proxy-model", None)

    assert saved["as_of"] == PRICES_AS_OF
    assert saved["models"]["claude-haiku-5-5"]["input"] == 0.10
    assert saved["models"]["claude-haiku-5-5"]["source"] == "built-in"
    assert saved["models"]["my-proxy-model"] is None


def _rows(agent, grading):
    return [{"agent_cost_usd": a, "grading_cost_usd": g} for a, g in zip(agent, grading, strict=True)]


def test_the_cost_line_shows_agent_and_grading_apart():
    line = cost_line(_rows([0.005, 0.0026], [0.009, 0.0086]), "claude-haiku-5-5", "claude-sonnet-5-5")
    assert line == "Estimated cost: $0.025 (agent $0.008 · grading $0.018)"


def test_a_model_without_a_price_is_named_never_counted_as_zero():
    rows = _rows([0.008], [None])
    assert cost_line(rows, "claude-haiku-5-5", "my-proxy-model") == (
        "Estimated cost: $0.008 for the agent · no price for the grading model my-proxy-model; "
        "add it under prices: in honest_agent_config.yml"
    )
    assert cost_line(_rows([None], [0.01]), "my-proxy-model", "claude-sonnet-5-5").startswith(
        "Estimated cost: $0.010 for grading · no price for the agent's model my-proxy-model"
    )
    assert cost_line(_rows([None], [None]), "a", "b") == (
        "Estimated cost: unknown (no prices for a or b); add them under prices: in honest_agent_config.yml"
    )


def test_amounts_keep_three_decimals_under_a_dollar():
    assert [usd(x) for x in (0, 0.0004, 0.0252, 0.999, 3.124, 1234.5)] == [
        "$0",
        "< $0.001",
        "$0.025",
        "$0.999",
        "$3.12",
        "$1,234.50",
    ]
