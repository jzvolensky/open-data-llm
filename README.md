# Bratislava Open Data LLM

A local, bilingual (Slovak / English) question-answering system over the open data of
the City of Bratislava ([data.bratislava.sk](https://data.bratislava.sk)).

It answers **what data exists**, **how many / where** (SQL over cached tables or the live
ArcGIS API) and **which datasets cover a district**, with citations and licence. The whole
stack runs locally — the only network calls are ingestion, downloads and the embedding
endpoint.

- Documentation: [`docs/`](docs/) (Docusaurus, EN + SK)
- CLI: `bdata`

## Requirements

- macOS on Apple Silicon (MLX generation) with **32 GB** RAM recommended
- [`uv`](https://docs.astral.sh/uv/) for Python 3.12
- [Ollama](https://ollama.com) running locally (serves `bge-m3` embeddings)
- Node 20+ only if you build the documentation
- ~16 GB free disk for the model (`models/`) plus ~1 GB for data

## Quick start

```bash
make setup     # install Python dependencies
make model     # download the generation model (12 GB, resumable, optional to start)
make build     # ingest -> download -> graph -> index -> data -> geo

bdata ask "Koľko priestupkov bolo v Ružinove v roku 2025?"
bdata serve    # web UI + API at http://127.0.0.1:8000
bdata mcp      # expose tools over MCP (stdio)
```

`make help` lists every target. Each pipeline stage is available on its own
(`make ingest`, `make index`, …) so you can run the project step by step.

## Common commands

| Command | Purpose |
| --- | --- |
| `bdata ingest catalog` / `ingest features` | DCAT feed, Hub search, layer schemas |
| `bdata download` | Distribution files (25 MB per-file cap) |
| `bdata graph build --with-related` | Knowledge graph |
| `bdata index build` | Cards, `bge-m3` embeddings, BM25 |
| `bdata data load` / `data sql` / `data live` | Cached tables and live ArcGIS |
| `bdata geo build` / `geo load` / `geo datasets` | District gazetteer and spatial queries |
| `bdata search "..."` / `bdata ask "..."` | Retrieval / grounded answer |
| `bdata eval` | Retrieval metrics on the gold question set |
| `bdata serve` / `bdata mcp` | Web API / MCP server |
| `make test` / `make lint` / `make typecheck` | Quality checks |
| `make docs` | Build the documentation site |

## Architecture (short)

Two planes behind a small intent router, because language search and counting need
different tools:

- **Catalog plane** — dataset cards, `bge-m3` vectors, BM25 and a knowledge graph over a
  bilingual controlled vocabulary; rescored by `bge-reranker-v2-m3`.
- **Data plane** — read-only SQL over locally cached CSVs, plus live ArcGIS FeatureServer
  queries for large or fresh data.

Generation is local via **MLX** (`EuroLLM-22B-Instruct`, 4-bit). See
[docs/architecture.md](docs/docs/architecture.md) for the full picture.

## Data and licence

Data is published by the **Magistrát hlavného mesta SR Bratislava** under
**CC BY 4.0**. Answers cite the source dataset; keep the attribution when reusing the
catalog or a knowledge pack.

## Packaging (RAG, not fine-tuning)

RAG is retrieval **plus** a model — the knowledge lives in the index, not the weights, so
it is shared as a **knowledge pack** rather than a single model file:

```bash
make pack            # metadata pack (~5 MB): catalog, cards, embeddings, graph
make pack FULL=1     # also include cached downloads for an offline data plane
```

The model stays a separate, swappable component. `/docs/packaging` explains the options
(pack vs. fine-tuning vs. both).

## Documentation

```bash
make docs-serve      # http://localhost:3000
make docs            # static build (EN + SK)
```

## License

Data: CC BY 4.0 (attribution above). Models retain their own licences
(EuroLLM, bge-m3, bge-reranker).
