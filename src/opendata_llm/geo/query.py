"""Spatial queries over the gazetteer and loaded layers."""

from __future__ import annotations

from typing import Any

from ..store import Catalog
from .layers import REGISTRY
from .spatial import ensure_spatial


def list_places(catalog: Catalog) -> list[dict[str, Any]]:
    ensure_spatial(catalog.con)
    rows = catalog.con.execute(
        "SELECT slug, name, ST_Area(geom) AS area FROM geo_places "
        "WHERE slug IS NOT NULL ORDER BY name"
    ).fetchall()
    return [{"slug": r[0], "name": r[1], "area": r[2]} for r in rows]


def district_at(catalog: Catalog, lon: float, lat: float) -> dict[str, Any] | None:
    ensure_spatial(catalog.con)
    row = catalog.con.execute(
        "SELECT slug, name FROM geo_places "
        "WHERE ST_Contains(geom, ST_Point(?, ?)) "
        "ORDER BY (slug = 'bratislava') LIMIT 1",
        [lon, lat],
    ).fetchone()
    return {"slug": row[0], "name": row[1]} if row else None


def datasets_in_district(catalog: Catalog, slug: str, limit: int = 20) -> list[dict[str, Any]]:
    ensure_spatial(catalog.con)
    results: dict[str, dict[str, Any]] = {}

    try:
        tables = catalog.con.execute(
            f"SELECT gt.dataset_id, gt.table_name, ds.title FROM {REGISTRY} gt "  # noqa: S608
            "JOIN datasets ds USING (dataset_id) WHERE gt.status = 'ok'"
        ).fetchall()
    except Exception:  # noqa: BLE001 - spatial layers may not be loaded
        tables = []
    for dataset_id, table_name, title in tables:
        try:
            row = catalog.con.execute(
                f"SELECT count(*) FROM {table_name} t, "  # noqa: S608
                "(SELECT geom AS g FROM geo_places WHERE slug = ?) p "
                "WHERE t.geom IS NOT NULL AND ST_Intersects(t.geom, p.g)",
                [slug],
            ).fetchone()
        except Exception:  # noqa: BLE001 - skip unreadable layers
            continue
        if row and row[0]:
            results[dataset_id] = {
                "dataset_id": dataset_id,
                "title": title,
                "source": "geometry",
                "matches": int(row[0]),
            }

    try:
        text_rows = catalog.con.execute(
            "SELECT ds.dataset_id, ds.title FROM dataset_places dp "
            "JOIN datasets ds USING (dataset_id) WHERE dp.slug = ? LIMIT ?",
            [slug, limit],
        ).fetchall()
    except Exception:  # noqa: BLE001 - gazetteer may not be built yet
        text_rows = []
    for dataset_id, title in text_rows:
        results.setdefault(
            dataset_id, {"dataset_id": dataset_id, "title": title, "source": "text"}
        )
    return list(results.values())[:limit]


def datasets_at_point(
    catalog: Catalog, lon: float, lat: float, limit: int = 20
) -> list[dict[str, Any]]:
    ensure_spatial(catalog.con)
    try:
        tables = catalog.con.execute(
            f"SELECT gt.dataset_id, gt.table_name, ds.title "  # noqa: S608
            f"FROM {REGISTRY} gt JOIN datasets ds USING (dataset_id) WHERE gt.status = 'ok'"
        ).fetchall()
    except Exception:  # noqa: BLE001 - registry may not exist yet
        return []

    hits: list[dict[str, Any]] = []
    for dataset_id, table_name, title in tables:
        try:
            count_row = catalog.con.execute(
                f"SELECT count(*) FROM {table_name} "  # noqa: S608
                "WHERE geom IS NOT NULL AND ST_Within(ST_Point(?, ?), geom)",
                [lon, lat],
            ).fetchone()
        except Exception:  # noqa: BLE001 - skip unreadable layers
            continue
        if count_row and count_row[0]:
            hits.append(
                {
                    "dataset_id": dataset_id,
                    "title": title,
                    "matches": int(count_row[0]),
                }
            )
        if len(hits) >= limit:
            break
    return hits
