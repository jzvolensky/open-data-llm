from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..config import Config
from ..http import DownloadTooLargeError, HttpClient
from ..store import Catalog

EXTENSIONS = {
    "CSV": "csv",
    "GEOJSON": "geojson",
    "KML": "kml",
    "XLSX": "xlsx",
    "TXT": "txt",
    "ZIP": "zip",
    "GPKG": "gpkg",
    "GDB": "zip",
}


def _dest_name(fmt: str, access_url: str) -> str:
    """Filename for a distribution, disambiguating multi-layer items."""
    ext = EXTENSIONS.get(fmt, fmt.lower())
    layers = parse_qs(urlparse(access_url).query).get("layers") or []
    layer = layers[0] if layers else None
    suffix = f"_l{layer}" if layer and layer != "0" else ""
    return f"data{suffix}.{ext}"


def download_datasets(
    config: Config,
    catalog: Catalog,
    client: HttpClient,
    item_ids: list[str] | None = None,
    formats: list[str] | None = None,
    max_bytes: int | None = None,
    limit: int | None = None,
    concurrency: int = 6,
) -> dict[str, int]:
    formats = formats or config.download.data_formats
    max_bytes = max_bytes if max_bytes is not None else config.download.max_bytes
    targets = catalog.list_download_targets(formats, item_ids, limit)
    downloads_dir = Path(config.paths.downloads)

    def work(target: dict[str, Any]) -> dict[str, Any]:
        item_id = target["item_id"]
        fmt = (target["fmt"] or "bin").upper()
        dest = downloads_dir / item_id / _dest_name(fmt, target["access_url"])
        if dest.exists() and dest.stat().st_size > 0:
            return {
                "item_id": item_id,
                "url": target["access_url"],
                "fmt": fmt,
                "path": str(dest),
                "size": dest.stat().st_size,
                "status": "ok",
                "error": None,
            }
        try:
            size = client.download(target["access_url"], dest, max_bytes=max_bytes)
            return {
                "item_id": item_id,
                "url": target["access_url"],
                "fmt": fmt,
                "path": str(dest),
                "size": size,
                "status": "ok",
                "error": None,
            }
        except DownloadTooLargeError as exc:
            return {
                "item_id": item_id,
                "url": target["access_url"],
                "fmt": fmt,
                "path": None,
                "size": None,
                "status": "skipped",
                "error": str(exc),
            }
        except Exception as exc:  # noqa: BLE001 - recorded per download
            return {
                "item_id": item_id,
                "url": target["access_url"],
                "fmt": fmt,
                "path": None,
                "size": None,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }

    counts: dict[str, int] = {"targets": len(targets), "ok": 0, "skipped": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(work, target) for target in targets]
        for future in as_completed(futures):
            result = future.result()
            counts[result["status"]] += 1
            catalog.record_download(
                result["item_id"],
                result["url"],
                result["fmt"],
                result["path"],
                result["size"],
                result["status"],
                result["error"],
            )
    return counts
