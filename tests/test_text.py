from __future__ import annotations

from opendata_llm.text import extract_item_id, first, language_code, parse_dt, scalar, strip_html


def test_strip_html_removes_tags_and_decodes_entities() -> None:
    assert strip_html("<p>Hello &amp; welcome</p>") == "Hello & welcome"
    assert strip_html(None) is None


def test_scalar_unwraps_jsonld() -> None:
    assert scalar({"@value": "2025-01-01"}) == "2025-01-01"
    assert scalar({"@id": "lang/SLK"}) == "lang/SLK"
    assert scalar({"skos:prefLabel": "Geospatial"}) == "Geospatial"
    assert scalar([{"@value": "a"}, {"@value": "b"}]) == ["a", "b"]


def test_extract_item_id() -> None:
    url = "https://www.arcgis.com/home/item.html?id=aba12fd2cbac4843bc7406151bc66106"
    assert extract_item_id(url) == "aba12fd2cbac4843bc7406151bc66106"
    assert extract_item_id(None) is None


def test_first_and_language_code() -> None:
    assert first(["x", "y"]) == "x"
    assert first("z") == "z"
    assert language_code("lang/SLK") == "SLK"


def test_parse_dt_handles_zulu() -> None:
    parsed = parse_dt("2026-09-19T04:00:24.000Z")
    assert parsed is not None and parsed.year == 2026
    assert parse_dt("not-a-date") is None
