from __future__ import annotations

from typing import Any

from ..http import HttpClient
from ..text import (
    as_list,
    extract_item_id,
    first,
    language_code,
    parse_dt,
    scalar,
    strip_html,
)

DATA_FORMATS = {"CSV", "GEOJSON", "KML", "XLSX", "TXT", "ZIP", "GPKG", "GDB", "SHP"}


def fetch_dcat(client: HttpClient, feed_path: str) -> list[dict[str, Any]]:
    feed = client.get_json(feed_path)
    return [parse_dataset(item) for item in feed.get("dcat:dataset", [])]


def parse_dataset(item: dict[str, Any]) -> dict[str, Any]:
    identifier = scalar(item.get("dct:identifier"))
    item_id = extract_item_id(identifier)
    dcat_id = item.get("@id")
    slug = dcat_id.split("::", 1)[1] if isinstance(dcat_id, str) and "::" in dcat_id else None

    contact = item.get("dcat:contactPoint") or {}
    publisher = scalar((item.get("dct:publisher") or {}).get("foaf:name"))

    description_html = scalar(item.get("dct:description"))
    keywords_value = scalar(item.get("dcat:keyword"))
    keywords = keywords_value if isinstance(keywords_value, list) else as_list(keywords_value)

    spatial_wkt = None
    spatial = item.get("dct:spatial")
    if isinstance(spatial, dict):
        spatial_wkt = first(scalar(spatial.get("dct:bbox")))

    distributions = _parse_distributions(item)
    service_url = next(
        (
            d["access_url"]
            for d in distributions
            if "FeatureServer" in (d.get("access_url") or "")
        ),
        None,
    )

    dataset_id = dcat_id or (f"arcgis:{item_id}" if item_id else None)
    return {
        "dataset_id": dataset_id,
        "item_id": item_id,
        "dcat_id": dcat_id,
        "slug": slug,
        "title": scalar(item.get("dct:title")),
        "description": strip_html(description_html),
        "description_html": description_html if isinstance(description_html, str) else None,
        "publisher": publisher,
        "contact_name": scalar(contact.get("vcard:fn")) if isinstance(contact, dict) else None,
        "contact_email": scalar(contact.get("vcard:hasEmail"))
        if isinstance(contact, dict)
        else None,
        "theme": scalar((item.get("dcat:theme") or {}).get("skos:prefLabel"))
        if isinstance(item.get("dcat:theme"), dict)
        else scalar(item.get("dcat:theme")),
        "access_rights": scalar(item.get("dct:accessRights")),
        "language": language_code(scalar(item.get("dct:language"))),
        "issued": parse_dt(scalar(item.get("dct:issued"))),
        "modified": parse_dt(scalar(item.get("dct:modified"))),
        "spatial_wkt": spatial_wkt,
        "keywords": [str(k) for k in keywords if k],
        "distributions": distributions,
        "service_url": service_url,
        "hub_url": dcat_id,
        "in_dcat": True,
    }


def _parse_distributions(item: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, dist in enumerate(as_list(item.get("dcat:distribution"))):
        if not isinstance(dist, dict):
            continue
        format_uri = scalar(dist.get("dct:format"))
        fmt = format_uri.rsplit("/", 1)[-1].upper() if isinstance(format_uri, str) else None
        out.append(
            {
                "idx": idx,
                "title": scalar(dist.get("dct:title")),
                "fmt": fmt,
                "format_uri": format_uri,
                "description": strip_html(scalar(dist.get("dct:description"))),
                "access_url": scalar(dist.get("dcat:accessURL")),
                "download_url": scalar(dist.get("dcat:downloadURL")),
                "is_download": fmt in DATA_FORMATS,
            }
        )
    return out
