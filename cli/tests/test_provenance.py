from honest_agent.provenance import Source, check_provenance


def test_no_expected_sources_is_trivially_satisfied():
    assert check_provenance().score == 1.0
    assert check_provenance(sql_statements=["select * from anything"]).score == 1.0


def test_source_found_in_sql_scores_full():
    score = check_provenance(
        sql_statements=["select * from analytics.fct_orders"],
        expected_sources=["fct_orders"],
    ).score
    assert score == 1.0


def test_source_missing_from_sql_scores_zero():
    score = check_provenance(
        sql_statements=["select * from raw_orders"],
        expected_sources=["fct_orders"],
    ).score
    assert score == 0.0


def test_no_sql_statements_scores_zero():
    score = check_provenance(sql_statements=[], expected_sources=["fct_orders"]).score
    assert score == 0.0


def test_source_check_respects_word_boundaries():
    """Querying `customer_fct_orders_summary` shouldn't count as evidence the
    agent used `fct_orders` -- the check must not just be a bare substring
    match, or an agent hitting the wrong table with a similar name would
    incorrectly pass.
    """
    score = check_provenance(
        sql_statements=["select * from customer_fct_orders_summary"],
        expected_sources=["fct_orders"],
    ).score
    assert score == 0.0


def test_source_check_is_case_insensitive():
    score = check_provenance(
        sql_statements=["select * from FCT_ORDERS"],
        expected_sources=["fct_orders"],
    ).score
    assert score == 1.0


def test_partial_source_overlap():
    score = check_provenance(
        sql_statements=["select * from fct_orders"],
        expected_sources=["fct_orders", "agg_daily_revenue"],
    ).score
    assert score == 0.5


def test_expected_database_requires_qualified_match():
    """A same-named table in the wrong database (e.g. Snowflake's own
    built-in snowflake_sample_data instead of the real target) must not
    count as a source-check hit once expected_database is declared.
    """
    score = check_provenance(
        sql_statements=["select * from snowflake_sample_data.tpch_sf1.orders"],
        expected_sources=["orders"],
        expected_database="agent_quiz_demo",
    ).score
    assert score == 0.0


def test_expected_database_passes_for_inline_qualified_match():
    score = check_provenance(
        sql_statements=["select * from agent_quiz_demo.public.orders"],
        expected_sources=["orders"],
        expected_database="agent_quiz_demo",
        expected_schema="public",
    ).score
    assert score == 1.0


def test_expected_database_resolves_bare_table_via_preceding_use_statements():
    """`use database`/`use schema` in an earlier tool call must carry
    forward to resolve a later, unqualified table reference -- exactly the
    pattern Snowflake supports natively.
    """
    score = check_provenance(
        sql_statements=[
            "use database agent_quiz_demo",
            "use schema public",
            "select * from orders",
        ],
        expected_sources=["orders"],
        expected_database="agent_quiz_demo",
        expected_schema="public",
    ).score
    assert score == 1.0


def test_expected_schema_alone_ignores_database():
    """Declaring only expected_schema shouldn't require a database match --
    each of expected_database/expected_schema is independently optional."""
    score = check_provenance(
        sql_statements=["select * from some_other_db.public.orders"],
        expected_sources=["orders"],
        expected_schema="public",
    ).score
    assert score == 1.0


def test_expected_database_wrong_use_statement_fails():
    score = check_provenance(
        sql_statements=[
            "use database snowflake_sample_data",
            "select * from orders",
        ],
        expected_sources=["orders"],
        expected_database="agent_quiz_demo",
    ).score
    assert score == 0.0


def test_a_name_in_a_comment_or_string_is_not_a_source():
    score = check_provenance(
        sql_statements=["select 'fct_orders' as label from raw_orders -- should have used fct_orders"],
        expected_sources=["fct_orders"],
    ).score
    assert score == 0.0


def test_a_cte_named_like_the_source_is_not_the_source():
    """`orders` here is the CTE; the table read is raw.tpch.lineitem."""
    score = check_provenance(
        sql_statements=["with orders as (select * from raw.tpch.lineitem) select count(*) from orders"],
        expected_sources=["orders"],
    ).score
    assert score == 0.0


def test_a_source_read_inside_a_cte_counts():
    score = check_provenance(
        sql_statements=["with yearly as (select * from agent_quiz_demo.public.fct_orders) select * from yearly"],
        expected_sources=["fct_orders"],
        expected_database="agent_quiz_demo",
    ).score
    assert score == 1.0


def test_describing_or_showing_a_source_is_not_reading_it():
    """Only statements that read data count: exploring the right table and then
    querying another one hasn't used it."""
    score = check_provenance(
        sql_statements=[
            "show tables",
            "describe table agent_quiz_demo.public.fct_orders",
            "select * from raw_orders",
        ],
        expected_sources=["fct_orders"],
    ).score
    assert score == 0.0


def test_quoted_identifiers_are_read_like_unquoted_ones():
    score = check_provenance(
        sql_statements=['select * from "AGENT_QUIZ_DEMO"."PUBLIC"."FCT_ORDERS"'],
        expected_sources=["fct_orders"],
        expected_database="agent_quiz_demo",
        expected_schema="public",
    ).score
    assert score == 1.0


def test_use_schema_with_a_database_sets_both():
    score = check_provenance(
        sql_statements=["use schema agent_quiz_demo.public", "select * from orders"],
        expected_sources=["orders"],
        expected_database="agent_quiz_demo",
        expected_schema="public",
    ).score
    assert score == 1.0


def test_bare_use_sets_the_database_or_database_and_schema():
    """Snowflake's `use x` is `use database x`; `use x.y` sets both."""
    assert (
        check_provenance(
            ["use agent_quiz_demo.public", "select * from orders"], ["agent_quiz_demo.public.orders"]
        ).score
        == 1.0
    )
    assert (
        check_provenance(
            ["use agent_quiz_demo", "select * from public.orders"], ["agent_quiz_demo.public.orders"]
        ).score
        == 1.0
    )


def test_use_warehouse_or_role_changes_nothing():
    score = check_provenance(
        sql_statements=["use database agent_quiz_demo", "use warehouse compute_wh", "select * from orders"],
        expected_sources=["orders"],
        expected_database="agent_quiz_demo",
    ).score
    assert score == 1.0


def test_an_expected_source_can_name_its_own_location():
    """Entries read like table names in SQL; their own parts beat the eval-wide
    expected_database/expected_schema, which fill in the parts they leave out."""
    sql = [
        "select * from agent_quiz_demo.public.fct_revenue r"
        " join snowflake_sample_data.tpch_sf1.customer c on true"
        " join agent_quiz_demo.staging.customer_flags f on true"
    ]
    provenance = check_provenance(
        sql_statements=sql,
        expected_sources=["fct_revenue", "snowflake_sample_data.tpch_sf1.customer", "staging.customer_flags"],
        expected_database="agent_quiz_demo",
        expected_schema="public",
    )
    assert provenance.score == 1.0


def test_a_qualified_expected_source_in_the_wrong_place_misses():
    score = check_provenance(
        sql_statements=["select * from snowflake_sample_data.tpch_sf1.orders"],
        expected_sources=["agent_quiz_demo.public.orders"],
    ).score
    assert score == 0.0


def test_a_bare_name_with_no_use_does_not_match_an_expected_database():
    """Its database is unknown, not "any": Snowflake's MCP server has no default
    database, so a bare `orders` fails to compile there rather than reading
    agent_quiz_demo.public.orders."""
    score = check_provenance(
        sql_statements=["select * from orders"],
        expected_sources=["orders"],
        expected_database="agent_quiz_demo",
    ).score
    assert score == 0.0


def test_queried_sources_lists_every_table_read_once_with_its_location():
    provenance = check_provenance(
        sql_statements=[
            "select * from snowflake_sample_data.tpch_sf1.lineitem l"
            " join snowflake_sample_data.tpch_sf1.orders o on true",
            "use database agent_quiz_demo",
            "select * from public.orders union all select * from snowflake_sample_data.tpch_sf1.orders",
            "select * from SEMANTIC_VIEW(AGENT_QUIZ_DEMO.PUBLIC.TPCH_SEMANTIC_VIEW METRICS total_revenue)",
            "select 1 from lineitem",
        ],
    )
    assert provenance.queried_sources == [
        Source("snowflake_sample_data", "tpch_sf1", "lineitem"),
        Source("snowflake_sample_data", "tpch_sf1", "orders"),
        Source("agent_quiz_demo", "public", "orders"),
        Source("AGENT_QUIZ_DEMO", "PUBLIC", "TPCH_SEMANTIC_VIEW"),
        Source("agent_quiz_demo", None, "lineitem"),
    ]


def test_sql_that_does_not_parse_is_reported_and_reads_nothing():
    provenance = check_provenance(
        sql_statements=["select from where fct_orders ((", "select * from fct_orders"],
        expected_sources=["fct_orders"],
    )
    assert provenance.unparsed == ["select from where fct_orders (("]
    assert provenance.score == 1.0
