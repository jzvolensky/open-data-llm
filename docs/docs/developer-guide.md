---
title: Developer guide
sidebar_label: Developer guide
---

# Developer guide

How the project is organised and where to change things.

## Repository layout

```
.
├── config.yaml                # all runtime options (see below)
├── Makefile                   # setup / pipeline / pack / docs targets
├── pyproject.toml             # deps, extras, `bdata` entry point
├── scripts/pack.py            # knowledge-pack build/restore
├── src/opendata_llm/
│   ├── cli.py                 # Typer commands
│   ├── config.py              # typed config loader
│   ├── http.py                # httpx client (retries, capped downloads)
│   ├── store.py               # DuckDB catalog + schema
│   ├── text.py                # HTML strip, JSON-LD unwrap, date parsing
│   ├── ingest/                # dcat.py, search.py, features.py, download.py, catalog.py
│   ├── semantic/              # vocab.py (concepts), graph.py (knowledge graph)
│   ├── index/                 # cards.py, embed.py, store.py, pipeline.py
│   ├── retrieve/              # hybrid.py (RRF), rerank.py (cross-encoder)
│   ├── query/                 # load.py (CSV->DuckDB), sql.py, arcgis.py
│   ├── geo/                   # gazetteer.py, layers.py, query.py, spatial.py
│   ├── generate/              # router.py, prompts.py, rag.py, mlx_provider.py
│   ├── app/api.py             # FastAPI (/search, /ask, /ask/stream)
│   ├── mcp_server.py          # MCP tools
│   └── eval/                  # run.py, questions.jsonl
├── tests/
├── data/                      # catalog.duckdb, downloads/, raw/ (gitignored)
├── models/                    # local model (gitignored)
└── docs/                      # this Docusaurus site (EN + SK)
```

## Module map

| Area | Entry point | Notes |
| --- | --- | --- |
| Ingest | `ingest/catalog.py` | merges DCAT + Hub search into `datasets` |
| Vocabulary | `semantic/vocab.py` | 19 SK/EN concepts, districts, folding |
| Graph | `semantic/graph.py` | nodes/edges: concepts, publishers, similar, related |
| Cards | `index/cards.py` | the text that gets embedded and indexed |
| Retrieval | `retrieve/hybrid.py` | vector + BM25 + concepts + places, fused with RRF |
| Data plane | `query/` | CSV→DuckDB views, read-only SQL, live ArcGIS |
| Geospatial | `geo/` | gazetteer + `ST_Intersects` / `ST_Within` |
| Answering | `generate/rag.py` | retrieval, optional SQL, prompt assembly |
| Routing | `generate/router.py` | decides `data` / `geospatial` / `discovery` |

## Configuration

Everything lives in `config.yaml`; `config.py` provides typed defaults.

```yaml
portal:      # base_url, dcat_feed, search page size, user agent, timeouts
paths:       # db, raw cache, downloads
ingest:      # feature_concurrency, feature_request_delay
download:    # max_bytes per file, data_formats
embeddings:  # provider, model, host, dim, batch_size
search:      # top_k, candidates, rrf_k, rerank, rerank_model
generation:  # provider, model, max_tokens, temperature
```

Point the CLI at a different config with `--config path.yaml` (or `make build CONFIG=...`).

## Tuning retrieval

- `search.candidates` – how many results each retriever contributes before fusion.
  Lower = faster rerank; higher = better recall. Default 20.
- `search.top_k` – results returned to the answer / UI.
- `search.rrf_k` – RRF smoothing constant (60 is a safe default).
- `search.rerank` – turn the cross-encoder on/off. It is the biggest quality lever
  (see [Evaluation](/evaluation)) but adds latency.
- Concept and place signals are added automatically from `semantic/vocab.py`.

## Tuning generation

- `generation.max_tokens` – the main latency dial. Generation time scales with it;
  384 keeps answers short.
- `generation.temperature` – 0.2 is used for grounded, factual answers.
- Prompt wording lives in `generate/prompts.py` (`SYSTEM`, `SQL_SYSTEM`,
  `build_context`). Context size is capped by `CONTEXT_SOURCES` and `max_chars`.

## Tuning ingestion and downloads

- `download.max_bytes` – per-file cap (25 MB). Larger files stay available via the API.
- `download.data_formats` – which formats to fetch (CSV, GEOJSON, XLSX, TXT, KML).
- `ingest.feature_concurrency` – parallel layer-schema requests (mind politeness).
- `ingest.feature_request_delay` – add a delay if you hit rate limits.

## Data-path guardrails

For numeric questions the model writes SQL, but the result is **validated** before it is
trusted (`generate/rag.py`):

- the SQL must reference the candidate table;
- if the question names a district, it must filter a district-like column
  (`Katastrálne územie`, `KU`, `MESTSKA_CAST`, …) — the exact column and value are probed
  and passed to the model as a hint;
- the result must be non-empty; and
- a second model pass confirms the SQL actually answers the question.

Candidate tables are ranked by semantic retrieval + concept overlap + a lightweight
Slovak stemmer (`semantic/vocab.py`), and they use the **real cached CSV columns**. If no
candidate passes, the assistant says it cannot answer from cached data instead of
guessing. Computed results are returned with their SQL, table and filter as evidence.

## Router policy

`generate/router.py` decides whether the SQL path runs. The rules are deliberately
conservative: numeric cues → `data`; a **specific district** or explicit spatial phrase →
`geospatial`; otherwise `discovery`. Edit `DATA_CUES` / `GEO_CUES` to change behaviour,
and keep `rag.py`'s `intent == "data"` guard in mind — that is what keeps discovery
questions cheap.

## Adding a concept or alias

Concepts bridge Slovak and English. Add or extend an entry in
`semantic/vocab.py` (`Concept(...)`), then rebuild the graph and index:

```bash
make graph && make index
```

`category_concept` maps ArcGIS `/Categories/...` labels; `places_in` / `place_slug`
handle districts with inflection tolerance.

## Changing dataset cards

Cards are built in `index/cards.py` (`render_card`). Anything you add here becomes both
searchable (BM25) and embeddable, so keep it short and factual. Rebuild with
`make index`.

## Evaluation set

Extend `src/opendata_llm/eval/questions.jsonl` with `{id, lang, query, expect}` entries
(`expect` is a lowercase title substring). Run `bdata eval` and compare MRR/nDCG.

## Extending the interfaces

- **New generation backend** – implement `generate(messages, **kwargs)` (and optionally
  `stream`) in a class, then wire it into `build_generator` in `generate/__init__.py`.
- **New API route / MCP tool** – add to `app/api.py` or `mcp_server.py`; both reuse the
  same retrieval and data-plane helpers.
- **New CLI command** – add a `@app.command()` (or sub-`Typer`) in `cli.py`.

## Development workflow

```bash
make lint        # ruff
make typecheck   # mypy src
make test        # pytest
make docs-serve  # this site at http://localhost:3000
```

## Gotchas

- **DuckDB is single-writer** – don't run two pipeline commands against `catalog.duckdb`
  at once.
- **One MLX worker** – run uvicorn with a single process; a 12 GB model can't be shared
  across workers.
- **Model download** – use `HF_HUB_DISABLE_XET=1` (the Makefile does) if the transfer
  stalls.
- **`models/` and `data/` are gitignored** – share them via a knowledge pack or a release
  artifact, not git.
