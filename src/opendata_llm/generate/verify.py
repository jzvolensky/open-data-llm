"""Deterministic verification of a generated answer against retrieved evidence.

No model call is involved: every number in the answer must be present in, or derivable
from, the SQL result (normalizing ``14 302`` ↔ ``14302``), and every cited URL must be
one of the retrieved sources. Failures become warnings surfaced to the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..text import as_number

_URL = re.compile(r"https?://[^\s)\]}>\"']+")
#: A run of digits with optional thousands separators and a decimal part.
_NUMBER_RUN = re.compile(r"\d[\d\s\u00a0.,]*\d|\d")
#: Hex ids (ArcGIS item ids) that must not be read as numbers.
_HEX_ID = re.compile(r"\b[0-9a-f]{8,}\b", re.IGNORECASE)

MAX_WARNINGS = 5


@dataclass
class Verification:
    verified: bool
    warnings: list[str] = field(default_factory=list)


def _strip_noise(text: str) -> str:
    text = _URL.sub(" ", text)
    return _HEX_ID.sub(" ", text)


def numbers_in(text: str) -> list[float]:
    """Extract normalized numbers from free text, ignoring dates and ids."""
    found: list[float] = []
    for match in _NUMBER_RUN.findall(_strip_noise(text)):
        value = as_number(match)
        if value is not None:
            found.append(value)
    return found


def _derived(values: set[float]) -> set[float]:
    derived = set(values)
    total = sum(values)
    if values:
        derived.add(round(total, 1))
        derived.add(float(round(total)))
    numbers = [value for value in values if value != 0]
    if total:
        numbers.append(total)
    for left in numbers:
        derived.add(float(round(left)))
        for right in numbers:
            if left == right or right == 0:
                continue
            percentage = left / right * 100
            derived.add(round(percentage, 1))
            derived.add(float(round(percentage)))
    return derived


def evidence_numbers(evidence: Any) -> set[float]:
    """Collect the numbers an answer may legitimately use from the evidence."""
    values: set[float] = set()
    if isinstance(evidence, dict):
        for row in evidence.get("rows") or []:
            for cell in row:
                number = as_number(cell)
                if number is not None:
                    values.add(number)
        row_count = evidence.get("row_count")
        count = as_number(row_count)
        if count is not None:
            values.add(count)
        values.update(numbers_in(str(evidence.get("sql") or "")))
    elif isinstance(evidence, str):
        values.update(numbers_in(evidence))
    return _derived(values)


def _allowed(number: float, allowed: set[float]) -> bool:
    if number in allowed:
        return True
    return any(abs(number - candidate) <= 0.05 for candidate in allowed)


def _url_in_sources(url: str, sources: list[dict[str, Any]]) -> bool:
    for source in sources:
        candidate = str(source.get("url") or "")
        if candidate and (
            url == candidate
            or url.startswith(candidate)
            or candidate.startswith(url)
        ):
            return True
    return False


def _format(number: float) -> str:
    return str(int(number)) if number.is_integer() else f"{number:g}"


def verify_answer(
    answer: str,
    evidence: Any = None,
    sources: list[dict[str, Any]] | None = None,
) -> Verification:
    """Check numbers and cited URLs in ``answer`` against the evidence and sources."""
    text = answer or ""
    allowed = evidence_numbers(evidence)
    warnings: list[str] = []

    for number in numbers_in(text):
        if not _allowed(number, allowed):
            warnings.append(f"číslo {_format(number)} nie je podložené výsledkom dopytu")

    for url in dict.fromkeys(_URL.findall(text)):
        if not _url_in_sources(url, sources or []):
            warnings.append(f"odkaz {url} nie je medzi použitými zdrojmi")

    unique = list(dict.fromkeys(warnings))
    return Verification(not unique, unique[:MAX_WARNINGS])
