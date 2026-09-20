---
title: Models
sidebar_label: Models
---

# Models

Three models are used, each for a different job. All run locally.

| Role | Model | Size | Runtime |
| --- | --- | --- | --- |
| **Generation** | `EuroLLM-22B-Instruct-2512` (MLX 4-bit) | ~12.7 GB | `mlx-lm` |
| **Embeddings** | `bge-m3` | ~1.2 GB | Ollama |
| **Reranking** | `bge-reranker-v2-m3` | ~2.3 GB | sentence-transformers |

## Generation – EuroLLM-22B (MLX 4-bit)

- **Why**: explicitly multilingual across EU languages, including Slovak, so it answers
  well in both SK and EN.
- **Why MLX**: runs natively on Apple Silicon via `mlx-lm`. At 4-bit it fits comfortably
  in 32 GB of unified memory alongside the embedding and reranker models.
- **Not Ollama**: MLX is a separate runtime. The provider is abstracted, so a GGUF/Ollama
  or API model can be swapped in via `config.yaml` (`generation.provider`).
- Sampling uses mlx-lm's `make_sampler(temp=…, top_p=…)`.

## Embeddings – bge-m3

- Multilingual model with 1024-dimensional vectors.
- Cross-lingual by design: a Slovak query and its English paraphrase land close together
  (cosine ≈ 0.81 in our check), which is what makes EN queries retrieve SK datasets.
- Served by Ollama (`/api/embed`) and stored directly in DuckDB as `FLOAT[1024]`.

## Reranking – bge-reranker-v2-m3

- A cross-encoder that scores each candidate card against the query jointly, which is
  much more accurate than vector similarity alone.
- It is the single biggest quality lever: MRR rose from 0.71 to 0.95 (see
  [Evaluation](/evaluation)).
- Optional dependency (`--extra rerank`); enabled by default in `config.yaml`.

## Configuration

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
  model: "models/EuroLLM-22B-4bit" # local dir or Hugging Face repo id
  max_tokens: 384                 # keep answers short; generation scales with this
  temperature: 0.2
```
