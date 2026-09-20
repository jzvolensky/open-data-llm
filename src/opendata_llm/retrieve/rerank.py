"""Optional cross-encoder reranking (bge-reranker-v2-m3).

Requires the ``rerank`` extra: ``uv sync --extra rerank``.
"""

from __future__ import annotations

from typing import Any


class CrossEncoderReranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        from sentence_transformers import CrossEncoder

        self.model: Any = CrossEncoder(model_name)

    def rerank(
        self, query: str, documents: list[str]
    ) -> list[tuple[int, float]]:
        if not documents:
            return []
        pairs = [(query, doc) for doc in documents]
        scores = self.model.predict(pairs)
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
        return [(idx, float(score)) for idx, score in ranked]


_RERANKERS: dict[str, CrossEncoderReranker] = {}


def get_reranker(model_name: str = "BAAI/bge-reranker-v2-m3") -> CrossEncoderReranker:
    """Return a process-wide cached reranker (loading one is several seconds)."""
    reranker = _RERANKERS.get(model_name)
    if reranker is None:
        reranker = CrossEncoderReranker(model_name)
        _RERANKERS[model_name] = reranker
    return reranker
