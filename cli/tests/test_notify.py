from pathlib import Path

import pytest
from click.testing import CliRunner

import honest_agent.notify as notify_mod
from honest_agent.cli import main
from honest_agent.notify import alert_message
from honest_agent.storage import write_run_results
from honest_agent.thresholds import failing_rows


def _row(**overrides) -> dict:
    row = {
        "result_id": "r1",
        "run_id": "run_1",
        "run_timestamp": "2026-10-07 09:30:00",
        "eval_id": "q_revenue_1996",
        "eval_title": "Revenue in 1996",
        "accuracy_score": 1.0,
        "accuracy_min_score": 0.8,
        "provenance_score": 0.0,
        "provenance_min_score": 0.7,
        "model_name": "claude-sonnet-5",
        "agent_name": "snowflake",
    }
    row.update(overrides)
    return row


def _texts(message: dict) -> list[str]:
    """Every piece of text in a message's blocks, in order."""
    texts = []
    for block in message["blocks"]:
        if "text" in block:
            texts.append(block["text"]["text"])
        texts += [element["text"] for element in block.get("elements", [])]
    return texts


def test_alert_names_agent_model_run_time_and_scores():
    rows = [_row(), _row(result_id="r2", eval_id="q_ok", provenance_score=1.0, run_timestamp="2026-10-07 09:31:00")]

    message = alert_message(rows, failing_rows(rows))

    assert message["text"] == "1 of 2 evals below threshold for snowflake (claude-sonnet-5)"
    assert _texts(message) == [
        "🔴 1 of 2 evals below threshold",
        "*snowflake* · claude-sonnet-5 · run started 2026-10-07 09:30 UTC",
        "*Revenue in 1996*  `q_revenue_1996`\nAccuracy *1.00* (min 0.8)  ·  Provenance *0.00* (min 0.7)",
        "Details: `honest-agent report` · honest-agent",
    ]


def test_alert_leaves_out_unchecked_provenance():
    rows = [_row(accuracy_score=0.0, provenance_score=None)]

    assert _texts(alert_message(rows, failing_rows(rows)))[2].endswith("\nAccuracy *0.00* (min 0.8)")


def test_alert_links_each_failure_to_the_report():
    rows = [_row(result_id="r 1", eval_title=None)]

    texts = _texts(alert_message(rows, failing_rows(rows), "https://example.com/report/"))

    assert texts[2].startswith("*<https://example.com/report/?result=r%201|q_revenue_1996>*")
    assert texts[-1] == "<https://example.com/report/|Open the report> · honest-agent"


def test_result_links_keep_an_existing_query_and_drop_a_fragment():
    rows = [_row()]

    text = _texts(alert_message(rows, failing_rows(rows), "https://host/evals/?team=data#/compare"))[2]

    assert text.startswith("*<https://host/evals/?team=data&result=r1|Revenue in 1996>*")


def test_alert_lists_at_most_20_failures():
    rows = [_row(result_id=f"r{i}", eval_id=f"q{i}") for i in range(25)]

    message = alert_message(rows, failing_rows(rows))

    assert len(message["blocks"]) <= 50
    assert "…and 5 more" in _texts(message)


def test_alert_escapes_text_from_eval_files():
    rows = [_row(eval_id="<!channel>", eval_title="A & <http://evil|B>", agent_name="<b>")]

    message = alert_message(rows, failing_rows(rows))
    text = "\n".join([message["text"], *_texts(message)])

    assert "<!channel>" not in text and "<http://evil" not in text and "<b>" not in text
    assert "*A &amp; &lt;http://evil|B&gt;*  `&lt;!channel&gt;`" in text


@pytest.fixture
def two_agents(in_tmp_dir: Path, monkeypatch) -> list[dict]:
    """Snowflake fails, then motherduck passes later; returns the messages posted to Slack."""
    write_run_results("results.duckdb", "run_1", [_row()])
    later = _row(result_id="r2", run_id="run_2", run_timestamp="2026-10-07 10:00:00", agent_name="motherduck_dev")
    write_run_results("results.duckdb", "run_2", [{**later, "provenance_score": 1.0}])
    Path("honest_agent_config.yml").write_text(
        "results_path: results.duckdb\n"
        "default_target: snowflake\n"
        "targets:\n"
        "  snowflake: {mcp_url: http://sf}\n"
        "  motherduck: {mcp_url: http://md, agent_name: motherduck_dev}\n"
    )
    posted: list[dict] = []
    monkeypatch.setattr(notify_mod, "_post_to_slack", lambda url, message: posted.append(message))
    return posted


def test_notify_alerts_on_the_default_targets_latest_run_even_if_another_ran_later(two_agents):
    result = CliRunner().invoke(main, ["notify", "--webhook-url", "http://hook"])

    assert result.exit_code == 0, result.output
    assert len(two_agents) == 1
    assert two_agents[0]["text"].endswith("for snowflake (claude-sonnet-5)")


def test_notify_target_uses_its_agent_name(two_agents):
    result = CliRunner().invoke(main, ["notify", "--target", "motherduck", "--webhook-url", "http://hook"])

    assert result.exit_code == 0, result.output
    assert two_agents == []
    assert "No evals below threshold in the latest run for agent motherduck_dev" in result.output


def test_notify_unknown_target_is_an_error(two_agents):
    result = CliRunner().invoke(main, ["notify", "--target", "nope", "--webhook-url", "http://hook"])

    assert result.exit_code != 0
    assert "No target 'nope'" in result.output


def test_motherduck_results_need_the_results_token(in_tmp_dir, monkeypatch):
    monkeypatch.delenv("HONEST_AGENT_RESULTS_TOKEN", raising=False)

    result = CliRunner().invoke(main, ["notify", "--results-path", "md:results", "--webhook-url", "http://hook"])

    assert result.exit_code != 0
    assert "HONEST_AGENT_RESULTS_TOKEN is not set" in result.output


def test_a_token_in_a_motherduck_results_path_is_refused(in_tmp_dir, monkeypatch):
    monkeypatch.setenv("HONEST_AGENT_RESULTS_TOKEN", "x")
    path = "md:results?motherduck_token=secret"

    result = CliRunner().invoke(main, ["notify", "--results-path", path, "--webhook-url", "http://hook"])

    assert result.exit_code != 0
    assert "Don't put a token in results_path" in result.output
