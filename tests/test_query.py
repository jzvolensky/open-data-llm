from __future__ import annotations

import duckdb
import pytest

from opendata_llm.ingest.download import _dest_name
from opendata_llm.query.sql import UnsafeQueryError, run_sql


def test_run_sql_allows_select() -> None:
    con = duckdb.connect()
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (1), (2)")
    columns, rows = run_sql(con, "SELECT x FROM t ORDER BY x")
    assert columns == ["x"]
    assert rows == [(1,), (2,)]


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO t VALUES (3)",
        "DROP TABLE t",
        "DELETE FROM t",
        "CREATE TABLE u (x INTEGER)",
    ],
)
def test_run_sql_rejects_writes(sql: str) -> None:
    con = duckdb.connect()
    con.execute("CREATE TABLE t (x INTEGER)")
    with pytest.raises(UnsafeQueryError):
        run_sql(con, sql)


def test_dest_name_disambiguates_layers() -> None:
    base = "https://data.bratislava.sk/api/download/v1/items/abc/csv?layers=0"
    layer1 = "https://data.bratislava.sk/api/download/v1/items/abc/csv?layers=1"
    assert _dest_name("CSV", base) == "data.csv"
    assert _dest_name("CSV", layer1) == "data_l1.csv"
    assert _dest_name("GEOJSON", layer1) == "data_l1.geojson"
