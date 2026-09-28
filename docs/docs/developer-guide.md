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
│   ├── query/                 # load.py (CSV->DuckDB), profile.py (value dict), sql.py, arcgis.py
│   ├── geo/                   # gazetteer.py, layers.py, query.py, spatial.py
│   ├── generate/              # router.py, prompts.py, rag.py, verify.py, mlx_provider.py
│   ├── app/api.py             # FastAPI (/search, /ask, /ask/stream)
│   ├── mcp_server.py          # MCP tools
│   └── eval/                  # run.py (typed cases), questions.jsonl
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
| Value dictionary | `query/profile.py` | `column_values` for low-cardinality columns |
| Geospatial | `geo/` | gazetteer + `ST_Intersects` / `ST_Within` |
| Answering | `generate/rag.py` | rewrite, retrieval, optional SQL, prompt assembly |
| Verification | `generate/verify.py` | deterministic number/URL checks on answers |
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
- `generation.temperature` – 0.2 is used for grounded, factual answers. SQL generation and
  the follow-up rewrite are called with `temperature=0` (greedy) so results are stable.
- Prompt wording lives in `generate/prompts.py` (`SYSTEM`, `SQL_SYSTEM`, `REWRITE_SYSTEM`,
  `build_context`, `build_sql_messages`, `build_rewrite_messages`). Context size is capped
  by `CONTEXT_SOURCES` and `max_chars`.

## Tuning ingestion and downloads

- `download.max_bytes` – per-file cap (25 MB). Larger files stay available via the API.
- `download.data_formats` – which formats to fetch (CSV, GEOJSON, XLSX, TXT, KML).
- `ingest.feature_concurrency` – parallel layer-schema requests (mind politeness).
- `ingest.feature_request_delay` – add a delay if you hit rate limits.

## Data-path guardrails

For numeric questions the model writes SQL, but every step around it is deterministic
(`generate/rag.py`). The data path is only entered when the router classifies the question
as `data`, and then:

1. **Relevance gate** – a candidate table is considered only if the question's content
   stems overlap its title, card or schema. If none does, the assistant declines instead
   of forcing SQL onto an unrelated table.
2. **Value dictionary** – `query/profile.py` stores the distinct values of
   low-cardinality columns in `column_values`. Values the question quotes verbatim are
   offered to the model so it does not invent filter values.
3. **District resolution** – a district named in the question is matched to the exact
   stored spelling (via `column_values`, with an `ILIKE` fallback), and the model is told
   which column and value to filter.
4. **Grounding** – the SQL must reference the candidate table, and, when a district was
   named, filter a district-like column (`Katastrálne územie`, `KU`, `MESTSKA_CAST`, …).
   Identifiers the model wrapped in single quotes are normalized to double quotes.
5. **Non-empty result** – otherwise the assistant declines, unless the filter value was a
   **category that does not exist**, in which case it returns the real breakdown of that
   column and says the category is undefined.
6. **Deterministic verification** – the generated prose is checked by `generate/verify.py`:
   every number must be present in, or derivable from, the evidence, and every cited URL
   must be a retrieved source. Failures are annotated as `warnings`; no second model call
   is made.

Candidate tables are ranked by semantic retrieval + concept overlap + a lightweight
Slovak stemmer (`semantic/vocab.py`), and they use the **real cached CSV columns**.
Computed results are returned with their SQL, table and filter as evidence.

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

`src/opendata_llm/eval/questions.jsonl` is a typed gold set (`discovery`, `data`, `geo`,
`abstain`, `followup`). Discovery cases use `{id, lang, query, expect}`; answer cases add
`gold`, `dataset`, `district` and, for follow-ups, `history`. See
[Evaluation](/evaluation) for the full schema and metric definitions.

```bash
bdata eval --type discovery    # ranking only (fast, no model)
bdata eval --type data         # execution accuracy (loads the model)
bdata eval                     # all types; writes reports/eval/eval-<ts>.json
```

A `data` case should use a value you can verify against the cached table
(`bdata data sql "SELECT …"`). New answer cases do not affect the discovery metrics, which
are computed per type.

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
- **`column_values` is derived** – after `make download` adds tables, rerun
  `make data` (or `bdata data profile`) so exact-value matching stays current. Metadata
  packs drop it, so restore + `make data` to rebuild it locally.
