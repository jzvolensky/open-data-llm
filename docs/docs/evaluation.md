---
title: Evaluation
sidebar_label: Evaluation
---

# Evaluation

Evaluation answers two separate questions:

1. **Retrieval** – does the system find the right dataset for a question?
2. **Answering** – does it produce the right value, decline when it should, and resolve
   follow-up questions?

The gold set is a single file, `src/opendata_llm/eval/questions.jsonl`, with one JSON
object per line. Every case has a `type`; runs are scored per type and aggregated.

## Typed gold set

| Type | Meaning | Primary metric | Needs model |
| --- | --- | --- | --- |
| `discovery` | find the dataset | recall@k / MRR / nDCG@k | no |
| `data` | numeric question with a `gold` value | `execution_accuracy` | yes |
| `geo` | resolve a district | `geo_accuracy` | no |
| `abstain` | unanswerable question | `abstention_accuracy` | yes |
| `followup` | multi-turn question with `history` | `resolution_accuracy` | yes |

Data, abstain and followup cases run the SQL/data plane, which is model-generated; without
a generator they are reported as **skipped** and excluded from their accuracy metric.
Retrieval (discovery) metrics are computed only over `discovery` cases, so adding answer
cases can never move them.

### Case fields

| Field | Used by | Meaning |
| --- | --- | --- |
| `id` | all | unique case id |
| `type` | all | one of the types above (default `discovery`) |
| `lang` | reporting | `sk` or `en` |
| `query` | all | the question |
| `expect` | `discovery` | lowercase title substrings that count as relevant |
| `gold` | `data`, `followup` | expected value (number or string) |
| `dataset` | `data`, `followup` | optional dataset-id/title substring check |
| `district` | `data`, `geo`, `followup` | expected district label |
| `year` | `data` | metadata only (not scored directly) |
| `tolerance` | `data` | allowed numeric difference (default `0`) |
| `history` | `followup` | prior `{role, content}` turns |
| `note` | any | free-text rationale |

### Examples

```json
{"id": "q01", "lang": "sk", "query": "Koľko priestupkov eviduje mestská polícia podľa mestských častí?", "expect": ["počet priestupkov podľa mestských častí"]}
{"id": "d01", "type": "data", "lang": "sk", "query": "Koľko priestupkov eviduje mestská polícia v Ružinove v roku 2025?", "gold": 14302, "dataset": "priestupk", "district": "Ružinov", "year": 2025}
{"id": "g01", "type": "geo", "lang": "sk", "query": "Ktoré datasety pokrývajú územie Petržalky?", "district": "Petržalka"}
{"id": "a02", "type": "abstain", "lang": "en", "query": "How many private jets are registered in Bratislava open data?", "note": "not on the portal"}
{"id": "f02", "type": "followup", "lang": "sk", "query": "A koľko v Ružinove?", "gold": 4514, "dataset": "pozemk", "district": "Ružinov", "year": 2020, "history": [{"role": "user", "content": "Koľko pozemkov vlastní mesto v Petržalke k 31.12.2020?"}, {"role": "assistant", "content": "V Petržalke to bolo 7 056 pozemkov."}]}
```

## Running

```bash
bdata eval                     # all types, rerank on (config default), writes a report
bdata eval --type discovery    # ranking metrics only (no model needed)
bdata eval --type data         # execution accuracy (loads the generation model)
bdata eval --type followup     # standalone-query rewrite + SQL
bdata eval --no-rerank         # hybrid retrieval only
bdata eval --no-report         # skip the dated JSON report
make eval                      # same as `bdata eval`; override with EVAL_TYPE=data
```

Every run writes a dated JSON report to `reports/eval/eval-YYYYMMDD-HHMMSS.json`
(gitignored). The SQL and rewrite prompts run at `temperature=0`, so a fixed build is
reproducible apart from the final answer prose.

## Metrics

| Metric | Definition |
| --- | --- |
| **recall@k** | fraction of discovery cases where a `expect` dataset is in the top *k* |
| **MRR** | mean of `1 / rank` of the first relevant result |
| **nDCG@k** | position-weighted ranking quality |
| **execution_accuracy** | fraction of `data` cases whose data-path result matches `gold` (after number normalization, e.g. `14 302` ↔ `14302`) and, when given, `dataset` and `district` |
| **abstention_accuracy** | fraction of `abstain` cases where the data path returns no grounded result |
| **resolution_accuracy** | fraction of `followup` cases resolved correctly using `history` |
| **geo_accuracy** | fraction of `geo` cases with the expected district |
| **latency** | p50/p90/p95 wall time in ms, split into `retrieval_ms` and `data_ms` |

Execution accuracy scores the **data-path result**, not the prose: it calls the same
intent router, candidate ranking and SQL path as `/ask`, then compares the returned rows
to `gold`. This isolates SQL/data correctness from generation quality and keeps runs fast.

## Current results

Latest full run (40 cases, reranker on):

| Metric | Value |
| --- | --- |
| recall@10 | **1.000** |
| MRR | **0.935** |
| nDCG@10 | **0.951** |
| execution_accuracy | **1.000** (5/5) |
| abstention_accuracy | **1.000** (2/2) |
| resolution_accuracy | **1.000** (2/2) |
| geo_accuracy | **1.000** (3/3) |

Latency (ms):

| Stage | p50 | p90 | p95 |
| --- | --- | --- | --- |
| Retrieval (BM25 + vectors + concepts + rerank) | 1052 | 2454 | 4475 |
| Data path (SQL generation + execution) | 10691 | 15705 | 17128 |

Per-type case counts: 28 `discovery`, 5 `data`, 3 `geo`, 2 `abstain`, 2 `followup`.

### Retrieval quality

A discovery result counts as correct when the expected dataset appears in the top *k*.

| Configuration | recall@10 | MRR | nDCG@10 |
| --- | --- | --- | --- |
| Hybrid (BM25 + vectors + concepts) | 0.964 | 0.712 | 0.769 |
| **+ `bge-reranker-v2-m3`** | **1.000** | **0.935** | **0.951** |

The reranker is the single biggest improvement: it recovers the one English query that
pure hybrid retrieval missed and lifts mean reciprocal rank substantially.

## Worked examples

### A grounded data answer

Given *"Koľko priestupkov eviduje mestská polícia v Ružinove v roku 2025?"* the router
selects the data plane, the model generates

```sql
SELECT POCET_PRIESTUPKOV
FROM ds_db2bc2a556af4a3dbb1d76107769a089_csv
WHERE "MESTSKA_CAST" = 'Ružinov' AND ROK = 2025
```

and the answer reports **14 302**, with the SQL, table and district filter shown as
evidence. The deterministic verifier accepts the number because it is present in the
result rows.

### A requested category that does not exist

*"Koľko obytných pozemkov vlastní hlavné mesto v Petržalke k 31.12.2020?"* names a
category (`obytné`) that the `Druh pozemku` column does not define. Instead of guessing
or refusing, the data path returns the real breakdown:

| Druh pozemku – názov | pocet |
| --- | --- |
| Zastavané plochy a nádvoria | 4021 |
| Ostatné plochy | 2510 |
| Záhrady | 274 |
| … | … |

and notes that the requested category is not defined. `column_values` (the low-cardinality
value dictionary) is what makes this detection deterministic.

### An unanswerable question

*"How many private jets are registered in Bratislava open data?"* has no matching dataset.
The relevance gate finds no candidate whose title, card or schema overlaps the question's
content stems, so the data path declines immediately — no SQL is generated and no value is
invented.

### A follow-up question

With history *"Koľko pozemkov vlastní mesto v Petržalke k 31.12.2020?"* → *"7 056"*, the
question *"A koľko v Ružinove?"* is rewritten to a standalone query that carries the year
forward, the SQL filters both district and date, and the answer reports **4 514**.

## Deterministic answer verification

Execution accuracy stops at the data-path result. Independently, **every** generated
answer is checked by `generate/verify.py` before it is returned:

- every number in the answer must be present in, or derivable from, the evidence
  (result rows, SQL, row count; pairwise percentages and sums are allowed);
- every cited URL must be one of the retrieved sources.

Failures do not trigger another model call: they become `warnings`, the answer is
annotated, and `answer_verified` is exposed on `/ask` and in a `verification` stream
event. This is a trust signal, not (yet) a scored metric.

## Reports and comparing runs

Each report contains the configuration, per-type aggregates, latency percentiles and a
`details` array with the effective query, generated SQL, result rows and pass/fail per
case. Compare two runs with `jq`:

```bash
jq -r '[.generated_at, .recall@k, .execution_accuracy, .resolution_accuracy] | @tsv' \
  reports/eval/*.json
```

## Adding cases

Append a JSON object to `questions.jsonl` with the right `type`. For `data` cases, use a
value you can verify against the cached table (`bdata data sql "SELECT …"`). Keep
`expect` as a lowercase substring of the dataset title. Then run:

```bash
bdata eval --type data
```

## Limitations

- The gold set is small and hand-written; expand it before drawing strong conclusions.
- `abstain` and `followup` have few cases, so a single miss moves their accuracy a lot.
- Execution accuracy does not judge answer wording; semantic faithfulness (e.g. Ragas) is
  still planned.
- The final answer prose is non-deterministic (temperature 0.2); SQL and rewrite are
  greedy.
- Some datasets change over time, so exact expected values should be re-verified against
  the live service.
