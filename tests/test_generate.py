from __future__ import annotations

from opendata_llm.generate.prompts import build_context, build_messages
from opendata_llm.generate.rag import _extract_sql
from opendata_llm.generate.router import classify


def test_classify_intents() -> None:
    assert classify("how many offences were recorded") == "data"
    assert classify("where are the schools in Petržalka") == "geospatial"
    assert classify("datasets about transport") == "discovery"


def test_classify_does_not_treat_lookup_as_geospatial() -> None:
    # "where can I find" is discovery, even when Bratislava (city-wide) is mentioned.
    assert classify("Kde nájdem údaje o doprave v Bratislave?") == "discovery"
    assert classify("where can I find public transport data") == "discovery"


def test_classify_numeric_with_district_is_data() -> None:
    assert classify("Koľko priestupkov bolo v Ružinove v roku 2025?") == "data"


def test_build_messages_includes_context_and_question() -> None:
    context = build_context([{"title": "GTFS", "url": "http://x", "card": "card text"}])
    messages = build_messages("Kde sú cestovné poriadky?", context)
    assert messages[0]["role"] == "system"
    assert "GTFS" in messages[1]["content"]
    assert "Kde sú cestovné poriadky?" in messages[1]["content"]


def test_extract_sql() -> None:
    assert _extract_sql("```sql\nSELECT 1\n```") == "SELECT 1"
    assert _extract_sql("Here you go: SELECT x FROM t;") == "SELECT x FROM t"
    assert _extract_sql("no query here") is None
