from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ..config import Config
from ..http import HttpClient
from ..store import Catalog


def feature_root(service_url: str) -> str:
    """Normalise a FeatureServer/layer URL down to its service root."""
    url = service_url.rstrip("/")
    parts = url.split("/")
    if parts and parts[-1].isdigit():
        url = "/".join(parts[:-1])
    return url


def fetch_service_layers(
    client: HttpClient, service_url: str
) -> list[tuple[int, dict[str, Any], list[dict[str, Any]]]]:
    root = feature_root(service_url)
    meta = client.get_json(root, params={"f": "json"})
    layers = (meta.get("layers") or []) + (meta.get("tables") or [])
    out: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []
    for layer in layers:
        layer_id = layer.get("id")
        if layer_id is None:
            continue
        detail = client.get_json(f"{root}/{layer_id}", params={"f": "json"})
        out.append((layer_id, detail, detail.get("fields") or []))
    return out


def ingest_features(
    config: Config,
    catalog: Catalog,
    client: HttpClient,
    limit: int | None = None,
    concurrency: int | None = None,
) -> dict[str, Any]:
    targets = catalog.datasets_missing_layers(limit=limit)
    workers = concurrency or config.ingest.feature_concurrency
    delay = config.ingest.feature_request_delay
    ok = failed = 0
    errors: list[str] = []

    def work(target: dict[str, str]) -> tuple[str, list[Any] | None, str | None]:
        if delay:
            time.sleep(delay)
        try:
            layers = fetch_service_layers(client, target["service_url"])
            return target["item_id"], layers, None
        except Exception as exc:  # noqa: BLE001 - collected per dataset
            return target["item_id"], None, f"{type(exc).__name__}: {exc}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work, target) for target in targets]
        for future in as_completed(futures):
            item_id, layers, error = future.result()
            if layers is None:
                failed += 1
                errors.append(f"{item_id}: {error}")
                continue
            catalog.replace_layers(item_id, layers)
            ok += 1

    return {"targets": len(targets), "ok": ok, "failed": failed, "errors_sample": errors[:10]}
