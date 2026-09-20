"""Load spatial GeoJSON distributions as DuckDB spatial views."""

from __future__ import annotations

from typing import Any

from ..store import Catalog
from .spatial import ensure_spatial

REGISTRY = "geo_tables"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {REGISTRY} (
    dataset_id VARCHAR,
    item_id VARCHAR,
    table_name VARCHAR,
    path VARCHAR,
    rows BIGINT,
    status VARCHAR,
    error VARCHAR,
    loaded_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (dataset_id)
);
"""


def ensure(con: Any) -> None:
    ensure_spatial(con)
    con.execute(SCHEMA)


def load_spatial_layers(catalog: Catalog, limit: int | None = None) -> dict[str, Any]:
    ensure(catalog.con)
    targets = catalog.con.execute(
        "SELECT DISTINCT ds.dataset_id, ds.item_id, dl.path FROM layers l "
        "JOIN datasets ds ON ds.item_id = l.item_id "
        "JOIN downloads dl ON dl.item_id = l.item_id AND upper(dl.fmt) = 'GEOJSON' "
        "WHERE l.geom_type IS NOT NULL AND dl.status = 'ok' AND dl.path IS NOT NULL "
        "ORDER BY ds.dataset_id"
    ).fetchall()
    if limit:
        targets = targets[:limit]

    ok = failed = 0
    errors: list[str] = []
    for dataset_id, item_id, path in targets:
        name = f"geo_{item_id}"
        literal = str(path).replace("'", "''")
        try:
            catalog.con.execute(f"DROP VIEW IF EXISTS {name}")  # noqa: S608
            catalog.con.execute(
                f"CREATE VIEW {name} AS SELECT * FROM ST_Read('{literal}')"  # noqa: S608
            )
            count_row = catalog.con.execute(
                f"SELECT count(*) FROM {name}"  # noqa: S608
            ).fetchone()
            rows = int(count_row[0]) if count_row else 0
            catalog.con.execute(
                f"INSERT OR REPLACE INTO {REGISTRY} "
                "(dataset_id, item_id, table_name, path, rows, status, error, loaded_at) "
                "VALUES (?, ?, ?, ?, ?, 'ok', NULL, now())",
                [dataset_id, item_id, name, str(path), rows],
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001 - recorded per dataset
            failed += 1
            errors.append(f"{dataset_id}: {type(exc).__name__}: {exc}")
            catalog.con.execute(
                f"INSERT OR REPLACE INTO {REGISTRY} "
                "(dataset_id, item_id, table_name, path, rows, status, error, loaded_at) "
                "VALUES (?, ?, ?, ?, NULL, 'failed', ?, now())",
                [dataset_id, item_id, name, str(path), f"{type(exc).__name__}: {exc}"],
            )
    return {"targets": len(targets), "ok": ok, "failed": failed, "errors_sample": errors[:5]}
