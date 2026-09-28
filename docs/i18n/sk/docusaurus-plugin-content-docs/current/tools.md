---
title: Nástroje
sidebar_label: Nástroje
---

# Nástroje

| Nástroj | Úloha | Prečo |
| --- | --- | --- |
| **Python 3.12 + uv** | jazyk + správa závislostí | rýchla, reprodukovateľná inštalácia; jednoduché CLI skripty |
| **DuckDB** | katalóg, graf, vektory, FTS, uložené dáta | jeden lokálny súbor bez servera; `fts`, `spatial` aj práca s poľami v jednom engine |
| **httpx** | HTTP klient | pooling spojení, timeouty, streamované sťahovanie s limitom |
| **Typer + Rich** | CLI | typované príkazy a čitateľné tabuľky s málo kódom |
| **FastAPI + uvicorn** | web API | `POST /search`, `POST /ask`, `POST /ask/stream` (ask rutiny prijímajú voliteľnú `history` konverzácie); malé a ľahko spustiteľné lokálne |
| **MCP SDK** | integrácia do agentov | sprístupní nástroje MCP klientom bez vlastného protokolu |
| **Docusaurus** | táto dokumentácia | Markdown dokumenty so vstavanou i18n (EN/SK) |
| **mlx-lm** | runtime modelu na Apple Silicon | natívna Metal inferencia; na generovanie nie je potrebný Ollama |
| **sentence-transformers** | reranking cross-encoderom | špičkový reranking, beží lokálne |
| **Ollama** | server embeddingov | poskytuje `bge-m3` embeddingy cez jednoduché HTTP API |

## Použité rozšírenia DuckDB

- `fts` – BM25 fulltextový index nad kartami datasetov.
- `spatial` – polygóny mestských častí, `ST_Intersects`, `ST_Within`, `ST_Read` pre GeoJSON.

## Poznámky

- Všetko beží lokálne. Sieť sa používa len na ingest, sťahovanie a embedding endpoint
  (`http://localhost:11434`).
- SQL rozhranie je **iba na čítanie**: príkazy musia začínať `SELECT/WITH/DESCRIBE`
  a zápisové kľúčové slová sú odmietnuté.
- Cross-encoder a MLX runtime sú voliteľné doplnky, takže jadro funguje aj bez ťažkých
  závislostí.
- Dôveryhodnosť odpovede je pravidlová: `generate/verify.py` kontroluje čísla a citované
  URL voči získanej evidencii a `query/profile.py` poskytuje slovník nízkokardinalitných
  hodnôt (`column_values`) na presné filtrovanie – bez ďalších volaní modelu.
