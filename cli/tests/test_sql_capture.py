import json

from honest_agent.sql_capture import extract_sql_calls


def _tool_use_trace(name: str, input_: dict) -> list[dict]:
    return [
        {"role": "user", "content": "prompt"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "1", "name": name, "input": input_}]},
    ]


def test_extract_uses_declared_field_for_named_tool():
    trace = _tool_use_trace("query_warehouse", {"sql_text": "select 1", "sql": "should be ignored"})

    calls = extract_sql_calls(trace, sql_fields={"query_warehouse": "sql_text"})

    assert calls == [{"tool_name": "query_warehouse", "sql": "select 1", "is_error": False, "generated": False}]


def test_extract_falls_back_to_heuristic_when_tool_not_declared():
    trace = _tool_use_trace("query_warehouse", {"query": "select 2"})

    calls = extract_sql_calls(trace, sql_fields={})

    assert calls == [{"tool_name": "query_warehouse", "sql": "select 2", "is_error": False, "generated": False}]


def test_extract_skips_tools_with_no_matching_field():
    trace = _tool_use_trace("calculator", {"expression": "1+1"})

    assert extract_sql_calls(trace) == []


def test_extract_skips_non_string_and_empty_values():
    trace = _tool_use_trace("query_warehouse", {"sql": "   "})

    assert extract_sql_calls(trace) == []


def test_extract_ignores_text_blocks_and_non_tool_messages():
    trace = [
        {"role": "user", "content": "prompt"},
        {"role": "assistant", "content": [{"type": "text", "text": "thinking..."}]},
    ]

    assert extract_sql_calls(trace) == []


def _tool_use_and_result_trace(name: str, input_: dict, result_content) -> list[dict]:
    return [
        {"role": "user", "content": "prompt"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "call_1", "name": name, "input": input_}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": result_content}],
        },
    ]


def test_extract_falls_back_to_result_content_when_input_has_no_sql():
    """Some tools (e.g. Snowflake's Cortex Analyst) take a natural-language
    message as input -- no SQL there -- and return the generated SQL inside
    the result instead."""
    trace = _tool_use_and_result_trace(
        "query_semantic_view",
        {"message": "What was total revenue in 1996?"},
        json.dumps([{"text": "interpretation..."}, {"statement": "select 1", "confidence": {}}]),
    )

    assert extract_sql_calls(trace) == [
        {"tool_name": "query_semantic_view", "sql": "select 1", "is_error": False, "generated": True}
    ]


def test_extract_prefers_input_over_result_when_both_present():
    trace = _tool_use_and_result_trace(
        "query_warehouse",
        {"sql": "select 1"},
        json.dumps({"sql": "select 2"}),
    )

    assert extract_sql_calls(trace) == [
        {"tool_name": "query_warehouse", "sql": "select 1", "is_error": False, "generated": False}
    ]


def test_extract_declared_field_checked_on_result_side_too():
    trace = _tool_use_and_result_trace(
        "query_semantic_view",
        {"message": "..."},
        json.dumps({"generated_sql": "select 1"}),
    )

    calls = extract_sql_calls(trace, sql_fields={"query_semantic_view": "generated_sql"})

    assert calls == [{"tool_name": "query_semantic_view", "sql": "select 1", "is_error": False, "generated": True}]


def test_extract_ignores_non_json_result_content():
    trace = _tool_use_and_result_trace("calculator", {"expression": "1+1"}, "2")

    assert extract_sql_calls(trace) == []


def test_extract_ignores_result_with_no_matching_field():
    trace = _tool_use_and_result_trace(
        "query_semantic_view",
        {"message": "..."},
        json.dumps({"answer": "42", "confidence": {}}),
    )

    assert extract_sql_calls(trace) == []


def test_extract_collects_multiple_calls_in_order_with_tool_names():
    trace = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "1", "name": "query_warehouse", "input": {"query": "select 1"}},
                {"type": "tool_use", "id": "2", "name": "run_metric_query", "input": {"statement": "select 2"}},
            ],
        }
    ]

    assert extract_sql_calls(trace) == [
        {"tool_name": "query_warehouse", "sql": "select 1", "is_error": False, "generated": False},
        {"tool_name": "run_metric_query", "sql": "select 2", "is_error": False, "generated": False},
    ]


def test_extract_skips_built_in_non_sql_tools():
    # MotherDuck's hosted server: `search_catalog`'s `query` is a search term.
    trace = _tool_use_trace("search_catalog", {"query": "orders"})

    assert extract_sql_calls(trace) == []


def test_extract_skips_tools_the_eval_ignores():
    trace = _tool_use_trace("find_tables", {"query": "orders"})

    assert extract_sql_calls(trace, ignore_tools=["find_tables"]) == []


def test_declaring_a_tool_in_sql_fields_beats_ignoring_it():
    trace = _tool_use_trace("search_catalog", {"query": "select 1"})

    calls = extract_sql_calls(trace, sql_fields={"search_catalog": "query"}, ignore_tools=["search_catalog"])

    assert calls == [{"tool_name": "search_catalog", "sql": "select 1", "is_error": False, "generated": False}]


def test_extract_marks_calls_whose_result_was_an_error():
    trace = [
        {"role": "user", "content": "prompt"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "1", "name": "query_warehouse", "input": {"sql": "select * from orders"}}
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "1",
                    "content": "SQL compilation error: Object 'ORDERS' does not exist or not authorized.",
                    "is_error": True,
                }
            ],
        },
    ]

    assert extract_sql_calls(trace) == [
        {"tool_name": "query_warehouse", "sql": "select * from orders", "is_error": True, "generated": False}
    ]
