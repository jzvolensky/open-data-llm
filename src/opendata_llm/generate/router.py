"""Lightweight intent router for SK/EN queries.

Intent decides whether the expensive SQL path runs, so the policy is deliberately
conservative: only clear numeric questions go to ``data``; ``geospatial`` requires a
specific district or explicit spatial phrasing; everything else is ``discovery``.
"""

from __future__ import annotations

from ..semantic import vocab

DATA_CUES = (
    "koľko",
    "kolko",
    "how many",
    "how much",
    "priemer",
    "average",
    "sucet",
    "súčet",
    "sum",
    "total",
    "podiel",
    "percent",
    "trend",
    "v roku",
    "in 20",
    "najviac",
    "najmenej",
    "maximum",
    "minimum",
    "top ",
    "počet",
    "pocet",
    "count",
)

# Explicit spatial phrasing only. "kde/where/find" are *lookup* words, not spatial
# intent, so they are intentionally absent.
GEO_CUES = (
    "blízko",
    "near",
    "súradnice",
    "suradnice",
    "coordinates",
    "mestská časť",
    "mestskej časti",
    "mestských častí",
    "v okolí",
    "katastrálne",
)


def classify(query: str) -> str:
    lowered = query.lower()
    if any(cue in lowered for cue in DATA_CUES):
        return "data"
    # "Bratislava" alone is city-wide, not a district, so it does not imply spatial intent.
    districts = vocab.places_in(query) - {"bratislava"}
    if districts or any(cue in lowered for cue in GEO_CUES):
        return "geospatial"
    return "discovery"
