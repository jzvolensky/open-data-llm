from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

Message = dict[str, str]


class Generator(Protocol):
    def generate(self, messages: Sequence[Message], **kwargs: Any) -> str: ...
