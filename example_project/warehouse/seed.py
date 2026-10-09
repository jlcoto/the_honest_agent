"""Seeds example_project/warehouse.duckdb from DuckDB's own built-in TPC-H
generator -- a real, standard, multi-table schema (customer/orders/lineitem/
part/partsupp/supplier/nation/region, with actual foreign-key relationships)
instead of a hand-rolled flat table, so provenance checking has genuine
joins/aggregation to get right or wrong, not just "which single table."

Deterministic: `dbgen(sf=...)` is itself fully deterministic for a given
scale factor (that's the whole point of a benchmark generator -- no random
seed needed here, unlike a hand-rolled generator). TPC-H's own order dates
always fall in 1992-01-01..1998-08-02 regardless of when this is actually
run, which is why the eval YAML asks about a fixed historical year (1996)
rather than anything relative to "today".

Run with: uv run python warehouse/seed.py
"""

from __future__ import annotations

from pathlib import Path

import duckdb

DB_PATH = Path(__file__).parent.parent / "warehouse.duckdb"

# ~15k orders / ~60k lineitem rows -- enough for a real join+aggregation to
# mean something, small enough that every query here runs in well under a
# second and an agent's tool calls never risk dumping a huge result set.
SCALE_FACTOR = 0.01


def main() -> None:
    DB_PATH.unlink(missing_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute("install tpch")
        con.execute("load tpch")
        con.execute(f"call dbgen(sf={SCALE_FACTOR})")

        print(f"Seeded {DB_PATH} from TPC-H dbgen(sf={SCALE_FACTOR}).")
        print("Tables:")
        for (name,) in con.execute("show tables").fetchall():
            count = con.execute(f"select count(*) from {name}").fetchone()[0]
            print(f"  - {name} ({count} rows)")

        revenue_1996 = con.execute(
            "select round(sum(l_extendedprice * (1 - l_discount)), 2) from orders "
            "join lineitem on o_orderkey = l_orderkey where extract(year from o_orderdate) = 1996"
        ).fetchone()[0]
        order_count_1996 = con.execute(
            "select count(*) from orders where extract(year from o_orderdate) = 1996"
        ).fetchone()[0]
        print(f"1996 revenue: {revenue_1996}")
        print(f"1996 order count: {order_count_1996}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
