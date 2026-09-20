"""Minimal ArcGIS FeatureServer query client (live data access)."""

from __future__ import annotations

import json
from typing import Any

from ..http import HttpClient


def layer_url(service_url: str) -> str:
    url = service_url.rstrip("/")
    if url.split("/")[-1].isdigit():
        return url
    return f"{url}/0"


class ArcGISClient:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def count(self, service_url: str, where: str = "1=1") -> int:
        url = f"{layer_url(service_url)}/query"
        payload = self._client.get_json(
            url,
            params={"f": "json", "where": where, "returnCountOnly": "true"},
        )
        return int(payload.get("count", 0))

    def query(
        self,
        service_url: str,
        where: str = "1=1",
        out_fields: str = "*",
        limit: int = 100,
        order_by: str | None = None,
        return_geometry: bool = False,
    ) -> dict[str, Any]:
        url = f"{layer_url(service_url)}/query"
        params: dict[str, Any] = {
            "f": "json",
            "where": where,
            "outFields": out_fields,
            "returnGeometry": str(return_geometry).lower(),
            "resultRecordCount": limit,
            "outSR": 4326,
        }
        if order_by:
            params["orderByFields"] = order_by
        return self._client.get_json(url, params=params)

    def statistics(
        self,
        service_url: str,
        group_by: str,
        statistic_fields: dict[str, tuple[str, str]],
        where: str = "1=1",
        order_by: str | None = None,
    ) -> dict[str, Any]:
        url = f"{layer_url(service_url)}/query"
        out_statistics = [
            {"statisticType": kind, "onStatisticField": field, "outStatisticFieldName": alias}
            for field, (kind, alias) in statistic_fields.items()
        ]
        params: dict[str, Any] = {
            "f": "json",
            "where": where,
            "groupByFieldsForStatistics": group_by,
            "outStatistics": json.dumps(out_statistics),
            "returnGeometry": "false",
        }
        if order_by:
            params["orderByFields"] = order_by
        return self._client.get_json(url, params=params)
