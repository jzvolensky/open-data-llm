from __future__ import annotations

from opendata_llm.retrieve.hybrid import reciprocal_rank_fusion


def test_rrf_prefers_items_in_multiple_lists() -> None:
    dense = ["a", "b", "c"]
    bm25 = ["b", "a", "d"]
    fused = reciprocal_rank_fusion([dense, bm25], k=60)
    ranked = sorted(fused, key=lambda key: -fused[key])
    assert ranked[:2] == ["a", "b"] or ranked[:2] == ["b", "a"]
    assert ranked[-1] == "c" or ranked[-1] == "d"


def test_rrf_empty() -> None:
    assert reciprocal_rank_fusion([]) == {}
