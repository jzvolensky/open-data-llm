"""Retrieval-augmented answering over the catalog and data plane."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from ..config import Config
from ..index.embed import OllamaEmbedder
from ..index.store import SearchIndex
from ..query.sql import run_sql
from ..retrieve.hybrid import HybridRetriever, SearchResult
from ..semantic import vocab
from ..store import Catalog
from .base import Generator, Message
from .prompts import (
    build_context,
    build_messages,
    build_sql_messages,
    build_verify_messages,
)
from .router import classify

_SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_SQL_START = re.compile(r"(select|with)\b", re.IGNORECASE)

CONTEXT_SOURCES = 6
SQL_MAX_TOKENS = 200
DATA_CANDIDATES = 5

STATUS_SEARCH = "Prehľadávam katalóg… · Searching the catalog…"
STATUS_SQL = "Zostavujem a overujem SQL… · Building and checking SQL…"
STATUS_GENERATING = "Generujem odpoveď… · Generating the answer…"

# Query words that carry no dataset signal.
_STOPWORDS = {
    "koko",
    "kolko",
    "how",
    "many",
    "much",
    "bolo",
    "bol",
    "bola",
    "boli",
    "roku",
    "rok",
    "the",
    "and",
    "for",
    "with",
    "za",
    "podla",
    "data",
    "datasety",
    "dataset",
    "udaje",
}
_PLACE_STEMS = {
    vocab.stem(word) for name in vocab.PLACES.values() for word in vocab.fold(name).split()
}
_DISTRICT_COLUMN_HINTS = (
    "katastr",
    "uzem",
    "mestsk",
    "cast",
    "okres",
    "district",
    "obec",
)


@dataclass
class RagAnswer:
    answer: str
    intent: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    data: dict[str, Any] | None = None


@dataclass
class PreparedAnswer:
    """Retrieval + optional SQL result, ready to be turned into an answer."""

    intent: str
    sources: list[dict[str, Any]]
    data: dict[str, Any] | None
    messages: list[Message]


def _retrieve(
    config: Config,
    catalog: Catalog,
    query: str,
    top_k: int | None = None,
    rerank: bool | None = None,
    embedder: OllamaEmbedder | None = None,
) -> list[SearchResult]:
    local_embedder = embedder is None
    embedder = embedder or OllamaEmbedder(
        model=config.embeddings.model,
        host=config.embeddings.host,
        timeout=config.embeddings.timeout,
        batch_size=config.embeddings.batch_size,
    )
    try:
        index = SearchIndex(catalog.con, config.embeddings.dim)
        retriever = HybridRetriever(catalog, index, embedder, config)
        return retriever.search(query, top_k=top_k, rerank=rerank)
    finally:
        if local_embedder:
            embedder.close()


def prepare(
    config: Config,
    catalog: Catalog,
    query: str,
    generator: Generator,
    top_k: int | None = None,
    rerank: bool | None = None,
    allow_data: bool = True,
    embedder: OllamaEmbedder | None = None,
) -> PreparedAnswer:
    results = _retrieve(config, catalog, query, top_k, rerank, embedder)
    intent = classify(query)
    data_result = (
        _data_answer(catalog, query, results, generator)
        if allow_data and intent == "data"
        else None
    )

    sources = [
        {
            "dataset_id": r.dataset_id,
            "title": r.title or "",
            "url": r.url or r.dataset_id,
            "license": r.license or "",
            "card": r.card or "",
        }
        for r in results
    ]
    messages = build_messages(
        query,
        build_context(sources[:CONTEXT_SOURCES]),
        _format_data(data_result),
    )
    return PreparedAnswer(intent=intent, sources=sources, data=data_result, messages=messages)


def rag_answer(
    config: Config,
    catalog: Catalog,
    query: str,
    generator: Generator,
    top_k: int | None = None,
    rerank: bool | None = None,
    allow_data: bool = True,
    embedder: OllamaEmbedder | None = None,
) -> RagAnswer:
    prepared = prepare(
        config, catalog, query, generator, top_k, rerank, allow_data, embedder
    )
    try:
        answer = generator.generate(prepared.messages)
    except Exception as exc:  # noqa: BLE001 - degrade to retrieval-only
        listing = "\n".join(f"- {s['title']} ({s['url']})" for s in prepared.sources[:5])
        answer = f"[generation unavailable: {type(exc).__name__}]\n\n{listing}"
    return RagAnswer(
        answer=answer,
        intent=prepared.intent,
        sources=prepared.sources,
        data=prepared.data,
    )


def stream_events(
    config: Config,
    catalog: Catalog,
    query: str,
    generator: Generator,
    top_k: int | None = None,
    rerank: bool | None = None,
    allow_data: bool = True,
    embedder: OllamaEmbedder | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield progress and answer events for a streaming UI."""
    yield {"event": "status", "stage": "searching", "message": STATUS_SEARCH}
    results = _retrieve(config, catalog, query, top_k, rerank, embedder)
    yield {
        "event": "status",
        "stage": "retrieved",
        "message": f"Nájdených {len(results)} datasetov · {len(results)} datasets found",
    }

    intent = classify(query)
    data = None
    if allow_data and intent == "data":
        yield {"event": "status", "stage": "sql", "message": STATUS_SQL}
        data = _data_answer(catalog, query, results, generator)
        if data:
            yield {
                "event": "status",
                "stage": "computed",
                "message": f"Vypočítané z: {data.get('title')}",
            }

    sources = [
        {
            "dataset_id": r.dataset_id,
            "title": r.title or "",
            "url": r.url or r.dataset_id,
            "license": r.license or "",
            "card": r.card or "",
        }
        for r in results
    ]
    messages = build_messages(
        query, build_context(sources[:CONTEXT_SOURCES]), _format_data(data)
    )
    yield {"event": "sources", "intent": intent, "sources": sources, "data": data}

    yield {"event": "status", "stage": "generating", "message": STATUS_GENERATING}
    stream = getattr(generator, "stream", None)
    try:
        if callable(stream):
            for delta in stream(messages):
                yield {"event": "token", "text": str(delta)}
        else:
            yield {"event": "token", "text": generator.generate(messages)}
    except Exception as exc:  # noqa: BLE001 - report over the stream
        yield {"event": "error", "error": f"{type(exc).__name__}: {exc}"}
    yield {"event": "done"}


# -- data plane ----------------------------------------------------------------


def _query_stems(query: str) -> list[str]:
    stems: list[str] = []
    for word in vocab.fold(query).split():
        if len(word) < 4 or word in _STOPWORDS:
            continue
        stem = vocab.stem(word)
        if stem in _PLACE_STEMS:
            continue
        stems.append(stem)
    return stems


def _stem_overlap(stems: list[str], text: str) -> int:
    tokens = vocab.fold(text).split()
    count = 0
    for stem in stems:
        if any(vocab.stems_match(stem, token) for token in tokens):
            count += 1
    return count


def _district(query: str) -> str | None:
    places = vocab.places_in(query) - {"bratislava"}
    if not places:
        return None
    # Prefer the most specific district (e.g. Devínska Nová Ves over Devín).
    slug = max(places, key=lambda s: len(vocab.fold(vocab.PLACES[s])))
    return vocab.PLACES[slug]


def _candidates(
    catalog: Catalog, query: str, results: list[SearchResult]
) -> list[tuple[SearchResult, str]]:
    stems = _query_stems(query)
    concepts = vocab.concepts_in(query)
    scored: list[tuple[float, SearchResult, str]] = []
    for rank, result in enumerate(results):
        row = catalog.con.execute(
            "SELECT table_name FROM data_tables WHERE dataset_id = ? AND status = 'ok'",
            [result.dataset_id],
        ).fetchone()
        if not row or not row[0]:
            continue
        score = 2.0 * _stem_overlap(stems, f"{result.title or ''} {result.card or ''}")
        score += len(concepts.intersection(result.concepts))
        score += 1.0 / (rank + 1)
        scored.append((score, result, row[0]))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [(result, table) for _, result, table in scored[:DATA_CANDIDATES]]


def _district_target(
    catalog: Catalog, table: str, district: str | None
) -> tuple[str, str] | None:
    """Find a district-like column and the value matching ``district``."""
    if not district:
        return None
    described = catalog.con.execute(f"DESCRIBE {table}").fetchall()  # noqa: S608
    columns = [row[0] for row in described]
    for column in columns:
        if not any(hint in vocab.fold(column) for hint in _DISTRICT_COLUMN_HINTS):
            continue
        try:
            row = catalog.con.execute(
                f'SELECT "{column}" FROM {table} '  # noqa: S608
                f'WHERE "{column}" ILIKE ? LIMIT 1',
                [f"%{district[:6]}%"],
            ).fetchone()
        except Exception:  # noqa: BLE001 - try the next column
            continue
        if row and row[0] is not None:
            return column, str(row[0])
    return None


def _grounded(
    table: str,
    sql: str,
    district: str | None,
    district_target: tuple[str, str] | None,
) -> bool:
    if table.lower() not in sql.lower():
        return False
    if district:
        if not district_target:
            return False
        if vocab.fold(district_target[0]) not in vocab.fold(sql):
            return False
    return True


def _verify(
    generator: Generator,
    query: str,
    table: str,
    schema: str,
    sql: str,
    preview: str,
) -> bool:
    try:
        raw = generator.generate(
            build_verify_messages(query, table, schema, sql, preview), max_tokens=8
        )
    except Exception:  # noqa: BLE001 - rules stand if verification is unavailable
        return True
    match = re.search(r"\b(YES|NO)\b", raw.upper())
    return match.group(1) == "YES" if match else True


def _data_answer(
    catalog: Catalog,
    query: str,
    results: list[SearchResult],
    generator: Generator,
) -> dict[str, Any] | None:
    district = _district(query)
    for result, table in _candidates(catalog, query, results):
        try:
            described = catalog.con.execute(f"DESCRIBE {table}").fetchall()  # noqa: S608
        except Exception:  # noqa: BLE001 - try the next candidate
            continue
        schema = ", ".join(f"{row[0]} {row[1]}" for row in described)

        district_target = _district_target(catalog, table, district)
        hints = None
        if district_target:
            column, value = district_target
            hints = [
                f'V otázke sa spomína územie "{district}". '
                f'Filtruj podľa stĺpca "{column}" hodnotou \'{value}\'.'
            ]

        try:
            raw = generator.generate(
                build_sql_messages(query, table, schema, result.title, hints),
                max_tokens=SQL_MAX_TOKENS,
            )
            if "NO_DATA" in raw.upper():
                continue
            sql = _extract_sql(raw)
            if not sql:
                continue
        except Exception:  # noqa: BLE001 - try the next candidate
            continue

        if not _grounded(table, sql, district, district_target):
            continue
        try:
            out_columns, rows = run_sql(catalog.con, sql, max_rows=50)
        except Exception:  # noqa: BLE001 - try the next candidate
            continue
        if not rows:
            continue

        preview = f"{' | '.join(out_columns)}\n" + "\n".join(
            " | ".join("" if v is None else str(v) for v in row) for row in rows
        )
        if not _verify(generator, query, table, schema, sql, preview):
            continue

        return {
            "dataset_id": result.dataset_id,
            "title": result.title or "",
            "table": table,
            "sql": sql,
            "columns": out_columns,
            "rows": [list(row) for row in rows],
            "district": district,
            "district_column": district_target[0] if district_target else None,
            "district_value": district_target[1] if district_target else None,
            "row_count": len(rows),
        }
    return None


def _extract_sql(text: str) -> str | None:
    block = _SQL_BLOCK.search(text)
    if block:
        candidate = block.group(1).strip()
    else:
        match = _SQL_START.search(text)
        candidate = text[match.start() :].strip() if match else ""
    candidate = candidate.strip().rstrip(";")
    return candidate or None


def _format_data(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    columns = data.get("columns") or []
    lines = [
        f"Dataset: {data.get('title')}",
        f"SQL: {data.get('sql')}",
        " | ".join(str(c) for c in columns),
    ]
    if data.get("district"):
        lines.insert(
            2,
            f"Filter: {data.get('district_column')} = {data.get('district_value')}",
        )
    for row in data.get("rows") or []:
        lines.append(" | ".join("" if v is None else str(v) for v in row))
    return "\n".join(lines)
