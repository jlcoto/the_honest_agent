import asyncio

import pytest

from honest_agent.sql_guard import ReadOnlySQL, refusal


@pytest.mark.parametrize(
    "sql",
    [
        "select count(*) from orders",
        "with recent as (select * from orders where o_orderdate > '1998-01-01') select count(*) from recent",
        "select 1 union all select 2",
        "show tables",
        "show semantic views",
        "describe table orders",
        "use database warehouse",
        "select * from information_schema.tables",
        "",
    ],
)
def test_reads_are_allowed(sql: str):
    assert refusal(sql) is None


@pytest.mark.parametrize(
    ("sql", "kind"),
    [
        ("insert into orders values (1)", "INSERT"),
        ("update orders set o_totalprice = 0", "UPDATE"),
        ("delete from orders", "DELETE"),
        ("truncate table orders", "TRUNCATE"),
        ("drop table orders", "DROP"),
        ("create table t as select 1", "CREATE"),
        ("alter table orders add column x int", "ALTER"),
        ("merge into t using s on t.a = s.a when matched then delete", "MERGE"),
        ("grant select on orders to role analyst", "GRANT"),
        ("copy (select 1) to 'out.csv'", "COPY"),
        ("call cleanup()", "CALL"),
        ("execute immediate 'drop table orders'", "EXECUTE"),
        ("explain analyze delete from orders", "EXPLAIN"),
        ("select * into backup from orders", "SELECT ... INTO"),
        ("select 1; drop table orders", "DROP"),
    ],
)
def test_anything_else_is_refused_and_named(sql: str, kind: str):
    reason = refusal(sql)

    assert reason is not None and f"a {kind} statement" in reason


def test_sql_that_cannot_be_parsed_is_refused():
    assert "couldn't be parsed" in refusal("export database 'dir'")


class _FakeMCP:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return "ran"


def _call(guard: ReadOnlySQL, name: str, arguments: dict):
    return asyncio.run(guard.call_tool(name, arguments))


def test_a_refused_call_never_reaches_the_server_and_comes_back_as_an_error():
    server = _FakeMCP()

    result = _call(ReadOnlySQL(server, {}, []), "query_warehouse", {"sql": "delete from orders"})

    assert server.calls == []
    assert result.is_error and "a DELETE statement" in result.content[0].text


def test_reads_and_tools_without_sql_go_through():
    server = _FakeMCP()
    guard = ReadOnlySQL(server, {}, ["search_docs"])

    assert _call(guard, "query_warehouse", {"sql": "select 1"}) == "ran"
    assert _call(guard, "list_tables", {"schema": "main"}) == "ran"  # no SQL field
    assert _call(guard, "search_docs", {"query": "delete old rows"}) == "ran"  # ignore_tools: not SQL
    assert len(server.calls) == 3


def test_a_declared_sql_field_is_checked_too():
    server = _FakeMCP()

    result = _call(ReadOnlySQL(server, {"run_it": "text"}, []), "run_it", {"text": "drop table orders"})

    assert result.is_error and server.calls == []
