---
title: Packaging & sharing
sidebar_label: Packaging
---

# Packaging & sharing

## Can the RAG be saved into the model?

No — RAG is **retrieval plus a model**, and the knowledge lives in the **index**, not the
model weights. There is nothing to write into the model without training it. The three
realistic options:

| Option | What it gives you | Trade-offs |
| --- | --- | --- |
| **Fine-tune / LoRA** | facts and style baked into weights | goes stale as the portal updates; **no citations**; can't run the SQL data plane; needs training |
| **Knowledge pack** (this project) | portable index: cards, embeddings, graph, cached tables | needs the model alongside it; re-pack after a refresh |
| **Both** | a pack for facts, a small LoRA for behaviour | most work; best of both |

A fine-tune is a poor fit for facts here: the portal's `dct:modified` dates change
continuously, citations matter, and numeric questions are answered with SQL, not
generation. Use a pack, and keep the model swappable.

## What is in a pack

`make pack` produces `release/bdata-pack-<date>.tar.gz` containing:

```
bdata-pack/
  catalog.duckdb     # datasets, cards, embeddings, graph, gazetteer
  config.yaml        # the producing configuration
  MANIFEST.json      # counts, model ids, checksums, git rev, timestamp
  NOTICE             # CC BY 4.0 attribution
```

The metadata pack is small (~5 MB). Cached-table views, the `data_tables` registry and the
derived `column_values` dictionary are intentionally dropped so the pack is self-consistent
without the CSV files; run `make download && make data` after restoring if you want the
data plane — including exact-value matching — offline.

## Build and restore

```bash
make pack            # metadata pack (~5 MB)
make pack FULL=1     # also include data/downloads (offline data plane, ~800 MB)

# on another machine / checkout
make restore PACK=release/bdata-pack-20260920.tar.gz
```

`restore` writes `data/catalog.duckdb`, `config.yaml` (does not overwrite an existing one),
`MANIFEST.json`, `NOTICE` and — for a full pack — `data/downloads`. Then install deps and
the model as usual (`make setup`, `make model`).

## Freshness

The pack is a snapshot. Refresh it by re-running the pipeline and packing again:

```bash
make ingest && make graph && make index
make pack
```

Metadata changes daily; the `MANIFEST.json` timestamp and `git_rev` record exactly what a
pack contains.
