"""Bilingual (SK/EN) controlled vocabulary for Bratislava open data.

The portal publishes free-text Slovak keywords, ArcGIS category paths and a
handful of English terms. This module maps all of them onto a small set of
canonical concepts so that a query in either language retrieves the same data.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_NON_WORD = re.compile(r"[^a-z0-9 ]+")


@dataclass(frozen=True)
class Concept:
    id: str
    sk: str
    en: str
    aliases: tuple[str, ...] = field(default_factory=tuple)

    @property
    def terms(self) -> tuple[str, ...]:
        return (self.sk, self.en, *self.aliases)


CONCEPTS: tuple[Concept, ...] = (
    Concept(
        "demografia",
        "Demografia",
        "Demographics",
        (
            "populacia",
            "obyvatelia",
            "obyvatelstvo",
            "population",
            "inhabitants",
            "residents",
            "migracia",
            "vek",
            "pohlavie",
            "domacnosti",
            "households",
            "narodenia",
            "umrtia",
        ),
    ),
    Concept(
        "doprava",
        "Doprava a komunikácie",
        "Transport and communications",
        (
            "doprava",
            "dopravne",
            "dopravna",
            "komunikacie",
            "mhd",
            "gtfs",
            "cyklo",
            "cyklotrasy",
            "cyklisti",
            "chodci",
            "parkovanie",
            "parking",
            "transport",
            "traffic",
            "cesty",
            "dopravne znacky",
            "scitace",
            "elektromobilita",
            "nabijacie stanice",
        ),
    ),
    Concept(
        "zivotne-prostredie",
        "Životné prostredie",
        "Environment",
        (
            "zivotne prostredie",
            "environment",
            "zelen",
            "green",
            "ovzdusie",
            "kvalita ovzdusia",
            "air quality",
            "emisie",
            "emissions",
            "odpad",
            "odpady",
            "waste",
            "voda",
            "water",
            "kanalizacia",
            "hluk",
            "noise",
        ),
    ),
    Concept(
        "vzdelavanie",
        "Vzdelávanie a šport",
        "Education and sport",
        (
            "skolstvo",
            "vzdelavanie",
            "education",
            "skoly",
            "schools",
            "materske skoly",
            "zakladne skoly",
            "gymnazia",
            "univerzity",
            "studenti",
            "ziaci",
            "jasle",
        ),
    ),
    Concept(
        "sport",
        "Šport",
        "Sport",
        (
            "sport",
            "sports",
            "ihriska",
            "sportoviska",
            "bazeny",
            "swimming",
            "telocvicne",
        ),
    ),
    Concept(
        "ekonomika",
        "Ekonomika a práca",
        "Economy and labour",
        (
            "ekonomika",
            "hospodarstvo",
            "financie",
            "finance",
            "budget",
            "rozpocet",
            "dane",
            "taxes",
            "praca",
            "employment",
            "zamestnanie",
            "nezamestnanost",
            "trh prace",
            "miestna ekonomika",
            "podnikanie",
            "business",
            "mzdy",
        ),
    ),
    Concept(
        "sprava-mesta",
        "Správa mesta a výstavba",
        "City administration and construction",
        (
            "sprava mesta",
            "vystavba",
            "urban",
            "uzemny plan",
            "planning",
            "building",
            "stavebne",
            "bytovy fond",
            "housing",
            "byvanie",
            "nehnutelnosti",
            "funkcne plochy",
        ),
    ),
    Concept(
        "kataster-pozemky",
        "Kataster a pozemky",
        "Cadastre and land parcels",
        (
            "parcela",
            "parcely",
            "parciel",
            "parcelne",
            "pozemok",
            "pozemky",
            "pozemkov",
            "kataster",
            "katastralne",
            "katastralne uzemie",
            "vlastnictvo",
            "cadastre",
            "parcel",
            "land parcel",
        ),
    ),
    Concept(
        "bezpecnost",
        "Bezpečnosť",
        "Safety and security",
        (
            "bezpecnost",
            "safety",
            "security",
            "kriminalita",
            "crime",
            "priestupky",
            "offences",
            "nehody",
            "accidents",
            "riziko",
            "risk",
            "citlivost",
            "poziar",
            "hasici",
        ),
    ),
    Concept(
        "socialne-sluzby",
        "Sociálne služby",
        "Social services",
        (
            "socialne sluzby",
            "socialne",
            "social services",
            "socialna starostlivost",
            "seniori",
            "elderly",
            "deti",
            "znevyhodneni",
        ),
    ),
    Concept(
        "zdravie",
        "Zdravie",
        "Health",
        (
            "zdravie",
            "zdravotnictvo",
            "health",
            "healthcare",
            "nemocnice",
            "hospitals",
            "lekari",
            "ambulancie",
        ),
    ),
    Concept(
        "historia-kultura",
        "História a kultúra",
        "History and culture",
        (
            "historia",
            "history",
            "kultura",
            "culture",
            "pamiatky",
            "monuments",
            "heritage",
            "muzea",
            "divadla",
            "kniznice",
        ),
    ),
    Concept(
        "technicka-mapa",
        "Technická mapa",
        "Technical map and utilities",
        (
            "technicka mapa",
            "inzinierske siete",
            "utilities",
            "kolektory",
            "vodovod",
            "plyn",
            "elektrina",
            "siet",
            "engineering networks",
            "kataster",
            "cadastre",
        ),
    ),
    Concept(
        "klima-energia",
        "Klíma a energia",
        "Climate and energy",
        (
            "klima",
            "zmena klimy",
            "climate",
            "climate change",
            "energia",
            "energy",
            "secap",
            "obnovitelne zdroje",
            "renewables",
            "solar",
            "emisie",
        ),
    ),
    Concept(
        "zmluvy",
        "Zmluvy a obstarávanie",
        "Contracts and procurement",
        (
            "zmluvy",
            "zmluva",
            "contracts",
            "objednavky",
            "orders",
            "faktury",
            "invoices",
            "obstaravanie",
            "procurement",
            "tendre",
        ),
    ),
    Concept(
        "verejna-sprava",
        "Vláda a verejný sektor",
        "Government and public sector",
        (
            "vlada",
            "government",
            "verejny sektor",
            "public sector",
            "zastupitelstvo",
            "council",
            "volby",
            "elections",
            "poslanci",
        ),
    ),
    Concept(
        "mapy-gis",
        "Mapy a GIS",
        "Maps and GIS",
        (
            "mapy",
            "maps",
            "gis",
            "geospatial",
            "geodata",
            "regiony a mesta",
            "regions",
            "kataster",
            "ortofoto",
        ),
    ),
    Concept(
        "analytika",
        "Analytika a prognózy",
        "Analytics and forecasts",
        (
            "analytika",
            "analytics",
            "analysis",
            "prognoza",
            "forecast",
            "predikcia",
            "indikatory",
            "indicators",
        ),
    ),
    Concept(
        "open-data",
        "Otvorené dáta",
        "Open data",
        (
            "opendata",
            "open data",
            "publikacne minimum",
            "metadata",
        ),
    ),
    Concept(
        "bratislava-2050",
        "Bratislava 2050",
        "Bratislava 2050",
        ("bratislava 2050", "plan 2050"),
    ),
)

CONCEPT_BY_ID: dict[str, Concept] = {c.id: c for c in CONCEPTS}

#: Bratislava city districts (mestské časti) used for geospatial resolution.
PLACES: dict[str, str] = {
    "stare-mesto": "Staré Mesto",
    "ruzinov": "Ružinov",
    "vrakuna": "Vrakuňa",
    "podunajske-biskupice": "Podunajské Biskupice",
    "nove-mesto": "Nové Mesto",
    "raca": "Rača",
    "vajnory": "Vajnory",
    "devinska-nova-ves": "Devínska Nová Ves",
    "devin": "Devín",
    "dubravka": "Dúbravka",
    "karlova-ves": "Karlova Ves",
    "lamac": "Lamač",
    "zahorska-bystrica": "Záhorská Bystrica",
    "petrzalka": "Petržalka",
    "jarovce": "Jarovce",
    "rusovce": "Rusovce",
    "cunovo": "Čunovo",
    "bratislava": "Bratislava",
}


def fold(text: str) -> str:
    """Lowercase and strip diacritics, keeping only [a-z0-9 ]."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_WORD.sub(" ", ascii_text).strip()


_SUFFIXES = (
    "iami",
    "ach",
    "ami",
    "eho",
    "emu",
    "ych",
    "ymi",
    "iel",
    "ym",
    "ej",
    "ou",
    "ov",
    "om",
    "mi",
    "am",
    "ie",
    "ia",
    "iu",
    "y",
    "e",
    "a",
    "u",
    "o",
    "i",
)


def stem(word: str) -> str:
    """Reduce a (possibly inflected) Slovak word to an approximate stem."""
    folded = fold(word)
    for suffix in _SUFFIXES:
        if len(folded) - len(suffix) >= 3 and folded.endswith(suffix):
            return folded[: -len(suffix)]
    return folded


def stems_match(a: str, b: str) -> bool:
    """True if two words likely share a stem (handles Slovak inflection)."""
    sa, sb = stem(a), stem(b)
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    if len(sa) < 3 or len(sb) < 3:
        return False
    return sa.startswith(sb) or sb.startswith(sa)


def build_term_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for concept in CONCEPTS:
        for term in concept.terms:
            index.setdefault(fold(term), concept.id)
    return index


_TERM_INDEX = build_term_index()


def canonicalize(term: str | None) -> str | None:
    """Return the concept id for an exact (folded) term, else ``None``."""
    if not term:
        return None
    return _TERM_INDEX.get(fold(term))


def category_concept(category: str) -> str | None:
    label = category.rsplit("/", 1)[-1]
    return canonicalize(label)


def concepts_in(text: str | None) -> set[str]:
    """Find all concepts whose terms occur in ``text`` (word-boundary match)."""
    if not text:
        return set()
    padded = f" {fold(text)} "
    found: set[str] = set()
    for term, concept_id in _TERM_INDEX.items():
        if f" {term} " in padded:
            found.add(concept_id)
    return found


def places_in(text: str | None) -> set[str]:
    """Match district names, tolerating Slovak inflection.

    Handles single words (``Ružinove`` -> Ružinov) and multi-word names with
    inflection or reordered words (``Záhorskej Bystrici`` -> Záhorská Bystrica,
    ``Novom Meste`` -> Nové Mesto).
    """
    if not text:
        return set()
    folded = fold(text)
    padded = f" {folded} "
    words = folded.split()
    word_stems = [stem(word) for word in words]
    found: set[str] = set()
    for slug, label in PLACES.items():
        term = fold(label)
        if " " not in term:
            if any(stems_match(word, term) for word in words):
                found.add(slug)
            continue
        if f" {term} " in padded:  # exact phrase fast path
            found.add(slug)
            continue
        needed = [stem(part) for part in term.split()]
        matched = [n for n in needed if any(stems_match(n, ws) for ws in word_stems)]
        # Either every word of the district matches, or a distinctive (longer)
        # word matches, which tolerates short generic words (e.g. "Ves", "Mesto").
        if len(matched) == len(needed) or (
            len(needed) >= 2 and any(len(n) >= 5 for n in matched)
        ):
            found.add(slug)
    return found


def place_slug(name: str | None) -> str | None:
    """Map a district label (e.g. from geometry) to its slug."""
    if not name:
        return None
    folded = fold(name)
    for slug, label in PLACES.items():
        if fold(label) == folded:
            return slug
    found = places_in(name)
    if not found:
        return None
    # Prefer the most specific (longest) match, e.g. Devínska Nová Ves over Devín.
    return max(found, key=lambda slug: len(fold(PLACES[slug])))


def label_for(concept_id: str, lang: str = "sk") -> str:
    concept = CONCEPT_BY_ID.get(concept_id)
    if not concept:
        return concept_id
    return concept.en if lang == "en" else concept.sk
