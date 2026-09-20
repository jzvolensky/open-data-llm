"""Evaluate hybrid retrieval against a small bilingual gold question set."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Config
from ..index.embed import OllamaEmbedder
from ..index.store import SearchIndex
from ..retrieve.hybrid import HybridRetriever, SearchResult
from ..store import Catalog

DEFAULT_QUESTIONS = Path(__file__).with_name("questions.jsonl")


@dataclass
class Question:
    id: str
    lang: str
    query: str
    expect: list[str]


def load_questions(path: str | Path | None = None) -> list[Question]:
    path = Path(path) if path else DEFAULT_QUESTIONS
    questions: list[Question] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        questions.append(
            Question(
                id=payload["id"],
                lang=payload.get("lang", "sk"),
                query=payload["query"],
                expect=[e.lower() for e in payload.get("expect", [])],
            )
        )
    return questions


def is_relevant(result: SearchResult, expect: list[str]) -> bool:
    title = (result.title or "").lower()
    return any(needle in title for needle in expect)


def evaluate(
    config: Config,
    catalog: Catalog,
    questions: list[Question],
    top_k: int | None = None,
    candidates: int | None = None,
    rerank: bool | None = None,
) -> dict[str, Any]:
    top_k = top_k or config.search.top_k
    candidates = candidates or config.search.candidates
    index = SearchIndex(catalog.con, config.embeddings.dim)
    embedder = OllamaEmbedder(
        model=config.embeddings.model,
        host=config.embeddings.host,
        timeout=config.embeddings.timeout,
        batch_size=config.embeddings.batch_size,
    )
    try:
        retriever = HybridRetriever(catalog, index, embedder, config)
        details: list[dict[str, Any]] = []
        for question in questions:
            results = retriever.search(
                question.query, top_k=top_k, candidates=candidates, rerank=rerank
            )
            relevances = [1 if is_relevant(r, question.expect) else 0 for r in results]
            first = next((i for i, rel in enumerate(relevances, start=1) if rel), None)
            details.append(
                {
                    "id": question.id,
                    "lang": question.lang,
                    "query": question.query,
                    "hit": 1.0 if first else 0.0,
                    "rr": 1.0 / first if first else 0.0,
                    "ndcg": _ndcg(relevances),
                    "top_title": results[0].title if results else None,
                }
            )
    finally:
        embedder.close()

    return {
        "top_k": top_k,
        "candidates": candidates,
        "rerank": bool(config.search.rerank if rerank is None else rerank),
        "questions": len(details),
        "recall@k": _mean(d["hit"] for d in details),
        "mrr": _mean(d["rr"] for d in details),
        "ndcg@k": _mean(d["ndcg"] for d in details),
        "details": details,
    }


def _ndcg(relevances: list[int]) -> float:
    dcg = sum(rel / math.log2(rank + 1) for rank, rel in enumerate(relevances, start=1))
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, sum(relevances) + 1))
    return dcg / ideal if ideal else 0.0


def _mean(values: Any) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0
