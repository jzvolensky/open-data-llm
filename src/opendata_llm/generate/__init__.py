"""Generation providers (MLX EuroLLM by default)."""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from .base import Generator


def resolve_model(config: Config) -> str:
    """Return a local model path if it exists, else the raw identifier."""
    candidate = Path(config.generation.model)
    if not candidate.is_absolute():
        candidate = config.root / candidate
    return str(candidate) if candidate.exists() else config.generation.model


def build_generator(config: Config) -> Generator:
    provider = config.generation.provider.lower()
    if provider == "mlx":
        from .mlx_provider import MLXGenerator

        return MLXGenerator(
            model_id=resolve_model(config),
            max_tokens=config.generation.max_tokens,
            temperature=config.generation.temperature,
        )
    if provider in ("fake", "offline", "echo"):
        from .fake import EchoGenerator

        return EchoGenerator()
    raise ValueError(f"unknown generation provider: {provider!r}")


__all__ = ["Generator", "build_generator"]
