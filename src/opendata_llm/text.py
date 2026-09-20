from __future__ import annotations

import html as _html
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlparse

_BLOCK_TAGS = {
    "br",
    "p",
    "div",
    "li",
    "tr",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "table",
}


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def strip_html(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    parser = _Stripper()
    parser.feed(value)
    parser.close()
    text = _html.unescape(parser.text())
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def scalar(value: Any) -> Any:
    """Unwrap JSON-LD structures (``@value``/``@id``/``prefLabel``) to plain values."""
    if value is None:
        return None
    if isinstance(value, dict):
        if "@value" in value:
            return scalar(value["@value"])
        if "@id" in value:
            return value["@id"]
        if "skos:prefLabel" in value:
            return scalar(value["skos:prefLabel"])
        if "foaf:name" in value:
            return scalar(value["foaf:name"])
        return None
    if isinstance(value, list):
        unwrapped = [scalar(item) for item in value]
        return [item for item in unwrapped if item is not None]
    return value


def first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def extract_item_id(url: Any) -> str | None:
    """Pull the 32-hex ArcGIS item id out of an item URL query string."""
    if not url or not isinstance(url, str):
        return None
    try:
        query = parse_qs(urlparse(url).query)
    except ValueError:
        return None
    return query.get("id", [None])[0]


def parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def language_code(value: Any) -> str | None:
    if not value or not isinstance(value, str):
        return None
    return value.rsplit("/", 1)[-1] or None
