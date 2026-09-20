"""District gazetteer: fetch Bratislava district polygons and link datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import Config
from ..http import HttpClient
from ..semantic import vocab
from ..store import Catalog
from .spatial import ensure_spatial

DISTRICT_DATASET_TITLE = "Mestská časť"


def build_gazetteer(
    config: Config, catalog: Catalog, client: HttpClient
) -> dict[str, Any]:
    con = catalog.con
    ensure_spatial(con)
    row = con.execute(
        "SELECT service_url FROM datasets WHERE title = ? LIMIT 1",
        [DISTRICT_DATASET_TITLE],
    ).fetchone()
    if not row or not row[0]:
        raise RuntimeError(f"district dataset {DISTRICT_DATASET_TITLE!r} not in catalog")
    layer = row[0].rstrip("/")
    if not layer.split("/")[-1].isdigit():
        layer = f"{layer}/0"

    payload = client.get_json(
        f"{layer}/query",
        params={
            "where": "1=1",
            "outFields": "NAZOV_UTJ,MC",
            "returnGeometry": "true",
            "outSR": 4326,
            "f": "geojson",
        },
    )
    geo_dir = Path(config.paths.raw) / "geo"
    geo_dir.mkdir(parents=True, exist_ok=True)
    path = geo_dir / "mestske-casti.geojson"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    con.execute(
        "CREATE OR REPLACE TABLE geo_places ("
        "slug VARCHAR, name VARCHAR, mc VARCHAR, geom GEOMETRY)"
    )
    con.execute(
        "INSERT INTO geo_places "
        "SELECT NULL, NAZOV_UTJ, MC, geom FROM ST_Read(?)",
        [str(path)],
    )
    for (name,) in con.execute("SELECT name FROM geo_places").fetchall():
        slug = vocab.place_slug(name)
        con.execute("UPDATE geo_places SET slug = ? WHERE name = ?", [slug, name])
    con.execute(
        "INSERT INTO geo_places "
        "SELECT 'bratislava', 'Bratislava', NULL, ST_Union_Agg(geom) FROM geo_places"
    )

    linked = link_dataset_places(catalog)
    count = con.execute("SELECT count(*) FROM geo_places").fetchone()
    return {
        "districts": int(count[0]) if count else 0,
        "datasets_linked": linked,
        "geojson": str(path),
    }


def link_dataset_places(catalog: Catalog) -> int:
    """Associate datasets with districts mentioned in their title/description."""
    con = catalog.con
    con.execute(
        "CREATE OR REPLACE TABLE dataset_places ("
        "dataset_id VARCHAR, slug VARCHAR, source VARCHAR, "
        "PRIMARY KEY (dataset_id, slug, source))"
    )
    rows = con.execute(
        "SELECT dataset_id, title, description FROM datasets"
    ).fetchall()
    inserted = 0
    for dataset_id, title, description in rows:
        text = f"{title or ''} {description or ''}"
        for slug in vocab.places_in(text):
            con.execute(
                "INSERT OR IGNORE INTO dataset_places VALUES (?, ?, 'text')",
                [dataset_id, slug],
            )
            inserted += 1
    return inserted
