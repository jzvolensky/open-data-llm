"""Hybrid retrieval: dense vectors + BM25 + concept matching fused with RRF."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import Config
from ..index.embed import OllamaEmbedder
from ..index.store import SearchIndex
from ..semantic import vocab
from ..store import Catalog


@dataclass
class SearchResult:
    dataset_id: str
    score: float
    title: str | None = None
    item_type: str | None = None
    license: str | None = None
    concepts: list[str] = field(default_factory=list)
    url: str | None = None
    card: str | None = None

    def concept_labels(self, lang: str = "sk") -> list[str]:
        return [vocab.label_for(c, lang) for c in self.concepts]


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]], k: int = 60
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, dataset_id in enumerate(ranked, start=1):
            scores[dataset_id] = scores.get(dataset_id, 0.0) + 1.0 / (k + rank)
    return scores


class HybridRetriever:
    def __init__(
        self,
        catalog: Catalog,
        index: SearchIndex,
        embedder: OllamaEmbedder,
        config: Config,
    ) -> None:
        self.catalog = catalog
        self.index = index
        self.embedder = embedder
        self.config = config
        self._reranker: Any | None = None

    def search(
        self,
        query: str,
        top_k: int | None = None,
        candidates: int | None = None,
        rerank: bool | None = None,
    ) -> list[SearchResult]:
        top_k = top_k or self.config.search.top_k
        candidates = candidates or self.config.search.candidates

        ranked_lists: list[list[str]] = [
            [ds for ds, _ in self.index.vector_search(self.embedder.embed([query])[0], candidates)],
            [ds for ds, _ in self.index.bm25_search(query, candidates)],
        ]
        concept_ids = sorted(vocab.concepts_in(query))
        if concept_ids:
            ranked_lists.append(
                [ds for ds, _ in self.index.concept_search(concept_ids, candidates)]
            )
        place_ranked = self._place_candidates(sorted(vocab.places_in(query)), candidates)
        if place_ranked:
            ranked_lists.append(place_ranked)

        fused = reciprocal_rank_fusion(ranked_lists, self.config.search.rrf_k)
        ordered = [ds for ds, _ in sorted(fused.items(), key=lambda item: -item[1])]
        if not ordered:
            return []

        meta = self._hydrate(ordered[:candidates])
        results: list[SearchResult] = []
        for dataset_id in ordered:
            entry = meta.get(dataset_id)
            if not entry:
                continue
            card = self.index.card(dataset_id)
            results.append(
                SearchResult(
                    dataset_id=dataset_id,
                    score=fused[dataset_id],
                    title=entry["title"],
                    item_type=entry["item_type"],
                    license=entry["license"],
                    concepts=entry["concepts"],
                    url=entry["url"],
                    card=card,
                )
            )

        use_rerank = self.config.search.rerank if rerank is None else rerank
        if use_rerank and len(results) > 1:
            results = self._apply_rerank(query, results)
        return results[:top_k]

    def _place_candidates(self, slugs: list[str], limit: int) -> list[str]:
        if not slugs:
            return []
        try:
            placeholders = ", ".join("?" for _ in slugs)
            rows = self.catalog.con.execute(
                "SELECT dataset_id, count(*) AS c FROM dataset_places "
                f"WHERE slug IN ({placeholders}) "  # noqa: S608 - placeholders only
                "GROUP BY dataset_id ORDER BY c DESC LIMIT ?",
                [*slugs, limit],
            ).fetchall()
            return [r[0] for r in rows]
        except Exception:  # noqa: BLE001 - gazetteer is optional
            return []

    def _apply_rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        from .rerank import get_reranker

        if self._reranker is None:
            self._reranker = get_reranker(self.config.search.rerank_model)
        documents = [r.card or r.title or "" for r in results]
        order = self._reranker.rerank(query, documents)
        reranked: list[SearchResult] = []
        for idx, score in order:
            result = results[idx]
            result.score = score
            reranked.append(result)
        return reranked

    def _hydrate(self, dataset_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not dataset_ids:
            return {}
        placeholders = ", ".join("?" for _ in dataset_ids)
        rows = self.catalog.con.execute(
            "SELECT dataset_id, title, item_type, license, dcat_id, service_url "
            f"FROM datasets WHERE dataset_id IN ({placeholders})",  # noqa: S608
            dataset_ids,
        ).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for dataset_id, title, item_type, license_, dcat_id, service_url in rows:
            out[dataset_id] = {
                "title": title,
                "item_type": item_type,
                "license": license_,
                "url": dcat_id or service_url,
                "concepts": [],
            }
        try:
            concept_rows = self.catalog.con.execute(
                "SELECT dataset_id, concept_id FROM dataset_concepts "
                f"WHERE dataset_id IN ({placeholders})",  # noqa: S608
                dataset_ids,
            ).fetchall()
            for dataset_id, concept_id in concept_rows:
                if dataset_id in out:
                    out[dataset_id]["concepts"].append(concept_id)
        except Exception:  # noqa: BLE001 - concepts are optional
            pass
        return out
