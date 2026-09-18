from agent_quiz_cli.provenance import score_provenance


def test_no_expected_sources_is_trivially_satisfied():
    assert score_provenance() == 1.0
    assert score_provenance(sql_statements=["SELECT * FROM anything"]) == 1.0


def test_source_found_in_sql_scores_full():
    score = score_provenance(
        sql_statements=["SELECT * FROM analytics.fct_orders"],
        expected_sources=["fct_orders"],
    )
    assert score == 1.0


def test_source_missing_from_sql_scores_zero():
    score = score_provenance(
        sql_statements=["SELECT * FROM raw_orders"],
        expected_sources=["fct_orders"],
    )
    assert score == 0.0


def test_no_sql_statements_scores_zero():
    score = score_provenance(sql_statements=[], expected_sources=["fct_orders"])
    assert score == 0.0


def test_source_check_respects_word_boundaries():
    """Querying `customer_fct_orders_summary` shouldn't count as evidence the
    agent used `fct_orders` -- the check must not just be a bare substring
    match, or an agent hitting the wrong table with a similar name would
    incorrectly pass.
    """
    score = score_provenance(
        sql_statements=["SELECT * FROM customer_fct_orders_summary"],
        expected_sources=["fct_orders"],
    )
    assert score == 0.0


def test_source_check_is_case_insensitive():
    score = score_provenance(
        sql_statements=["SELECT * FROM FCT_ORDERS"],
        expected_sources=["fct_orders"],
    )
    assert score == 1.0


def test_partial_source_overlap():
    score = score_provenance(
        sql_statements=["SELECT * FROM fct_orders"],
        expected_sources=["fct_orders", "agg_daily_revenue"],
    )
    assert score == 0.5


def test_expected_database_requires_qualified_match():
    """A same-named table in the wrong database (e.g. Snowflake's own
    built-in snowflake_sample_data instead of the real target) must not
    count as a source-check hit once expected_database is declared.
    """
    score = score_provenance(
        sql_statements=["SELECT * FROM snowflake_sample_data.tpch_sf1.orders"],
        expected_sources=["orders"],
        expected_database="agent_quiz_demo",
    )
    assert score == 0.0


def test_expected_database_passes_for_inline_qualified_match():
    score = score_provenance(
        sql_statements=["SELECT * FROM agent_quiz_demo.public.orders"],
        expected_sources=["orders"],
        expected_database="agent_quiz_demo",
        expected_schema="public",
    )
    assert score == 1.0


def test_expected_database_resolves_bare_table_via_preceding_use_statements():
    """`use database`/`use schema` in an earlier tool call must carry
    forward to resolve a later, unqualified table reference -- exactly the
    pattern Snowflake supports natively.
    """
    score = score_provenance(
        sql_statements=[
            "use database agent_quiz_demo",
            "use schema public",
            "SELECT * FROM orders",
        ],
        expected_sources=["orders"],
        expected_database="agent_quiz_demo",
        expected_schema="public",
    )
    assert score == 1.0


def test_expected_schema_alone_ignores_database():
    """Declaring only expected_schema shouldn't require a database match --
    each of expected_database/expected_schema is independently optional."""
    score = score_provenance(
        sql_statements=["SELECT * FROM some_other_db.public.orders"],
        expected_sources=["orders"],
        expected_schema="public",
    )
    assert score == 1.0


def test_expected_database_wrong_use_statement_fails():
    score = score_provenance(
        sql_statements=[
            "use database snowflake_sample_data",
            "SELECT * FROM orders",
        ],
        expected_sources=["orders"],
        expected_database="agent_quiz_demo",
    )
    assert score == 0.0
