"""Dataset knowledge graph.

Nodes are datasets and the entities around them (concepts, publishers,
formats, places). Edges come from the DCAT metadata, the controlled
vocabulary, curated Hub ``related`` links and nearest-neighbour similarity.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import duckdb

from ..http import HttpClient
from . import vocab

SCHEMA = """
CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id VARCHAR PRIMARY KEY,
    node_type VARCHAR,
    label VARCHAR
);
CREATE TABLE IF NOT EXISTS graph_edges (
    src VARCHAR,
    dst VARCHAR,
    rel VARCHAR,
    weight DOUBLE DEFAULT 1.0,
    PRIMARY KEY (src, dst, rel)
);
CREATE TABLE IF NOT EXISTS dataset_concepts (
    dataset_id VARCHAR,
    concept_id VARCHAR,
    source VARCHAR,
    score DOUBLE,
    PRIMARY KEY (dataset_id, concept_id, source)
);
"""

SOURCE_SCORE = {"category": 1.0, "keyword": 0.9, "tag": 0.8, "text": 0.4}


class Graph:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self.con = con
        self.con.execute(SCHEMA)

    # -- low level ---------------------------------------------------------
    def clear(self) -> None:
        for table in ("graph_nodes", "graph_edges", "dataset_concepts"):
            self.con.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed names

    def add_node(self, node_id: str, node_type: str, label: str | None = None) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO graph_nodes VALUES (?, ?, ?)",
            [node_id, node_type, label or node_id],
        )

    def add_edge(self, src: str, dst: str, rel: str, weight: float = 1.0) -> None:
        if src == dst:
            return
        if rel in ("similar", "related") and src > dst:
            src, dst = dst, src
        self.con.execute(
            "INSERT OR REPLACE INTO graph_edges VALUES (?, ?, ?, ?)",
            [src, dst, rel, weight],
        )

    # -- build -------------------------------------------------------------
    def build(
        self,
        client: HttpClient | None = None,
        search_collection: str = "dataset",
        with_related: bool = False,
        top_k: int = 10,
        concurrency: int = 6,
    ) -> dict[str, int]:
        self.clear()
        datasets = self.con.execute(
            "SELECT dataset_id, item_id, title, publisher, description, "
            "keywords, categories, tags FROM datasets"
        ).fetchall()

        concept_datasets: dict[str, list[str]] = defaultdict(list)
        concept_rows: list[tuple[str, str, str, float]] = []

        for dataset_id, _item_id, title, publisher, description, kw, cats, tags in datasets:
            self.add_node(dataset_id, "dataset", title)
            if publisher:
                pub_id = f"publisher:{publisher}"
                self.add_node(pub_id, "publisher", publisher)
                self.add_edge(dataset_id, pub_id, "published_by")

            per_concept: dict[str, float] = {}
            for cat in _loads(cats):
                cid = vocab.category_concept(cat) or vocab.canonicalize(cat)
                if cid:
                    _bump(per_concept, cid, "category", concept_rows, dataset_id)
            for kwd in _loads(kw):
                cid = vocab.canonicalize(kwd)
                if cid:
                    _bump(per_concept, cid, "keyword", concept_rows, dataset_id)
            for tag in _loads(tags):
                cid = vocab.canonicalize(tag)
                if cid:
                    _bump(per_concept, cid, "tag", concept_rows, dataset_id)
            text = f"{title or ''} {description or ''}"
            for cid in vocab.concepts_in(text):
                _bump(per_concept, cid, "text", concept_rows, dataset_id)
            for place in vocab.places_in(text):
                place_id = f"place:{place}"
                self.add_node(place_id, "place", vocab.PLACES[place])
                self.add_edge(dataset_id, place_id, "covers_place")

            for cid, score in per_concept.items():
                self.add_node(f"concept:{cid}", "concept", vocab.label_for(cid))
                self.add_edge(dataset_id, f"concept:{cid}", "about", score)
                concept_datasets[cid].append(dataset_id)

        for row in concept_rows:
            self.con.execute(
                "INSERT OR REPLACE INTO dataset_concepts VALUES (?, ?, ?, ?)", list(row)
            )

        for fmt, dataset_id in self.con.execute(
            "SELECT DISTINCT fmt, dataset_id FROM distributions WHERE fmt IS NOT NULL"
        ).fetchall():
            fmt_id = f"format:{fmt}"
            self.add_node(fmt_id, "format", fmt)
            self.add_edge(dataset_id, fmt_id, "available_as")

        similar = self._similarity_edges(concept_datasets, top_k)
        related = 0
        if with_related and client is not None:
            related = self._related_edges(datasets, client, search_collection, concurrency)

        def one(sql: str) -> int:
            row = self.con.execute(sql).fetchone()
            return int(row[0]) if row else 0

        return {
            "datasets": len(datasets),
            "nodes": one("SELECT count(*) FROM graph_nodes"),
            "edges": one("SELECT count(*) FROM graph_edges"),
            "similar_edges": similar,
            "related_edges": related,
        }

    def _similarity_edges(
        self, concept_datasets: dict[str, list[str]], top_k: int
    ) -> int:
        total = max(1, len({d for ds in concept_datasets.values() for d in ds}))
        pair_weight: dict[tuple[str, str], float] = defaultdict(float)
        for datasets in concept_datasets.values():
            if len(datasets) < 2 or len(datasets) > 0.6 * total:
                continue
            weight = math.log(1 + total / len(datasets))
            for i in range(len(datasets)):
                for j in range(i + 1, len(datasets)):
                    a, b = sorted((datasets[i], datasets[j]))
                    pair_weight[(a, b)] += weight

        neighbours: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for (a, b), weight in pair_weight.items():
            neighbours[a].append((weight, b))
            neighbours[b].append((weight, a))

        count = 0
        for dataset_id, items in neighbours.items():
            items.sort(reverse=True)
            for weight, other in items[:top_k]:
                self.add_edge(dataset_id, other, "similar", round(weight, 4))
                count += 1
        return count

    def _related_edges(
        self,
        datasets: list[tuple[Any, ...]],
        client: HttpClient,
        collection: str,
        concurrency: int,
    ) -> int:
        item_to_datasets: dict[str, list[str]] = defaultdict(list)
        for dataset_id, item_id, *_ in datasets:
            if item_id:
                item_to_datasets[item_id].append(dataset_id)

        def fetch(item_id: str) -> tuple[str, list[str]]:
            try:
                page = client.get_json(
                    f"/api/search/v1/collections/{collection}/items/{item_id}/related",
                    params={"limit": 20},
                )
            except Exception:  # noqa: BLE001 - best effort enrichment
                return item_id, []
            related = []
            for feature in page.get("features") or []:
                rid = (feature.get("id") or "").split("_", 1)[0]
                if rid:
                    related.append(rid)
            return item_id, related

        count = 0
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(fetch, item_id) for item_id in item_to_datasets]
            for future in as_completed(futures):
                item_id, related_items = future.result()
                for other_item in related_items:
                    for src in item_to_datasets.get(item_id, []):
                        for dst in item_to_datasets.get(other_item, []):
                            if src != dst:
                                self.add_edge(src, dst, "related", 1.0)
                                count += 1
        return count

    # -- queries -----------------------------------------------------------
    def neighbours(
        self, dataset_id: str, rel: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        rel_clause = "AND e.rel = ?" if rel else ""
        params: list[Any] = [dataset_id, dataset_id, dataset_id]
        if rel:
            params.append(rel)
        params.append(limit)
        rows = self.con.execute(
            "SELECT e.rel, e.weight, n.node_id, n.node_type, n.label "
            "FROM graph_edges e JOIN graph_nodes n "
            "ON n.node_id = CASE WHEN e.src = ? THEN e.dst ELSE e.src END "
            "WHERE (e.src = ? OR e.dst = ?) " + rel_clause + " "  # noqa: S608
            "ORDER BY e.weight DESC LIMIT ?",
            params,
        ).fetchall()
        return [
            {
                "rel": r[0],
                "weight": r[1],
                "node_id": r[2],
                "node_type": r[3],
                "label": r[4],
            }
            for r in rows
        ]

    def stats(self) -> dict[str, int]:
        def one(sql: str) -> int:
            row = self.con.execute(sql).fetchone()
            return int(row[0]) if row else 0

        out = {
            "nodes": one("SELECT count(*) FROM graph_nodes"),
            "edges": one("SELECT count(*) FROM graph_edges"),
            "concept_links": one("SELECT count(*) FROM dataset_concepts"),
        }
        for rel, count in self.con.execute(
            "SELECT rel, count(*) FROM graph_edges GROUP BY rel ORDER BY 2 DESC"
        ).fetchall():
            out[f"rel:{rel}"] = int(count)
        return out


def _loads(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return [str(value)]
    if isinstance(parsed, list):
        return [str(v) for v in parsed]
    return []


def _bump(
    per_concept: dict[str, float],
    concept_id: str,
    source: str,
    rows: list[tuple[str, str, str, float]],
    dataset_id: str,
) -> None:
    score = SOURCE_SCORE[source]
    per_concept[concept_id] = max(per_concept.get(concept_id, 0.0), score)
    rows.append((dataset_id, concept_id, source, score))
