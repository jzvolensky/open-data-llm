from __future__ import annotations

from opendata_llm.semantic import vocab


def test_canonicalize_sk_and_en() -> None:
    assert vocab.canonicalize("Doprava") == "doprava"
    assert vocab.canonicalize("transport") == "doprava"
    assert vocab.canonicalize("Životné prostredie") == "zivotne-prostredie"
    assert vocab.canonicalize("environment") == "zivotne-prostredie"


def test_category_concept_from_arcgis_path() -> None:
    assert vocab.category_concept("/Categories/Doprava a komunikácie") == "doprava"
    assert vocab.category_concept("/Categories/Demografia") == "demografia"
    assert vocab.category_concept("/Categories/Územný plán") == "sprava-mesta"


def test_concepts_in_text_bilingual() -> None:
    assert "zivotne-prostredie" in vocab.concepts_in("kvalita ovzdušia a zeleň")
    assert "zdravie" in vocab.concepts_in("hospitals and clinics")
    assert vocab.concepts_in("") == set()


def test_places_in() -> None:
    assert vocab.places_in("počet priestupkov v Ružinove") == {"ruzinov"}
    assert "petrzalka" in vocab.places_in("Petržalka")


def test_place_slug() -> None:
    assert vocab.place_slug("Ružinov") == "ruzinov"
    assert vocab.place_slug("Staré Mesto") == "stare-mesto"
    assert vocab.place_slug("Bratislava") == "bratislava"
    assert vocab.place_slug("Nowhere") is None


def test_stem_and_stems_match_handle_slovak_inflection() -> None:
    assert vocab.stems_match("parciel", "Parcely")
    assert vocab.stems_match("obytných", "obytnej")
    assert vocab.stems_match("Petržalke", "Petržalka")
    assert not vocab.stems_match("parciel", "doprava")


def test_kataster_concept_exists() -> None:
    assert vocab.canonicalize("parcely") == "kataster-pozemky"
    assert vocab.canonicalize("pozemky") == "kataster-pozemky"
    assert vocab.canonicalize("kataster") == "kataster-pozemky"
