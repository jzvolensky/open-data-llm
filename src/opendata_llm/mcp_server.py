"""MCP server exposing the Bratislava open data tools."""

from __future__ import annotations

from typing import Any

from .config import Config
from .geo.query import datasets_at_point, datasets_in_district
from .index.embed import OllamaEmbedder
from .index.store import SearchIndex
from .query.sql import run_sql
from .retrieve.hybrid import HybridRetriever
from .semantic import vocab
from .store import Catalog


def create_server(config_path: str | None = None) -> Any:
    from mcp.server.mcpserver import MCPServer

    config = Config.load(config_path)
    server = MCPServer("bratislava-open-data")

    def _search(query: str, top_k: int, rerank: bool) -> list[dict[str, Any]]:
        catalog = Catalog(config.paths.db)
        embedder = OllamaEmbedder(
            model=config.embeddings.model,
            host=config.embeddings.host,
            timeout=config.embeddings.timeout,
            batch_size=config.embeddings.batch_size,
        )
        try:
            index = SearchIndex(catalog.con, config.embeddings.dim)
            retriever = HybridRetriever(catalog, index, embedder, config)
            results = retriever.search(query, top_k=top_k, rerank=rerank)
        finally:
            embedder.close()
            catalog.close()
        return [
            {
                "dataset_id": r.dataset_id,
                "title": r.title,
                "url": r.url,
                "license": r.license,
                "score": r.score,
            }
            for r in results
        ]

    @server.tool()
    def search_datasets(query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic search for datasets on data.bratislava.sk."""
        return _search(query, top_k, rerank=config.search.rerank)

    @server.tool()
    def get_dataset(dataset_id: str) -> dict[str, Any]:
        """Return metadata and distributions for a dataset."""
        catalog = Catalog(config.paths.db)
        try:
            row = catalog.con.execute(
                "SELECT title, description, publisher, license, dcat_id, service_url, "
                "modified FROM datasets WHERE dataset_id = ?",
                [dataset_id],
            ).fetchone()
            if not row:
                return {"error": "not found"}
            distributions = catalog.con.execute(
                "SELECT fmt, access_url FROM distributions WHERE dataset_id = ?",
                [dataset_id],
            ).fetchall()
            columns, rows = run_sql(
                catalog.con,
                "SELECT table_name, rows FROM data_tables WHERE dataset_id = ?",
                max_rows=5,
            )
            return {
                "dataset_id": dataset_id,
                "title": row[0],
                "description": row[1],
                "publisher": row[2],
                "license": row[3],
                "url": row[4] or row[5],
                "modified": str(row[6]) if row[6] else None,
                "distributions": [{"format": d[0], "url": d[1]} for d in distributions],
                "cached_tables": {r[0]: r[1] for r in rows},
            }
        finally:
            catalog.close()

    @server.tool()
    def query_sql(sql: str, max_rows: int = 50) -> dict[str, Any]:
        """Run a read-only SQL query over the catalog and cached data tables."""
        catalog = Catalog(config.paths.db)
        try:
            columns, rows = run_sql(catalog.con, sql, max_rows=max_rows)
            return {"columns": columns, "rows": [list(r) for r in rows]}
        finally:
            catalog.close()

    @server.tool()
    def district_datasets(place: str, limit: int = 15) -> list[dict[str, Any]]:
        """Datasets covering a Bratislava district (by geometry or text)."""
        catalog = Catalog(config.paths.db)
        try:
            slug = vocab.place_slug(place) or place.lower()
            return datasets_in_district(catalog, slug, limit=limit)
        finally:
            catalog.close()

    @server.tool()
    def point_datasets(lon: float, lat: float, limit: int = 15) -> list[dict[str, Any]]:
        """Spatial datasets containing a coordinate."""
        catalog = Catalog(config.paths.db)
        try:
            return datasets_at_point(catalog, lon, lat, limit=limit)
        finally:
            catalog.close()

    return server


def main() -> None:
    create_server().run()
