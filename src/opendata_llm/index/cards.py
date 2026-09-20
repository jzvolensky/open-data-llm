"""Turn catalog rows into compact, bilingual dataset cards for retrieval."""

from __future__ import annotations

import json
from typing import Any

import duckdb

from ..semantic import vocab


def collect_cards(con: duckdb.DuckDBPyConnection) -> list[tuple[str, str]]:
    concept_map = _concepts_by_dataset(con)
    field_map = _fields_by_item(con)
    cached_map = _cached_columns(con)

    rows = con.execute(
        "SELECT dataset_id, item_id, title, description, publisher, source, license, "
        "categories, tags, keywords, modified, dcat_id, item_type, service_url "
        "FROM datasets"
    ).fetchall()

    cards: list[tuple[str, str]] = []
    for row in rows:
        (
            dataset_id,
            item_id,
            title,
            description,
            publisher,
            source,
            license_,
            categories,
            tags,
            keywords,
            modified,
            dcat_id,
            item_type,
            service_url,
        ) = row
        concepts = concept_map.get(dataset_id, [])
        # Prefer the real cached-table columns (spaces/diacritics) over ArcGIS field names.
        fields = cached_map.get(dataset_id) or field_map.get(item_id, [])
        places = sorted(vocab.places_in(f"{title or ''} {description or ''}"))
        text = render_card(
            title=title,
            description=description,
            concepts=concepts,
            keywords=_loads(keywords) + _loads(tags),
            category=_first_label(categories),
            publisher=publisher,
            source=source,
            license_=license_,
            formats=_formats(con, dataset_id),
            modified=str(modified) if modified else None,
            places=[vocab.PLACES[p] for p in places],
            fields=fields,
            item_type=item_type,
            url=dcat_id or service_url,
        )
        cards.append((dataset_id, text))
    return cards


def render_card(
    *,
    title: str | None,
    description: str | None,
    concepts: list[str],
    keywords: list[str],
    category: str | None,
    publisher: str | None,
    source: str | None,
    license_: str | None,
    formats: list[str],
    modified: str | None,
    places: list[str],
    fields: list[str],
    item_type: str | None,
    url: str | None,
) -> str:
    lines: list[str] = []
    if title:
        lines.append(title.strip())
    if description:
        lines.append(description.strip())
    if concepts:
        lines.append("Témy: " + ", ".join(vocab.label_for(c, "sk") for c in concepts))
        lines.append("Topics: " + ", ".join(vocab.label_for(c, "en") for c in concepts))
    if keywords:
        lines.append("Kľúčové slová: " + ", ".join(dict.fromkeys(keywords)))
    if category:
        lines.append(f"Kategória: {category}")
    if publisher:
        lines.append(f"Vydavateľ: {publisher}")
    if source and source != publisher:
        lines.append(f"Zdroj: {source}")
    if formats:
        lines.append("Formáty: " + ", ".join(formats))
    if places:
        lines.append("Územie: " + ", ".join(places))
    if modified:
        lines.append(f"Aktualizované: {modified}")
    if item_type:
        lines.append(f"Typ: {item_type}")
    if license_:
        lines.append(f"Licencia: {license_}")
    if fields:
        lines.append("Stĺpce: " + ", ".join(fields))
    if url:
        lines.append(f"URL: {url}")
    return "\n".join(lines)


def _concepts_by_dataset(con: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    try:
        rows = con.execute(
            "SELECT dataset_id, concept_id FROM dataset_concepts ORDER BY score DESC"
        ).fetchall()
    except duckdb.Error:
        return out
    for dataset_id, concept_id in rows:
        out.setdefault(dataset_id, []).append(concept_id)
    return out


def _cached_columns(con: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    """Actual columns of cached CSV tables, keyed by dataset id."""
    out: dict[str, list[str]] = {}
    try:
        rows = con.execute(
            "SELECT dataset_id, columns FROM data_tables WHERE status = 'ok'"
        ).fetchall()
    except duckdb.Error:
        return out
    for dataset_id, columns in rows:
        names = _loads(columns)
        if names:
            out[dataset_id] = names[:20]
    return out


def _fields_by_item(con: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    try:
        rows = con.execute(
            "SELECT item_id, name, field_type FROM fields ORDER BY item_id, layer_id"
        ).fetchall()
    except duckdb.Error:
        return out
    for item_id, name, field_type in rows:
        items = out.setdefault(item_id, [])
        if len(items) < 15:
            short = (field_type or "").replace("esriFieldType", "")
            items.append(f"{name} ({short})" if short else str(name))
    return out


def _formats(con: duckdb.DuckDBPyConnection, dataset_id: str) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT fmt FROM distributions "
        "WHERE dataset_id = ? AND fmt NOT IN ('HTML', 'JSON') ORDER BY fmt",
        [dataset_id],
    ).fetchall()
    return [r[0] for r in rows if r[0]]


def _first_label(value: Any) -> str | None:
    items = _loads(value)
    if not items:
        return None
    return items[0].rsplit("/", 1)[-1]


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
    return [str(parsed)]
