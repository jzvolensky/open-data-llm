---
title: Evaluation
sidebar_label: Evaluation
---

# Evaluation

## Retrieval quality

We evaluate retrieval against a small gold set of **28 questions** (Slovak and English)
in `src/opendata_llm/eval/questions.jsonl`. A result counts as correct when the expected
dataset appears in the top *k*.

| Configuration | recall@10 | MRR | nDCG@10 |
| --- | --- | --- | --- |
| Hybrid (BM25 + vectors + concepts) | 0.964 | 0.712 | 0.769 |
| **+ `bge-reranker-v2-m3`** | **1.000** | **0.952** | **0.965** |

The reranker is the single biggest improvement: it recovers the one English query that
pure hybrid retrieval missed and lifts mean reciprocal rank by ~34%.

Reproduce with:

```bash
bdata eval                     # rerank on (config default)
bdata eval --no-rerank         # hybrid only
```

## Data question (end-to-end)

Given *"Koľko priestupkov bolo v Ružinove v roku 2025?"* the router selects the data
plane, the model generates

```sql
SELECT POCET_PRIESTUPKOV FROM ds_db2bc2a556af4a3dbb1d76107769a089_csv
WHERE MESTSKA_CAST = 'Ružinov' AND ROK = 2025
```

and the answer is the correct value, **14 302**.

## What is measured, and how

- **recall@k** – fraction of questions where a relevant dataset is in the top *k*.
- **MRR** – mean of `1 / rank` of the first relevant result.
- **nDCG@k** – position-weighted ranking quality.
- **Data path** – checked against known values (e.g. the offences figure above) and
  against the live ArcGIS service.

## Limitations

- The gold set is small and hand-written; expand it before drawing strong conclusions.
- The evaluation covers retrieval, not full answer faithfulness. Adding an answer-level
  metric (e.g. Ragas) is planned.
- Some datasets change over time, so exact expected values should be re-verified against
  the live service.
