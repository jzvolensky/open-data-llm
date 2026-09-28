from __future__ import annotations

import json

import pytest

from opendata_llm.eval.run import (
    Question,
    _aggregate,
    _data_contains,
    _data_passed,
    _geo_passed,
    _percentile,
    as_number,
    load_questions,
    write_report,
)


def test_as_number_normalizes_thousands_and_decimals() -> None:
    assert as_number("14 302") == 14302
    assert as_number("14.302") == 14302
    assert as_number("14,302") == 14302
    assert as_number(14302) == 14302
    assert as_number("1,5") == 1.5
    assert as_number("1.5") == 1.5
    assert as_number("abc") is None
    assert as_number(None) is None
    assert as_number(True) is None


def test_data_contains_matches_normalized_gold() -> None:
    data = {"rows": [[14302]], "columns": ["c"]}
    assert _data_contains(data, 14302, 0.0)
    assert _data_contains(data, "14 302", 0.0)
    assert not _data_contains(data, 7056, 0.0)


def test_data_passed_checks_dataset_district_and_value() -> None:
    data = {
        "dataset_id": "https://data.bratislava.sk/datasets/MagBa::pocet-priestupkov",
        "title": "Počet priestupkov podľa mestských častí",
        "rows": [[14302]],
        "district_value": "Ružinov",
    }
    question = Question(
        id="d1",
        type="data",
        lang="sk",
        query="koľko priestupkov v Ružinove?",
        gold=14302,
        dataset="priestupk",
        district="Ružinov",
    )
    assert _data_passed(question, data)
    assert not _data_passed(question, None)
    assert not _data_passed(question, {**data, "district_value": "Petržalka"})
    assert not _data_passed(question, {**data, "rows": [[19250]]})


def test_geo_passed_uses_district_extraction() -> None:
    question = Question(
        id="g1", type="geo", lang="sk", query="koľko v Petržalke?", district="Petržalka"
    )
    assert _geo_passed(question)


def test_load_questions_parses_typed_cases(tmp_path) -> None:
    path = tmp_path / "q.jsonl"
    path.write_text(
        '{"id": "d", "type": "data", "query": "q", "gold": "14 302"}\n',
        encoding="utf-8",
    )
    questions = load_questions(path)
    assert questions[0].type == "data"
    assert questions[0].gold == "14 302"
    assert questions[0].expect == []


def test_load_questions_rejects_unknown_type(tmp_path) -> None:
    path = tmp_path / "q.jsonl"
    path.write_text('{"id": "x", "type": "bogus", "query": "q"}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_questions(path)


def test_percentile_bounds() -> None:
    assert _percentile([], 0.5) == 0.0
    assert _percentile([10.0], 0.9) == 10.0
    assert _percentile([0.0, 100.0], 0.5) == 50.0


def test_aggregate_reports_per_type_metrics() -> None:
    details = [
        {
            "id": "q1",
            "type": "discovery",
            "hit": 1.0,
            "rr": 1.0,
            "ndcg": 1.0,
            "retrieval_ms": 10.0,
        },
        {
            "id": "d1",
            "type": "data",
            "hit": 0.0,
            "rr": 0.0,
            "ndcg": 0.0,
            "retrieval_ms": 20.0,
            "data_ms": 30.0,
            "passed": True,
        },
        {
            "id": "a1",
            "type": "abstain",
            "hit": 0.0,
            "rr": 0.0,
            "ndcg": 0.0,
            "retrieval_ms": 5.0,
            "data_ms": 7.0,
            "passed": False,
        },
    ]
    report = _aggregate(details, top_k=10, candidates=20, rerank=False)
    assert report["recall@k"] == 1.0
    assert report["execution_accuracy"] == 1.0
    assert report["abstention_accuracy"] == 0.0
    assert report["latency"]["data_ms"]["p50"] == 18.5
    assert report["by_type"]["data"]["passed"] == 1


def test_write_report_adds_timestamp(tmp_path) -> None:
    path = write_report({"questions": 1}, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["questions"] == 1
    assert "generated_at" in payload
