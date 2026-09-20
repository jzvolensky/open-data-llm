from __future__ import annotations

from typing import Any

from ..http import HttpClient
from ..text import strip_html


def fetch_search(
    client: HttpClient,
    collection: str,
    page_size: int = 100,
    max_passes: int = 4,
) -> list[dict[str, Any]]:
    """Page through the Hub OGC API Records collection and parse every record.

    The endpoint caps pages at 100 and its ordering is not stable between
    requests, so identical ``startindex`` values can yield overlapping pages.
    We collect the union of several passes (keyed by record id) until we have
    ``numberMatched`` unique records.
    """
    endpoint = f"/api/search/v1/collections/{collection}/items"
    collected: dict[str, dict[str, Any]] = {}
    target: int | None = None
    for _ in range(max_passes):
        start = 1
        while True:
            page = client.get_json(
                endpoint, params={"limit": page_size, "startindex": start}
            )
            features = page.get("features") or []
            for feature in features:
                record = parse_feature(feature)
                if record["search_id"]:
                    collected[record["search_id"]] = record
            matched = page.get("numberMatched")
            if matched:
                target = matched
            if not features or (target is not None and start + len(features) > target):
                break
            start += len(features)
        if target is not None and len(collected) >= target:
            break
    return list(collected.values())


def parse_feature(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties") or {}
    raw_id = feature.get("id") or props.get("id") or ""
    item_id = raw_id.split("_", 1)[0] if raw_id else None
    description_html = props.get("description")
    return {
        "item_id": item_id,
        "search_id": raw_id,
        "title": props.get("title"),
        "description": strip_html(description_html),
        "description_html": description_html if isinstance(description_html, str) else None,
        "license": props.get("license"),
        "license_info": strip_html(props.get("licenseInfo")),
        "categories": props.get("categories") or [],
        "tags": props.get("tags") or [],
        "item_type": props.get("type"),
        "owner": props.get("owner"),
        "org_id": props.get("orgId"),
        "source": props.get("source"),
        "culture": props.get("culture"),
        "num_views": props.get("numViews"),
        "size_bytes": props.get("size"),
        "service_url": props.get("url"),
        "in_search": True,
    }
