from __future__ import annotations

from opendata_llm.generate.rag import _district, _grounded, _query_stems, _stem_overlap


def test_query_stems_handle_inflection() -> None:
    stems = _query_stems("vie mi povedat kolko parciel sa nachadza v petrzalke?")
    assert any(stem.startswith("parc") for stem in stems)
    assert "petrzalk" not in stems  # place words are excluded from dataset scoring


def test_stem_overlap_matches_dataset_titles() -> None:
    assert _stem_overlap(["parc"], "Parcely vo vlastníctve hlavného mesta") >= 1
    assert _stem_overlap(["obytn"], "Počet bytov podľa obytnej plochy") >= 1
    assert _stem_overlap(["doprav"], "Parcely vo vlastníctve mesta") == 0


def test_district_extraction_excludes_city_wide() -> None:
    assert _district("koľko parciel je v Petržalke?") == "Petržalka"
    assert _district("koľko parciel je v Bratislave?") is None


def test_district_multiword_and_specificity() -> None:
    assert _district("koľko pozemkov v Záhorskej Bystrici?") == "Záhorská Bystrica"
    assert _district("koľko v Novom Meste?") == "Nové Mesto"
    assert _district("koľko v Starom Meste?") == "Staré Mesto"
    # Must prefer the specific district over the shorter, overlapping one.
    assert _district("koľko v Devínskej Novej Vsi?") == "Devínska Nová Ves"


def test_grounding_requires_district_filter() -> None:
    table = "ds_x_csv"
    target = ("Katastrálne územie", "Petržalka")
    good = f"SELECT count(*) FROM {table} WHERE \"Katastrálne územie\" = 'Petržalka'"
    bad = f"SELECT count(*) FROM {table}"
    assert _grounded(table, good, "Petržalka", target) is True
    assert _grounded(table, bad, "Petržalka", target) is False
    assert _grounded("ds_y_csv", good, "Petržalka", target) is False
    assert _grounded(table, bad, None, None) is True
