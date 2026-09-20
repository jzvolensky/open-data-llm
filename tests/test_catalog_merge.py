from __future__ import annotations

from opendata_llm.ingest.catalog import apply_search


def test_apply_search_overlays_enrichment() -> None:
    record = {
        "dataset_id": "https://data.bratislava.sk/datasets/MagBa::demo",
        "item_id": "abc",
        "title": "DCAT title",
        "keywords": [],
    }
    search = {
        "item_id": "abc",
        "search_id": "abc",
        "license": "CC-BY-4.0",
        "categories": ["/Categories/Doprava a komunikácie"],
        "tags": ["Doprava"],
        "num_views": 123,
        "title": "Search title",
    }
    apply_search(record, search)
    assert record["in_search"] is True
    assert record["license"] == "CC-BY-4.0"
    assert record["categories"] == ["/Categories/Doprava a komunikácie"]
    assert record["num_views"] == 123
    # DCAT title is canonical and must not be overwritten
    assert record["title"] == "DCAT title"


def test_apply_search_fills_missing_title() -> None:
    record = {"dataset_id": "arcgis:abc", "item_id": "abc", "keywords": []}
    apply_search(record, {"item_id": "abc", "search_id": "abc", "title": "From search"})
    assert record["title"] == "From search"
