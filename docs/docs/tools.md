---
title: Tools
sidebar_label: Tools
---

# Tools

| Tool | Role | Why this one |
| --- | --- | --- |
| **Python 3.12 + uv** | language + dependency management | fast, reproducible installs; simple CLI scripts |
| **DuckDB** | catalog, graph, vectors, FTS, cached data | single local file, no server; `fts`, `spatial` and array math in one engine |
| **httpx** | HTTP client | connection pooling, timeouts, streaming downloads with a size cap |
| **Typer + Rich** | CLI | typed commands and readable tables with little code |
| **FastAPI + uvicorn** | web API | `POST /search`, `POST /ask`, `POST /ask/stream` (the ask routes accept optional conversation `history`); small, typed, easy to run locally |
| **MCP SDK** | agent integration | expose tools to MCP clients without a custom protocol |
| **Docusaurus** | this documentation | Markdown docs with built-in i18n (EN/SK) |
| **mlx-lm** | model runtime on Apple Silicon | native Metal inference; no Ollama needed for generation |
| **sentence-transformers** | cross-encoder reranking | best-in-class reranking, runs locally |
| **Ollama** | embedding server | serves `bge-m3` embeddings over a simple HTTP API |

## DuckDB extensions used

- `fts` – BM25 full-text index over the dataset cards.
- `spatial` – district polygons, `ST_Intersects`, `ST_Within`, `ST_Read` for GeoJSON.

## Notes

- Everything runs locally. The only network calls are ingestion, downloads, and the
  embedding endpoint (`http://localhost:11434`).
- The SQL interface is **read-only**: statements must start with `SELECT/WITH/DESCRIBE`,
  and write keywords are rejected.
- The cross-encoder and the MLX runtime are optional extras, so the core tool works
  without heavy dependencies.
- Answer trust is rule-based: `generate/verify.py` checks numbers and cited URLs against
  the retrieved evidence, and `query/profile.py` supplies the low-cardinality value
  dictionary (`column_values`) used for exact filtering — no extra model calls.
