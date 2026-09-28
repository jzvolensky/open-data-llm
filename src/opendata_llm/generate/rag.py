"""Retrieval-augmented answering over the catalog and data plane."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from ..config import Config
from ..index.embed import OllamaEmbedder
from ..index.store import SearchIndex
from ..query.profile import values_for
from ..query.sql import run_sql
from ..retrieve.hybrid import HybridRetriever, SearchResult
from ..semantic import vocab
from ..store import Catalog
from .base import Generator, Message
from .prompts import (
    build_context,
    build_messages,
    build_rewrite_messages,
    build_sql_messages,
)
from .router import classify
from .verify import verify_answer

_SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_SQL_START = re.compile(r"(select|with)\b", re.IGNORECASE)

CONTEXT_SOURCES = 6
SQL_MAX_TOKENS = 200
REWRITE_MAX_TOKENS = 64
DATA_CANDIDATES = 5
#: How many profiled columns and values to offer the SQL model.
MAX_VALUE_COLUMNS = 8
MAX_VALUES_PER_COLUMN = 20

STATUS_SEARCH = "Prehľadávam katalóg… · Searching the catalog…"
STATUS_REWRITING = "Spresňujem otázku z konverzácie… · Resolving the question…"
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
    "open",
    "registered",
    "register",
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
_CATEGORY_COLUMN_HINTS = (
    "druh",
    "kateg",
    "typ",
    "kind",
    "category",
    "charakter",
)
#: Words that are never a category value when scanning the question.
_CATEGORY_STOPWORDS = _STOPWORDS | {
    "aku",
    "ake",
    "aky",
    "ktore",
    "percento",
    "podiel",
    "pomer",
    "celkom",
    "spolu",
    "medzi",
    "podla",
    "vlastni",
    "vlastnit",
    "vlastnictvo",
    "vlastnicke",
    "vlastnictve",
    "mesto",
    "mesta",
    "hlavne",
    "hlavneho",
}
_NUMERIC_TOKEN = re.compile(r"^\d+(?:[.,]\d+)?$")


@dataclass
class RagAnswer:
    answer: str
    intent: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    data: dict[str, Any] | None = None
    answer_verified: bool = True
    warnings: list[str] = field(default_factory=list)


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


def rewrite_query(
    generator: Generator, query: str, history: list[dict[str, str]] | None
) -> str:
    """Turn the latest question into a standalone query using the recent turns."""
    if not history:
        return query
    try:
        raw = generator.generate(
            build_rewrite_messages(query, history),
            max_tokens=REWRITE_MAX_TOKENS,
            temperature=0,
        )
    except Exception:  # noqa: BLE001 - fall back to the raw question
        return query
    rewritten = (raw.strip().splitlines()[0] if raw.strip() else "").strip().strip('"')
    return rewritten or query


def prepare(
    config: Config,
    catalog: Catalog,
    query: str,
    generator: Generator,
    top_k: int | None = None,
    rerank: bool | None = None,
    allow_data: bool = True,
    embedder: OllamaEmbedder | None = None,
    history: list[dict[str, str]] | None = None,
) -> PreparedAnswer:
    effective = rewrite_query(generator, query, history)
    results = _retrieve(config, catalog, effective, top_k, rerank, embedder)
    intent = classify(effective)
    data_result = (
        _data_answer(catalog, effective, results, generator)
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
        effective,
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
    history: list[dict[str, str]] | None = None,
) -> RagAnswer:
    prepared = prepare(
        config, catalog, query, generator, top_k, rerank, allow_data, embedder, history
    )
    try:
        answer = generator.generate(prepared.messages)
    except Exception as exc:  # noqa: BLE001 - degrade to retrieval-only
        listing = "\n".join(f"- {s['title']} ({s['url']})" for s in prepared.sources[:5])
        answer = f"[generation unavailable: {type(exc).__name__}]\n\n{listing}"
    verification = verify_answer(answer, prepared.data, prepared.sources)
    if verification.warnings:
        answer = _annotate(answer, verification.warnings)
    return RagAnswer(
        answer=answer,
        intent=prepared.intent,
        sources=prepared.sources,
        data=prepared.data,
        answer_verified=verification.verified,
        warnings=verification.warnings,
    )


def _annotate(answer: str, warnings: list[str]) -> str:
    note = "⚠️ " + "; ".join(warnings)
    return f"{answer}\n\n{note}"


def stream_events(
    config: Config,
    catalog: Catalog,
    query: str,
    generator: Generator,
    top_k: int | None = None,
    rerank: bool | None = None,
    allow_data: bool = True,
    embedder: OllamaEmbedder | None = None,
    history: list[dict[str, str]] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield progress and answer events for a streaming UI."""
    effective = query
    if history:
        yield {"event": "status", "stage": "rewriting", "message": STATUS_REWRITING}
        effective = rewrite_query(generator, query, history)
        if effective != query:
            yield {
                "event": "status",
                "stage": "rewritten",
                "message": f"Samostatná otázka: {effective}",
            }

    yield {"event": "status", "stage": "searching", "message": STATUS_SEARCH}
    results = _retrieve(config, catalog, effective, top_k, rerank, embedder)
    yield {
        "event": "status",
        "stage": "retrieved",
        "message": f"Nájdených {len(results)} datasetov · {len(results)} datasets found",
    }

    intent = classify(effective)
    data = None
    if allow_data and intent == "data":
        yield {"event": "status", "stage": "sql", "message": STATUS_SQL}
        data = _data_answer(catalog, effective, results, generator)
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
        effective, build_context(sources[:CONTEXT_SOURCES]), _format_data(data)
    )
    yield {
        "event": "sources",
        "intent": intent,
        "query": effective,
        "sources": sources,
        "data": data,
    }

    yield {"event": "status", "stage": "generating", "message": STATUS_GENERATING}
    stream = getattr(generator, "stream", None)
    chunks: list[str] = []
    try:
        if callable(stream):
            for delta in stream(messages):
                text = str(delta)
                chunks.append(text)
                yield {"event": "token", "text": text}
        else:
            text = generator.generate(messages)
            chunks.append(text)
            yield {"event": "token", "text": text}
    except Exception as exc:  # noqa: BLE001 - report over the stream
        yield {"event": "error", "error": f"{type(exc).__name__}: {exc}"}

    verification = verify_answer("".join(chunks), data, sources)
    if verification.warnings:
        yield {"event": "token", "text": "\n\n" + "⚠️ " + "; ".join(verification.warnings)}
    yield {
        "event": "verification",
        "verified": verification.verified,
        "warnings": verification.warnings,
    }
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


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _district_target(
    catalog: Catalog, dataset_id: str, table: str, district: str | None
) -> tuple[str, str] | None:
    """Find a district-like column and the exact value matching ``district``."""
    if not district:
        return None
    described = catalog.con.execute(f"DESCRIBE {table}").fetchall()  # noqa: S608
    columns = [row[0] for row in described]
    candidates = [
        column
        for column in columns
        if any(hint in vocab.fold(column) for hint in _DISTRICT_COLUMN_HINTS)
    ]
    wanted = vocab.fold(district)
    profiled = values_for(catalog, dataset_id)
    for column in candidates:
        for value in profiled.get(column, []):
            if vocab.fold(value) == wanted:
                return column, value
    # Fallback: case-insensitive prefix match in the table itself.
    for column in candidates:
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


def _value_matches_query(value: str, padded_query: str) -> bool:
    """True only when the whole value phrase appears as words in the question."""
    folded = vocab.fold(value)
    return len(folded) >= 4 and f" {folded} " in padded_query


def _value_lines(values: dict[str, list[str]], query: str) -> list[str]:
    """Offer the actual values of columns whose value the question quotes verbatim.

    Matching a whole value phrase (not loose word stems) keeps the model from
    inventing filters for unrelated categorical columns.
    """
    padded_query = f" {vocab.fold(query)} "
    lines: list[str] = []
    for column, column_values in values.items():
        shown = [v for v in column_values if _value_matches_query(v, padded_query)]
        if not shown:
            continue
        rendered = ", ".join(f"'{value}'" for value in shown[:MAX_VALUES_PER_COLUMN])
        lines.append(
            f'Prípustné hodnoty stĺpca "{column}": {rendered}. Použi presne uvedený tvar.'
        )
        if len(lines) >= MAX_VALUE_COLUMNS:
            break
    return lines


def _normalize_sql(sql: str, columns: list[str]) -> str:
    """Fix the common mistake of single-quoting identifiers that need double quotes."""
    for column in columns:
        if f"'{column}'" in sql:
            sql = sql.replace(f"'{column}'", _quote_ident(column))
    return sql


_NUMERIC_VALUE = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _pick_category_column(profiled: dict[str, list[str]]) -> str | None:
    """Choose the label-like categorical column (prefer names over codes)."""
    scored: list[tuple[int, str]] = []
    for column, values in profiled.items():
        folded = vocab.fold(column)
        if not any(hint in folded for hint in _CATEGORY_COLUMN_HINTS):
            continue
        if sum(1 for value in values if not _NUMERIC_VALUE.match(value.strip())) < 2:
            continue
        score = 2 if any(k in folded for k in ("nazov", "nazev", "name", "popis")) else 0
        score -= 1 if any(k in folded for k in ("kod", "id")) else 0
        scored.append((score, column))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]


def _requested_category(
    query: str, title: str | None, profiled: dict[str, list[str]]
) -> tuple[str, str] | None:
    """Detect a category modifier the question names that the dataset does not define.

    Only an unknown word immediately modifying a title noun (e.g. *obytných
    pozemkov*) is treated as a requested category, which keeps ordinary count
    questions from triggering a breakdown.
    """
    column = _pick_category_column(profiled)
    if not column:
        return None
    known = [word for value in profiled[column] for word in vocab.fold(value).split()]
    title_words = vocab.fold(title or "").split()
    tokens = _WORD.findall(query)
    for index, token in enumerate(tokens):
        folded = vocab.fold(token)
        if len(folded) < 4 or folded in _CATEGORY_STOPWORDS:
            continue
        if vocab.places_in(token) or _NUMERIC_TOKEN.match(folded):
            continue
        if any(vocab.stems_match(word, folded) for word in title_words):
            continue
        if any(vocab.stems_match(word, folded) for word in known):
            continue
        following = vocab.fold(tokens[index + 1]) if index + 1 < len(tokens) else ""
        if following in _CATEGORY_STOPWORDS:
            continue
        if not following or not any(
            vocab.stems_match(word, following) for word in title_words
        ):
            continue
        return column, token
    return None


_FILTER_QUOTED = re.compile(r'"([^"]+)"\s*(?:=|I?LIKE)\s*\'([^\']*)\'', re.IGNORECASE)
_FILTER_BARE = re.compile(
    r"\b([A-Za-z_][\w\u00c0-\u024f]*)\s*(?:=|I?LIKE)\s*'([^']*)'", re.IGNORECASE
)


def _filter_literals(sql: str) -> list[tuple[str, str]]:
    found = _FILTER_QUOTED.findall(sql)
    return found or _FILTER_BARE.findall(sql)


def _ambiguity(
    sql: str, values: dict[str, list[str]]
) -> tuple[str, str] | None:
    """Return ``(column, requested)`` when SQL filters a known column by an unknown value."""
    for column, literal in _filter_literals(sql):
        allowed = values.get(column)
        if not allowed:
            continue
        if not any(vocab.fold(value) == vocab.fold(literal) for value in allowed):
            return column, literal
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


def _data_answer(
    catalog: Catalog,
    query: str,
    results: list[SearchResult],
    generator: Generator,
) -> dict[str, Any] | None:
    district = _district(query)
    stems = _query_stems(query)
    for result, table in _candidates(catalog, query, results):
        try:
            described = catalog.con.execute(f"DESCRIBE {table}").fetchall()  # noqa: S608
        except Exception:  # noqa: BLE001 - try the next candidate
            continue
        schema = ", ".join(f"{row[0]} {row[1]}" for row in described)

        # Relevance gate: never force SQL onto a dataset unrelated to the question.
        if not _stem_overlap(stems, f"{result.title or ''} {result.card or ''} {schema}"):
            continue

        district_target = _district_target(catalog, result.dataset_id, table, district)
        profiled = values_for(catalog, result.dataset_id)

        requested = _requested_category(query, result.title, profiled)
        if requested:
            fallback = _breakdown(
                catalog,
                result.dataset_id,
                result.title or "",
                table,
                requested[0],
                requested[1],
                district,
                district_target,
            )
            if fallback:
                return fallback

        hints = None
        if district_target:
            column, value = district_target
            hints = [
                f'V otázke sa spomína územie "{district}". '
                f'Filtruj podľa stĺpca "{column}" hodnotou \'{value}\'.'
            ]
        value_lines = _value_lines(profiled, query)

        try:
            raw = generator.generate(
                build_sql_messages(
                    query, table, schema, result.title, hints, value_lines
                ),
                max_tokens=SQL_MAX_TOKENS,
                temperature=0,
            )
            if "NO_DATA" in raw.upper():
                continue
            sql = _extract_sql(raw)
            if not sql:
                continue
        except Exception:  # noqa: BLE001 - try the next candidate
            continue

        sql = _normalize_sql(sql, [row[0] for row in described])
        if not _grounded(table, sql, district, district_target):
            continue
        try:
            out_columns, rows = run_sql(catalog.con, sql, max_rows=50)
        except Exception:  # noqa: BLE001 - try the next candidate
            continue
        if not rows:
            ambiguous = _ambiguity(sql, profiled)
            if ambiguous:
                fallback = _breakdown(
                    catalog,
                    result.dataset_id,
                    result.title or "",
                    table,
                    ambiguous[0],
                    ambiguous[1],
                    district,
                    district_target,
                )
                if fallback:
                    return fallback
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


def _breakdown(
    catalog: Catalog,
    dataset_id: str,
    title: str,
    table: str,
    column: str,
    requested: str,
    district: str | None,
    district_target: tuple[str, str] | None,
) -> dict[str, Any] | None:
    """Return the real value breakdown for a column whose requested value is unknown."""
    quoted = _quote_ident(column)
    where = ""
    if district_target:
        literal = district_target[1].replace("'", "''")
        where = f" WHERE {_quote_ident(district_target[0])} = '{literal}'"
    fallback_sql = (
        f"SELECT {quoted}, count(*) AS pocet FROM {table}{where} "
        f"GROUP BY 1 ORDER BY 2 DESC LIMIT 50"
    )
    try:
        grouped = catalog.con.execute(fallback_sql).fetchall()  # noqa: S608
    except Exception:  # noqa: BLE001 - fall back to the next candidate
        return None
    if not grouped:
        return None
    return {
        "dataset_id": dataset_id,
        "title": title,
        "table": table,
        "sql": fallback_sql,
        "columns": [column, "pocet"],
        "rows": [[value, count] for value, count in grouped],
        "district": district,
        "district_column": district_target[0] if district_target else None,
        "district_value": district_target[1] if district_target else None,
        "row_count": len(grouped),
        "ambiguous": {"column": column, "requested": requested},
        "note": (
            f'Kategória "{requested}" nie je v datasete definovaná. '
            f'Zobrazujem skutočné hodnoty stĺpca "{column}".'
        ),
    }


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
    ]
    if data.get("note"):
        lines.append(f"Poznámka: {data['note']}")
    if data.get("district"):
        lines.append(
            f"Filter: {data.get('district_column')} = {data.get('district_value')}"
        )
    lines.append(" | ".join(str(c) for c in columns))
    for row in data.get("rows") or []:
        lines.append(" | ".join("" if v is None else str(v) for v in row))
    return "\n".join(lines)
