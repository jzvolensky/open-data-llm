"""Embedding client backed by Ollama (default: bge-m3, multilingual)."""

from __future__ import annotations

from typing import Any

import httpx


class OllamaEmbedder:
    def __init__(
        self,
        model: str = "bge-m3",
        host: str = "http://localhost:11434",
        timeout: float = 180.0,
        batch_size: int = 16,
    ) -> None:
        self.model = model
        self.batch_size = batch_size
        self._client = httpx.Client(base_url=host, timeout=timeout)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = self._client.post(
                "/api/embed", json={"model": self.model, "input": batch}
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            embeddings = payload.get("embeddings")
            if not embeddings:
                raise RuntimeError(f"Ollama returned no embeddings: {payload}")
            vectors.extend(embeddings)
        return vectors

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OllamaEmbedder:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
