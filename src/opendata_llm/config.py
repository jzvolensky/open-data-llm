from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class PortalConfig:
    base_url: str = "https://data.bratislava.sk"
    dcat_feed: str = "/api/feed/dcat-ap/2.1.1"
    search_collection: str = "dataset"
    search_page_size: int = 100
    user_agent: str = "open-data-llm/0.1"
    request_timeout: float = 60.0
    max_retries: int = 3


@dataclass
class PathsConfig:
    db: Path = Path("data/catalog.duckdb")
    raw: Path = Path("data/raw")
    downloads: Path = Path("data/downloads")

    def resolve(self, root: Path) -> None:
        self.db = _resolve(root, self.db)
        self.raw = _resolve(root, self.raw)
        self.downloads = _resolve(root, self.downloads)


@dataclass
class IngestConfig:
    feature_concurrency: int = 4
    feature_request_delay: float = 0.0


@dataclass
class DownloadConfig:
    max_bytes: int = 25 * 1024 * 1024
    data_formats: list[str] = field(
        default_factory=lambda: ["CSV", "GEOJSON", "XLSX", "TXT", "KML"]
    )


@dataclass
class EmbeddingsConfig:
    provider: str = "ollama"
    model: str = "bge-m3"
    host: str = "http://localhost:11434"
    dim: int = 1024
    batch_size: int = 16
    timeout: float = 180.0


@dataclass
class SearchConfig:
    top_k: int = 10
    candidates: int = 20
    rrf_k: int = 60
    rerank: bool = False
    rerank_model: str = "BAAI/bge-reranker-v2-m3"


@dataclass
class GenerationConfig:
    provider: str = "mlx"
    model: str = "mlx-community/EuroLLM-22B-Instruct-2512-mlx-4bit"
    max_tokens: int = 384
    temperature: float = 0.2


@dataclass
class Config:
    portal: PortalConfig = field(default_factory=PortalConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    ingest: IngestConfig = field(default_factory=IngestConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    root: Path = PACKAGE_ROOT

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        if path is None:
            candidate = Path.cwd() / "config.yaml"
            path = candidate if candidate.exists() else PACKAGE_ROOT / "config.yaml"
        path = Path(path)
        raw: dict[str, Any] = {}
        if path.exists():
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        cfg = cls(
            portal=_build(PortalConfig, raw.get("portal")),
            paths=_build(PathsConfig, raw.get("paths")),
            ingest=_build(IngestConfig, raw.get("ingest")),
            download=_build(DownloadConfig, raw.get("download")),
            embeddings=_build(EmbeddingsConfig, raw.get("embeddings")),
            search=_build(SearchConfig, raw.get("search")),
            generation=_build(GenerationConfig, raw.get("generation")),
            root=path.resolve().parent if path.exists() else PACKAGE_ROOT,
        )
        cfg.paths.resolve(cfg.root)
        return cfg


def _resolve(root: Path, value: Path) -> Path:
    return value if value.is_absolute() else (root / value)


def _build(cls: type, data: dict[str, Any] | None) -> Any:
    if not data:
        return cls()
    known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    kwargs = {k: v for k, v in data.items() if k in known}
    if cls is PathsConfig:
        kwargs = {k: Path(v) for k, v in kwargs.items()}
    return cls(**kwargs)
