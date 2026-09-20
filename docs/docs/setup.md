---
title: Setup
sidebar_label: Setup
---

# Setup

This page walks through a full local setup. The `Makefile` wraps every step, but each
command is shown so you can run them individually.

## Prerequisites

| Requirement | Why |
| --- | --- |
| macOS on Apple Silicon, **32 GB** RAM recommended | MLX generation; the 22B model is ~12.7 GB |
| [`uv`](https://docs.astral.sh/uv/) | Python 3.12 environment and dependencies |
| [Ollama](https://ollama.com) running | serves the `bge-m3` embedding model |
| Node 20+ | only for building this documentation site |

```bash
# once
brew install uv
brew install ollama
ollama serve &            # if not already running as a service
ollama pull bge-m3        # embedding model (~1.2 GB)
```

## 1. Install dependencies

```bash
make setup
# equivalent to: uv sync --extra dev,rerank,mlx,api,mcp
```

This installs everything: retrieval, the MLX runtime, the reranker, the API and MCP.

## 2. Download the generation model

This is a separate step because it is ~12 GB. It is resumable — re-run it if interrupted.

```bash
make model
# downloads mlx-community/EuroLLM-22B-Instruct-2512-mlx-4bit into models/EuroLLM-22B-4bit
```

The download uses plain HTTP (`HF_HUB_DISABLE_XET=1`) because the Xet transfer path can
stall on some connections.

## 3. Build the data pipeline

```bash
make build
```

Runs the stages in order (each is also available on its own):

| Step | Command | What it does |
| --- | --- | --- |
| 1 | `make ingest` | DCAT feed + Hub search + ArcGIS layer schemas |
| 2 | `make download` | distribution files, 25 MB per-file cap |
| 3 | `make graph` | concepts, place links, similarity + curated edges |
| 4 | `make data` | exposes downloaded CSVs as DuckDB views |
| 5 | `make index` | dataset cards, `bge-m3` embeddings, BM25 (uses the real CSV schema) |
| 6 | `make geo` | district gazetteer and spatial layers |

Expected scale: ~669 datasets, ~4,860 distributions, ~620 layer schemas, ~2,060
downloaded files.

:::tip Partial builds
Run only what you need. For discovery-only use, `make ingest && make graph && make index`
is enough; the data and geo steps enable SQL and spatial questions.
:::

## 4. Run it

`make setup` installs `bdata` into the project virtualenv (`.venv/bin/bdata`), so it is on
`PATH` only when that environment is active. Either prefix commands with `uv run`, or
activate the venv once per shell:

```bash
source .venv/bin/activate
```

```bash
bdata ask "Koľko priestupkov bolo v Ružinove v roku 2025?"
bdata search "air quality"
bdata serve          # web UI + API at http://127.0.0.1:8000
bdata mcp            # MCP server over stdio
```

Or via make:

```bash
make ask Q="Kde nájdem údaje o školstve?"
make serve           # PORT=9000 to change the port
```

## 5. Verify

```bash
bdata status         # dataset/format counts
bdata eval           # retrieval metrics (recall@k, MRR, nDCG)
make test            # unit tests
```

## Troubleshooting

- **`catalog not found`** – run `make build` (or at least `make ingest`).
- **Embedding errors / connection refused** – make sure `ollama serve` is running and
  `ollama pull bge-m3` has completed.
- **First answer is slow** – the 22B model and reranker are loaded on first use. The API
  warms both at startup; `bdata ask` loads per invocation by design.
- **Generation is very slow / memory pressure** – close other large apps; the model needs
  ~13 GB resident.
