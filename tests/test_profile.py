from __future__ import annotations

from opendata_llm.query.load import ensure as ensure_data_tables
from opendata_llm.query.profile import profile_columns, values_for
from opendata_llm.store import Catalog


def _catalog(tmp_path):
    catalog = Catalog(tmp_path / "catalog.duckdb")
    ensure_data_tables(catalog.con)
    catalog.con.execute(
        "CREATE TABLE ds_demo_csv (okres VARCHAR, druh VARCHAR, amount INTEGER)"
    )
    catalog.con.execute(
        "INSERT INTO ds_demo_csv VALUES ('A', 'x', 1), ('A', 'y', 2), ('B', 'x', 3)"
    )
    catalog.con.execute(
        "INSERT INTO data_tables (dataset_id, item_id, table_name, fmt, rows, status) "
        "VALUES ('d1', 'i1', 'ds_demo_csv', 'CSV', 3, 'ok')"
    )
    return catalog


def test_profile_columns_builds_value_dictionary(tmp_path) -> None:
    catalog = _catalog(tmp_path)
    try:
        stats = profile_columns(catalog)
        assert stats["ok"] == 1
        values = values_for(catalog, "d1")
        assert set(values["okres"]) == {"A", "B"}
        assert set(values["druh"]) == {"x", "y"}
    finally:
        catalog.close()


def test_profile_columns_skips_high_cardinality(tmp_path) -> None:
    catalog = _catalog(tmp_path)
    try:
        profile_columns(catalog, max_distinct=2)
        values = values_for(catalog, "d1")
        # okres has 2 values (kept), druh has 2 (kept), amount has 3 (skipped).
        assert "amount" not in values
    finally:
        catalog.close()


def test_profile_columns_is_idempotent(tmp_path) -> None:
    catalog = _catalog(tmp_path)
    try:
        profile_columns(catalog)
        profile_columns(catalog)
        count = catalog.con.execute("SELECT count(*) FROM column_values").fetchone()
        assert count is not None and count[0] > 0
    finally:
        catalog.close()
