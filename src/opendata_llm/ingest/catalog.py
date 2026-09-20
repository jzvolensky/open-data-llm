from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import Config
from ..http import HttpClient
from ..store import Catalog
from . import dcat as dcat_ingest
from . import search as search_ingest


def ingest_catalog(config: Config, catalog: Catalog, client: HttpClient) -> dict[str, Any]:
    """Fetch DCAT + Hub search records, merge them and replace the catalog tables."""
    started = datetime.now(UTC)
    dcat_records = dcat_ingest.fetch_dcat(client, config.portal.dcat_feed)
    search_records = search_ingest.fetch_search(
        client, config.portal.search_collection, config.portal.search_page_size
    )

    _snapshot(config.paths.raw, "dcat-ap-2.1.1", dcat_records)
    _snapshot(config.paths.raw, "search-items", search_records)

    by_item: dict[str, dict[str, Any]] = {}
    for record in search_records:
        if record.get("item_id"):
            by_item[record["item_id"]] = record

    datasets: dict[str, dict[str, Any]] = {}
    for record in dcat_records:
        dataset_id = record.get("dataset_id")
        if not dataset_id:
            continue
        enriched = dict(record)
        enriched["in_dcat"] = True
        enriched["in_search"] = False
        item_id = record.get("item_id")
        search = by_item.get(item_id) if item_id else None
        if search:
            apply_search(enriched, search)
        datasets[dataset_id] = enriched

    known_items = {r.get("item_id") for r in datasets.values() if r.get("item_id")}
    for search in by_item.values():
        item_id = search["item_id"]
        if item_id in known_items:
            continue
        record = {
            "dataset_id": f"arcgis:{item_id}",
            "item_id": item_id,
            "in_dcat": False,
            "in_search": True,
            "keywords": [],
        }
        apply_search(record, search)
        datasets[record["dataset_id"]] = record

    records = list(datasets.values())
    catalog.replace_catalog(records)

    finished = datetime.now(UTC)
    stats = {
        "dcat": len(dcat_records),
        "search": len(search_records),
        "merged": len(records),
        "only_dcat": sum(1 for r in records if r.get("in_dcat") and not r.get("in_search")),
        "only_search": sum(1 for r in records if r.get("in_search") and not r.get("in_dcat")),
    }
    catalog.log_run(
        run_id=started.strftime("%Y%m%dT%H%M%SZ"),
        source="catalog",
        started_at=started,
        finished_at=finished,
        status="ok",
        records=len(records),
        detail=json.dumps(stats),
    )
    return stats


def apply_search(record: dict[str, Any], search: dict[str, Any]) -> None:
    """Overlay Hub search enrichment onto a dataset record in place."""
    record["in_search"] = True
    record.setdefault("keywords", [])
    for key in (
        "license",
        "license_info",
        "categories",
        "tags",
        "item_type",
        "owner",
        "org_id",
        "source",
        "culture",
        "num_views",
        "size_bytes",
        "search_id",
    ):
        value = search.get(key)
        if value not in (None, "", []):
            record[key] = value
    if not record.get("service_url") and search.get("service_url"):
        record["service_url"] = search["service_url"]
    for key in ("title", "description", "description_html"):
        if not record.get(key) and search.get(key):
            record[key] = search[key]


def _snapshot(raw_dir: Path, name: str, payload: Any) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    (raw_dir / f"{name}.{stamp}.json").write_text(text, encoding="utf-8")
    (raw_dir / f"{name}.latest.json").write_text(text, encoding="utf-8")
