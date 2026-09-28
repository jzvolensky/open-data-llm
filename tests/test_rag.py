from __future__ import annotations

from opendata_llm.generate.rag import (
    _ambiguity,
    _district,
    _grounded,
    _normalize_sql,
    _pick_category_column,
    _query_stems,
    _requested_category,
    _stem_overlap,
    _value_lines,
)


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


def test_normalize_sql_fixes_single_quoted_identifiers() -> None:
    columns = ["Katastrálne územie", "ROK"]
    sql = "SELECT * FROM t WHERE 'Katastrálne územie' = 'Petržalka'"
    assert _normalize_sql(sql, columns) == (
        'SELECT * FROM t WHERE "Katastrálne územie" = \'Petržalka\''
    )


def test_pick_category_column_prefers_label_over_code() -> None:
    profiled = {
        "Druh pozemku - kód": ["13.0", "14.0"],
        "Druh pozemku - názov": ["Záhrady", "Orná pôda"],
    }
    assert _pick_category_column(profiled) == "Druh pozemku - názov"


def test_requested_category_detects_unknown_modifier() -> None:
    profiled = {
        "Druh pozemku - kód": ["13.0", "14.0"],
        "Druh pozemku - názov": ["Zastavané plochy a nádvoria", "Lesné pozemky"],
    }
    title = "Pozemky vo vlastníctve hlavného mesta"
    assert _requested_category("Koľko obytných pozemkov?", title, profiled) == (
        "Druh pozemku - názov",
        "obytných",
    )
    # A known value, a district and a plain count question are not category misses.
    assert _requested_category("Koľko lesných pozemkov?", title, profiled) is None
    assert _requested_category("Koľko pozemkov v Petržalke?", title, profiled) is None


def test_ambiguity_flags_unknown_filter_value() -> None:
    profiled = {"Druh": ["A", "B"]}
    assert _ambiguity('SELECT * FROM t WHERE "Druh" = \'C\'', profiled) == ("Druh", "C")
    assert _ambiguity('SELECT * FROM t WHERE "Druh" = \'A\'', profiled) is None


def test_value_lines_require_whole_words() -> None:
    profiled = {
        "Katastrálne územie": ["Petržalka", "Ružinov"],
        "Správa - názov": ["vlastnı"],
    }
    assert _value_lines(profiled, "Zaujíma ma Ružinov") == [
        'Prípustné hodnoty stĺpca "Katastrálne územie": \'Ružinov\'. '
        "Použi presne uvedený tvar."
    ]
    # Inflected district and a noisy partial value must not become filter hints.
    assert _value_lines(profiled, "koľko pozemkov v Petržalke vlastní mesto") == []
