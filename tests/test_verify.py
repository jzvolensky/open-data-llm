from __future__ import annotations

from opendata_llm.generate.verify import numbers_in, verify_answer


def test_numbers_in_ignores_urls_ids_and_dates() -> None:
    text = "V roku 2020 to bolo 14 302. https://x/8bd7889eaba647d4adcbc1e3516532cf"
    found = numbers_in(text)
    assert 14302.0 in found
    assert 2020.0 in found
    assert all(len(str(int(n))) < 8 for n in found)


def test_verify_answer_passes_grounded_number() -> None:
    data = {"rows": [[14302]], "sql": "SELECT ... WHERE ROK = 2025"}
    result = verify_answer("V Ružinove bolo 14 302 priestupkov v roku 2025.", data, [])
    assert result.verified, result.warnings


def test_verify_answer_flags_ungrounded_number() -> None:
    data = {"rows": [[14302]], "sql": "SELECT ..."}
    result = verify_answer("Bolo to 999 999 priestupkov.", data, [])
    assert not result.verified
    assert any("999999" in warning for warning in result.warnings)


def test_verify_answer_allows_derived_percentage() -> None:
    data = {"rows": [["A", 4021], ["B", 2510]]}
    result = verify_answer("Kategória A predstavuje 61,6 % záznamov.", data, [])
    assert result.verified, result.warnings


def test_verify_answer_flags_unknown_source_url() -> None:
    sources = [{"url": "https://data.bratislava.sk/datasets/x"}]
    result = verify_answer("Pozri https://example.com/other", None, sources)
    assert not result.verified
    assert any("example.com" in warning for warning in result.warnings)


def test_verify_answer_accepts_cited_source_url() -> None:
    sources = [{"url": "https://data.bratislava.sk/datasets/x"}]
    result = verify_answer(
        "Zdroj: https://data.bratislava.sk/datasets/x", None, sources
    )
    assert result.verified, result.warnings
