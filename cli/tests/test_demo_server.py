from pathlib import Path

import duckdb
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from honest_agent.demo_server import DESCRIPTION, MAX_ROWS, run_query


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "warehouse.duckdb"
    con = duckdb.connect(str(path))
    con.execute("create table orders as select range as o_orderkey from range(300)")
    con.close()
    return path


def test_a_query_returns_rows(database: Path):
    assert run_query(database, "select count(*) as n from orders") == "n\n300"


def test_results_are_capped(database: Path):
    lines = run_query(database, "select o_orderkey from orders").splitlines()

    assert len(lines) == 1 + MAX_ROWS + 1  # header, rows, the truncation note
    assert "truncated" in lines[-1]


@pytest.mark.parametrize("sql", ["select * from missing_table", "create table t (a int)"])
def test_failures_raise_so_mcp_flags_them_as_errors(database: Path, sql: str):
    with pytest.raises(ToolError, match="error running query"):
        run_query(database, sql)


def test_a_missing_database_raises(tmp_path: Path):
    with pytest.raises(ToolError, match="not found"):
        run_query(tmp_path / "nope.duckdb", "select 1")


def test_the_description_names_no_tables():
    assert "orders" not in DESCRIPTION and "lineitem" not in DESCRIPTION
