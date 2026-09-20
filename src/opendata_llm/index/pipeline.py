"""Orchestrate card generation, embedding and full-text index creation."""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..store import Catalog
from .cards import collect_cards
from .embed import OllamaEmbedder
from .store import SearchIndex


def build_index(config: Config, catalog: Catalog) -> dict[str, Any]:
    index = SearchIndex(catalog.con, config.embeddings.dim)
    cards = collect_cards(catalog.con)
    index.replace_cards(cards)

    embedder = OllamaEmbedder(
        model=config.embeddings.model,
        host=config.embeddings.host,
        timeout=config.embeddings.timeout,
        batch_size=config.embeddings.batch_size,
    )
    try:
        vectors = embedder.embed([text for _, text in cards])
    finally:
        embedder.close()

    rows = [
        (dataset_id, vector) for (dataset_id, _), vector in zip(cards, vectors, strict=True)
    ]
    index.replace_embeddings(rows)
    index.build_fts()

    stats: dict[str, Any] = dict(index.stats())
    stats["dim"] = config.embeddings.dim
    stats["model"] = config.embeddings.model
    return stats
