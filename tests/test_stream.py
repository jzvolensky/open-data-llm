from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import opendata_llm.generate.rag as rag
from opendata_llm.config import Config
from opendata_llm.retrieve.hybrid import SearchResult


class FakeGenerator:
    def generate(self, messages: Sequence[dict[str, str]], **kwargs: Any) -> str:
        return "ANSWER"

    def stream(self, messages: Sequence[dict[str, str]], **kwargs: Any):
        yield "Hello "
        yield "world"


def test_stream_events_ordering(monkeypatch) -> None:
    monkeypatch.setattr(
        rag,
        "_retrieve",
        lambda *a, **k: [
            SearchResult(dataset_id="d1", score=1.0, title="T", url="u", card="c")
        ],
    )
    config = Config.load()
    events = list(rag.stream_events(config, None, "datasets about transport", FakeGenerator()))

    names = [event["event"] for event in events]
    assert names[0] == "status"
    assert "sources" in names
    assert names[-1] == "done"
    # The answer streams only after the sources event.
    assert names.index("sources") < names.index("token")
    # A deterministic verification event follows the answer.
    assert names.index("token") < names.index("verification") < names.index("done")

    text = "".join(e["text"] for e in events if e["event"] == "token")
    assert text == "Hello world"
