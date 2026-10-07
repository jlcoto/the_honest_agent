import json

from honest_agent.sql_capture import error_message, extract_sql_calls, single_value


def _call(tool_name, sql, *, is_error=False, generated=False, step=1, error=None, column=None, value=None) -> dict:
    return {
        "tool_name": tool_name,
        "sql": sql,
        "is_error": is_error,
        "generated": generated,
        "step": step,
        "error": error,
        "result_column": column,
        "result_value": value,
    }


def _tool_use_trace(name: str, input_: dict) -> list[dict]:
    return [
        {"role": "user", "content": "prompt"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "1", "name": name, "input": input_}]},
    ]


def test_extract_uses_declared_field_for_named_tool():
    trace = _tool_use_trace("query_warehouse", {"sql_text": "select 1", "sql": "should be ignored"})

    calls = extract_sql_calls(trace, sql_fields={"query_warehouse": "sql_text"})

    assert calls == [_call("query_warehouse", "select 1")]


def test_extract_falls_back_to_heuristic_when_tool_not_declared():
    trace = _tool_use_trace("query_warehouse", {"query": "select 2"})

    calls = extract_sql_calls(trace, sql_fields={})

    assert calls == [_call("query_warehouse", "select 2")]


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

    assert extract_sql_calls(trace) == [_call("query_semantic_view", "select 1", generated=True)]


def test_extract_prefers_input_over_result_when_both_present():
    trace = _tool_use_and_result_trace(
        "query_warehouse",
        {"sql": "select 1"},
        json.dumps({"sql": "select 2"}),
    )

    assert extract_sql_calls(trace) == [_call("query_warehouse", "select 1")]


def test_extract_declared_field_checked_on_result_side_too():
    trace = _tool_use_and_result_trace(
        "query_semantic_view",
        {"message": "..."},
        json.dumps({"generated_sql": "select 1"}),
    )

    calls = extract_sql_calls(trace, sql_fields={"query_semantic_view": "generated_sql"})

    assert calls == [_call("query_semantic_view", "select 1", generated=True)]


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
        _call("query_warehouse", "select 1"),
        _call("run_metric_query", "select 2"),
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

    assert calls == [_call("search_catalog", "select 1")]


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
        _call(
            "query_warehouse",
            "select * from orders",
            is_error=True,
            error="Object 'ORDERS' does not exist or not authorized.",
        )
    ]


def test_each_call_records_its_step():
    trace = [
        {"role": "user", "content": "prompt"},
        {"role": "assistant", "content": [{"type": "text", "text": "Let me look."}]},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "1", "name": "query", "input": {"sql": "select 1"}}],
        },
    ]

    assert [c["step"] for c in extract_sql_calls(trace)] == [2]


def test_a_one_value_result_is_kept_and_a_bigger_one_is_not():
    one = _tool_use_and_result_trace("query", {"sql": "select 1"}, "order_count\n2297")
    many = _tool_use_and_result_trace("query", {"sql": "select 1"}, json.dumps({"columns": ["a"], "rows": [[1], [2]]}))

    assert extract_sql_calls(one)[0]["result_value"] == "2297"
    assert extract_sql_calls(many)[0]["result_value"] is None


def test_single_value_reads_each_servers_format():
    snowflake = {"result_set": {"data": [["311928357.7805"]], "resultSetMetaData": {"rowType": [{"name": "TOTAL"}]}}}
    motherduck_local = {"success": True, "columns": ["count_star()"], "rows": [[0]], "rowCount": 1}
    motherduck = 'success: true\ncolumns[1]: order_count\ncolumnTypes[1]: BIGINT\nrows[1]:\n  - [1]: "0"\nrowCount: 1'

    assert single_value(json.dumps(snowflake)) == ("TOTAL", "311928357.7805")
    assert single_value(json.dumps(motherduck_local)) == ("count_star()", "0")
    assert single_value(motherduck) == ("order_count", "0")
    assert single_value("order_count\n2297") == ("order_count", "2297")
    assert single_value("columns[2]: year,revenue\nrows[1]:\n  - [2]: 1996,1") is None


def test_error_message_drops_the_mcp_wrapping():
    snowflake = (
        "MCP error calling tool query_warehouse: MCP Server tool error: SQL compilation error:\n"
        "Object 'LINEITEM' does not exist or not authorized.\nrequest-id: 1c833ee3"
    )
    motherduck = 'success: false\nerror: "Catalog Error: No catalog named \\"md:x\\" found."\nerrorType: Error'

    assert error_message(snowflake) == "Object 'LINEITEM' does not exist or not authorized."
    assert error_message(motherduck) == 'Catalog Error: No catalog named "md:x" found.'
    assert error_message("Agent error (code 399504): Access denied for trial accounts.") == (
        "Access denied for trial accounts."
    )
    assert error_message("Error calling tool 'execute_query': The --read-only flag needs a token.") == (
        "The --read-only flag needs a token."
    )
