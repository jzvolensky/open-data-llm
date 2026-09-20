---
title: Inštalácia
sidebar_label: Inštalácia
---

# Inštalácia

Táto stránka popisuje úplné lokálne nastavenie. `Makefile` obaľuje každý krok, ale
uvádzame aj jednotlivé príkazy, aby sa dali spustiť samostatne.

## Predpoklady

| Požiadavka | Prečo |
| --- | --- |
| macOS na Apple Silicon, odporúčaných **32 GB** RAM | MLX generovanie; 22B model má ~12,7 GB |
| [`uv`](https://docs.astral.sh/uv/) | Python 3.12 prostredie a závislosti |
| bežiaci [Ollama](https://ollama.com) | poskytuje embedding model `bge-m3` |
| Node 20+ | len na zostavenie tejto dokumentácie |

```bash
# raz
brew install uv
brew install ollama
ollama serve &            # ak už nebeží ako služba
ollama pull bge-m3        # embedding model (~1,2 GB)
```

## 1. Inštalácia závislostí

```bash
make setup
# ekvivalent: uv sync --extra dev,rerank,mlx,api,mcp
```

Nainštaluje všetko: vyhľadávanie, MLX runtime, reranker, API aj MCP.

## 2. Stiahnutie generatívneho modelu

Je to samostatný krok, pretože má ~12 GB. Sťahovanie je obnoviteľné — pri prerušení ho
spustite znova.

```bash
make model
# stiahne mlx-community/EuroLLM-22B-Instruct-2512-mlx-4bit do models/EuroLLM-22B-4bit
```

Sťahovanie používa obyčajné HTTP (`HF_HUB_DISABLE_XET=1`), pretože Xet prenos môže na
niektorých pripojeniach zamrznúť.

## 3. Zostavenie dátového pipeline

```bash
make build
```

Spustí kroky v poradí (každý je dostupný aj samostatne):

| Krok | Príkaz | Čo robí |
| --- | --- | --- |
| 1 | `make ingest` | DCAT feed + Hub vyhľadávanie + schémy ArcGIS vrstiev |
| 2 | `make download` | distribučné súbory, limit 25 MB na súbor |
| 3 | `make graph` | koncepty, väzby na mestské časti, podobnosť + kurátorské hrany |
| 4 | `make data` | sprístupní stiahnuté CSV ako DuckDB pohľady |
| 5 | `make index` | karty datasetov, embeddingy `bge-m3`, BM25 (používa reálnu schému CSV) |
| 6 | `make geo` | gazetteer mestských častí a priestorové vrstvy |

Očakávaný rozsah: ~669 datasetov, ~4 860 distribúcií, ~620 schém vrstiev, ~2 060
stiahnutých súborov.

:::tip Čiastočné zostavenie
Spustite len to, čo potrebujete. Na samotné vyhľadávanie stačí
`make ingest && make graph && make index`; dátové a geo kroky zapnú SQL a priestorové
otázky.
:::

## 4. Spustenie

```bash
bdata ask "Koľko priestupkov bolo v Ružinove v roku 2025?"
bdata search "kvalita ovzdušia"
bdata serve          # web UI + API na http://127.0.0.1:8000
bdata mcp            # MCP server cez stdio
```

Alebo cez make:

```bash
make ask Q="Kde nájdem údaje o školstve?"
make serve           # PORT=9000 zmení port
```

## 5. Overenie

```bash
bdata status         # počty datasetov/formátov
bdata eval           # metriky vyhľadávania (recall@k, MRR, nDCG)
make test            # unit testy
```

## Riešenie problémov

- **`catalog not found`** – spustite `make build` (alebo aspoň `make ingest`).
- **Chyby embeddingov / connection refused** – overte, že beží `ollama serve` a že
  `ollama pull bge-m3` dobehol.
- **Prvá odpoveď je pomalá** – 22B model a reranker sa načítajú pri prvom použití. API
  oba zahreje pri štarte; `bdata ask` ich načítava pri každom spustení zámerne.
- **Generovanie je veľmi pomalé / tlak na pamäť** – zatvorte iné veľké aplikácie; model
  potrebuje ~13 GB v pamäti.
