"""Expose downloaded CSV distributions as DuckDB tables/views."""

from __future__ import annotations

import json
from typing import Any

import duckdb

from ..store import Catalog

REGISTRY = "data_tables"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {REGISTRY} (
    dataset_id VARCHAR,
    item_id VARCHAR,
    table_name VARCHAR,
    path VARCHAR,
    fmt VARCHAR,
    rows BIGINT,
    columns VARCHAR,
    column_types VARCHAR,
    status VARCHAR,
    error VARCHAR,
    loaded_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (dataset_id, fmt)
);
"""


def ensure(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA)


def table_name_for(item_id: str, fmt: str = "CSV") -> str:
    return f"ds_{item_id}_{fmt.lower()}"


def load_csv_tables(
    catalog: Catalog,
    limit: int | None = None,
    materialize: bool = False,
) -> dict[str, Any]:
    ensure(catalog.con)
    targets = catalog.con.execute(
        "SELECT d.dataset_id, d.item_id, dl.path FROM distributions d "
        "JOIN downloads dl ON dl.item_id = d.item_id AND dl.fmt = d.fmt "
        "WHERE d.fmt = 'CSV' AND dl.status = 'ok' AND dl.path IS NOT NULL "
        "ORDER BY d.dataset_id"
    ).fetchall()
    if limit:
        targets = targets[:limit]

    ok = failed = 0
    errors: list[str] = []
    for dataset_id, item_id, path in targets:
        if not item_id:
            continue
        name = table_name_for(item_id)
        kind = "TABLE" if materialize else "VIEW"
        literal = str(path).replace("'", "''")
        try:
            catalog.con.execute(f"DROP {kind} IF EXISTS {name}")  # noqa: S608
            catalog.con.execute(
                f"CREATE {kind} {name} AS "  # noqa: S608
                f"SELECT * FROM read_csv_auto('{literal}', ignore_errors=true)"
            )
            described = catalog.con.execute(f"DESCRIBE {name}").fetchall()  # noqa: S608
            columns = [row[0] for row in described]
            types = [row[1] for row in described]
            count_row = catalog.con.execute(f"SELECT count(*) FROM {name}").fetchone()  # noqa: S608
            rows = int(count_row[0]) if count_row else 0
            catalog.con.execute(
                f"INSERT OR REPLACE INTO {REGISTRY} "
                "(dataset_id, item_id, table_name, path, fmt, rows, columns, "
                "column_types, status, error, loaded_at) "
                "VALUES (?, ?, ?, ?, 'CSV', ?, ?, ?, 'ok', NULL, now())",
                [
                    dataset_id,
                    item_id,
                    name,
                    str(path),
                    rows,
                    json.dumps(columns),
                    json.dumps(types),
                ],
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001 - recorded per dataset
            failed += 1
            errors.append(f"{dataset_id}: {type(exc).__name__}: {exc}")
            catalog.con.execute(
                f"INSERT OR REPLACE INTO {REGISTRY} "
                "(dataset_id, item_id, table_name, path, fmt, rows, columns, "
                "column_types, status, error, loaded_at) "
                "VALUES (?, ?, ?, ?, 'CSV', NULL, NULL, NULL, 'failed', ?, now())",
                [dataset_id, item_id, name, str(path), f"{type(exc).__name__}: {exc}"],
            )
    return {"targets": len(targets), "ok": ok, "failed": failed, "errors_sample": errors[:5]}


def list_tables(catalog: Catalog) -> list[dict[str, Any]]:
    ensure(catalog.con)
    rows = catalog.con.execute(
        f"SELECT dataset_id, table_name, rows, status FROM {REGISTRY} ORDER BY rows DESC NULLS LAST"
    ).fetchall()
    return [
        {"dataset_id": r[0], "table_name": r[1], "rows": r[2], "status": r[3]} for r in rows
    ]
