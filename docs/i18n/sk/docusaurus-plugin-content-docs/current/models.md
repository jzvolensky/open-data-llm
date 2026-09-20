---
title: Modely
sidebar_label: Modely
---

# Modely

Používame tri modely, každý na inú úlohu. Všetky bežia lokálne.

| Úloha | Model | Veľkosť | Runtime |
| --- | --- | --- | --- |
| **Generovanie** | `EuroLLM-22B-Instruct-2512` (MLX 4-bit) | ~12,7 GB | `mlx-lm` |
| **Embeddingy** | `bge-m3` | ~1,2 GB | Ollama |
| **Reranking** | `bge-reranker-v2-m3` | ~2,3 GB | sentence-transformers |

## Generovanie – EuroLLM-22B (MLX 4-bit)

- **Prečo**: je výslovne viacjazyčný pre jazyky EÚ vrátane slovenčiny, takže odpovedá
  dobre po slovensky aj anglicky.
- **Prečo MLX**: beží natívne na Apple Silicon cez `mlx-lm`. V 4-bit kvantizácii sa
  pohodlne zmestí do 32 GB zjednotenej pamäte spolu s embedding a reranking modelom.
- **Nie Ollama**: MLX je samostatný runtime. Poskytovateľ je abstrahovaný, takže cez
  `config.yaml` (`generation.provider`) sa dá prepnúť na GGUF/Ollama alebo API model.
- Vzorkovanie používa `make_sampler(temp=…, top_p=…)` z mlx-lm.

## Embeddingy – bge-m3

- Viacjazyčný model s 1024-dimenzionálnymi vektormi.
- Je navrhnutý ako medzijazykový: slovenská otázka a jej anglická parafráza sú blízko
  seba (kosínus ≈ 0,81), vďaka čomu anglické otázky nájdu slovenské datasety.
- Poskytuje ho Ollama (`/api/embed`) a vektory sa ukladajú priamo do DuckDB ako `FLOAT[1024]`.

## Reranking – bge-reranker-v2-m3

- Cross-encoder, ktorý spoločne vyhodnotí kartu kandidáta a otázku, čo je výrazne
  presnejšie než samotná vektorová podobnosť.
- Je to najväčší kvalitatívny prínos: MRR stúplo z 0,71 na 0,95 (pozri [Vyhodnotenie](/evaluation)).
- Voliteľná závislosť (`--extra rerank`); v `config.yaml` je predvolene zapnutá.

## Konfigurácia

```yaml
embeddings:
  provider: "ollama"
  model: "bge-m3"
  dim: 1024

search:
  rerank: true
  rerank_model: "BAAI/bge-reranker-v2-m3"

generation:
  provider: "mlx"                 # mlx | ollama | fake
  model: "models/EuroLLM-22B-4bit" # lokálny priečinok alebo HF repozitár
  max_tokens: 384                 # krátke odpovede; čas rastie s týmto limitom
  temperature: 0.2
```
