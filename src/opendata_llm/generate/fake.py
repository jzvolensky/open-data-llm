from __future__ import annotations

from collections.abc import Sequence

from .base import Message


class EchoGenerator:
    """Deterministic offline generator for tests and environments without MLX."""

    def generate(self, messages: Sequence[Message], **kwargs: object) -> str:
        last = messages[-1]["content"] if messages else ""
        return f"[offline] {last[:500]}"
