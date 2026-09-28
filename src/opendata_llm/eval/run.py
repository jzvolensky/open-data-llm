"""Evaluate the retrieval and data paths against a typed bilingual gold set.

Question types
--------------
``discovery``  dataset lookup — scored with recall@k / MRR / nDCG@k.
``data``       numeric question with a gold value — scored with execution accuracy
               (the *data path* result, no prose generation).
``geo``        district resolution — scored on the extracted district.
``abstain``    unanswerable question — scored on whether the data path declines.
``followup``   multi-turn question whose referents live in ``history``.

Data/abstain/followup cases require a ``generator`` (the SQL is model-generated);
without one they are reported as skipped and excluded from their accuracy metric.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from ..config import Config
from ..generate.base import Generator
from ..generate.rag import _data_answer
from ..generate.router import classify
from ..index.embed import OllamaEmbedder
from ..index.store import SearchIndex
from ..retrieve.hybrid import HybridRetriever, SearchResult
from ..semantic import vocab
from ..store import Catalog
from ..text import as_number

DEFAULT_QUESTIONS = Path(__file__).with_name("questions.jsonl")
DEFAULT_REPORT_DIR = Path("reports/eval")

TYPES = ("discovery", "data", "geo", "abstain", "followup")
#: Types whose answers come from the SQL/data plane.
DATA_TYPES = ("data", "abstain", "followup")
#: Types scored with the ranking metrics.
RETRIEVAL_TYPES = ("discovery",)


@dataclass
class Question:
    id: str
    type: str
    lang: str
    query: str
    expect: list[str] = field(default_factory=list)
    gold: Any | None = None
    dataset: str | None = None
    district: str | None = None
    year: int | None = None
    tolerance: float = 0.0
    history: list[dict[str, str]] = field(default_factory=list)
    note: str | None = None


def load_questions(path: str | Path | None = None) -> list[Question]:
    path = Path(path) if path else DEFAULT_QUESTIONS
    questions: list[Question] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        qtype = payload.get("type", "discovery")
        if qtype not in TYPES:
            raise ValueError(f"{payload.get('id')}: unknown type {qtype!r}")
        questions.append(
            Question(
                id=payload["id"],
                type=qtype,
                lang=payload.get("lang", "sk"),
                query=payload["query"],
                expect=[e.lower() for e in payload.get("expect", [])],
                gold=payload.get("gold"),
                dataset=payload.get("dataset"),
                district=payload.get("district"),
                year=payload.get("year"),
                tolerance=float(payload.get("tolerance", 0.0)),
                history=payload.get("history", []),
                note=payload.get("note"),
            )
        )
    return questions


def is_relevant(result: SearchResult, expect: list[str]) -> bool:
    title = (result.title or "").lower()
    return any(needle in title for needle in expect)


# -- value normalization -------------------------------------------------------


def _value_matches(cell: Any, gold: Any, tolerance: float) -> bool:
    if cell is None:
        return False
    gold_number = as_number(gold)
    cell_number = as_number(cell)
    if gold_number is not None and cell_number is not None:
        return abs(gold_number - cell_number) <= tolerance
    return str(cell).strip().lower() == str(gold).strip().lower()


def _data_contains(data: dict[str, Any], gold: Any, tolerance: float) -> bool:
    cells = [cell for row in data.get("rows") or [] for cell in row]
    if isinstance(gold, (list, tuple)):
        return all(
            any(_value_matches(cell, item, tolerance) for cell in cells) for item in gold
        )
    return any(_value_matches(cell, gold, tolerance) for cell in cells)


# -- scoring -------------------------------------------------------------------


def _data_passed(question: Question, data: dict[str, Any] | None) -> bool:
    if data is None:
        return False
    if question.dataset:
        haystack = f"{data.get('dataset_id', '')} {data.get('title', '')}".lower()
        if question.dataset.lower() not in haystack:
            return False
    if question.district:
        found = vocab.fold(str(data.get("district_value") or ""))
        if vocab.fold(question.district) not in found:
            return False
    if question.gold is None:
        return True
    return _data_contains(data, question.gold, question.tolerance)


def _geo_passed(question: Question) -> bool:
    if not question.district:
        return False
    from ..generate.rag import _district

    return (_district(question.query) or "").lower() == question.district.lower()


def _mean(values: Any) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * fraction
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    return ordered[low] * (high - rank) + ordered[high] * (rank - low)


def _latency(values: list[float]) -> dict[str, float]:
    return {
        "p50": round(_percentile(values, 0.50), 1),
        "p90": round(_percentile(values, 0.90), 1),
        "p95": round(_percentile(values, 0.95), 1),
    }


# -- evaluation ----------------------------------------------------------------


def evaluate(
    config: Config,
    catalog: Catalog,
    questions: list[Question],
    top_k: int | None = None,
    candidates: int | None = None,
    rerank: bool | None = None,
    generator: Generator | None = None,
    rewrite: Callable[[str, list[dict[str, str]]], str] | None = None,
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
    details: list[dict[str, Any]] = []
    try:
        retriever = HybridRetriever(catalog, index, embedder, config)
        for question in questions:
            started = perf_counter()
            effective = (
                rewrite(question.query, question.history)
                if rewrite and question.history
                else question.query
            )
            results = retriever.search(
                effective, top_k=top_k, candidates=candidates, rerank=rerank
            )
            retrieval_ms = (perf_counter() - started) * 1000

            relevances = [1 if is_relevant(r, question.expect) else 0 for r in results]
            first = next((i for i, rel in enumerate(relevances, start=1) if rel), None)
            detail: dict[str, Any] = {
                "id": question.id,
                "type": question.type,
                "lang": question.lang,
                "query": question.query,
                "effective_query": effective,
                "hit": 1.0 if first else 0.0,
                "rr": 1.0 / first if first else 0.0,
                "ndcg": _ndcg(relevances),
                "top_title": results[0].title if results else None,
                "retrieval_ms": round(retrieval_ms, 1),
            }

            if question.type in DATA_TYPES:
                if generator is None:
                    detail["skipped"] = "no generator"
                else:
                    data_started = perf_counter()
                    data = (
                        _data_answer(catalog, effective, results, generator)
                        if classify(effective) == "data"
                        else None
                    )
                    detail["data_ms"] = round((perf_counter() - data_started) * 1000, 1)
                    detail["data"] = _summarize(data)
                    if question.type == "abstain":
                        detail["passed"] = data is None
                    else:
                        detail["passed"] = _data_passed(question, data)
            elif question.type == "geo":
                detail["passed"] = _geo_passed(question)
            else:
                detail["passed"] = bool(first)
            details.append(detail)
    finally:
        embedder.close()

    return _aggregate(
        details,
        top_k=top_k,
        candidates=candidates,
        rerank=bool(config.search.rerank if rerank is None else rerank),
    )


def _summarize(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return None
    return {
        "dataset_id": data.get("dataset_id"),
        "table": data.get("table"),
        "sql": data.get("sql"),
        "columns": data.get("columns"),
        "rows": data.get("rows"),
        "district_value": data.get("district_value"),
    }


def _aggregate(
    details: list[dict[str, Any]],
    top_k: int,
    candidates: int,
    rerank: bool,
) -> dict[str, Any]:
    def of_type(*types: str, require_run: bool = False) -> list[dict[str, Any]]:
        return [
            d
            for d in details
            if d["type"] in types and (not require_run or not d.get("skipped"))
        ]

    retrieval = of_type(*RETRIEVAL_TYPES)
    data_cases = of_type("data", require_run=True)
    followups = of_type("followup", require_run=True)
    abstains = of_type("abstain", require_run=True)

    def accuracy(items: list[dict[str, Any]]) -> float:
        return _mean(1.0 if d.get("passed") else 0.0 for d in items)

    retrieval_ms = [d["retrieval_ms"] for d in details]
    data_ms = [d["data_ms"] for d in details if "data_ms" in d]
    return {
        "top_k": top_k,
        "candidates": candidates,
        "rerank": rerank,
        "questions": len(details),
        # ranking metrics (discovery)
        "recall@k": _mean(d["hit"] for d in retrieval),
        "mrr": _mean(d["rr"] for d in retrieval),
        "ndcg@k": _mean(d["ndcg"] for d in retrieval),
        # answer-path metrics
        "execution_accuracy": accuracy(data_cases),
        "abstention_accuracy": accuracy(abstains),
        "resolution_accuracy": accuracy(followups),
        "geo_accuracy": accuracy(of_type("geo")),
        # latency percentiles (ms)
        "latency": {
            "retrieval_ms": _latency(retrieval_ms),
            "data_ms": _latency(data_ms),
        },
        "by_type": {
            qtype: {
                "count": len(of_type(qtype)),
                "run": len(of_type(qtype, require_run=True)),
                "passed": sum(1 for d in of_type(qtype, require_run=True) if d.get("passed")),
            }
            for qtype in TYPES
        },
        "details": details,
    }


def _ndcg(relevances: list[int]) -> float:
    dcg = sum(rel / math.log2(rank + 1) for rank, rel in enumerate(relevances, start=1))
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, sum(relevances) + 1))
    return dcg / ideal if ideal else 0.0


def write_report(report: dict[str, Any], directory: str | Path = DEFAULT_REPORT_DIR) -> Path:
    """Persist a dated JSON report and return its path."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = directory / f"eval-{stamp}.json"
    payload = {"generated_at": datetime.now(UTC).isoformat(), **report}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return path
