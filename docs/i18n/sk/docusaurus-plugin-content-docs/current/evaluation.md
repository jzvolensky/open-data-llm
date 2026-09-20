---
title: Vyhodnotenie
sidebar_label: Vyhodnotenie
---

# Vyhodnotenie

## Kvalita vyhľadávania

Vyhľadávanie hodnotíme na malej zlatej množine **28 otázok** (slovensky a anglicky)
v `src/opendata_llm/eval/questions.jsonl`. Výsledok je správny, ak sa očakávaný dataset
objaví v top *k*.

| Konfigurácia | recall@10 | MRR | nDCG@10 |
| --- | --- | --- | --- |
| Hybrid (BM25 + vektory + koncepty) | 0,964 | 0,712 | 0,769 |
| **+ `bge-reranker-v2-m3`** | **1,000** | **0,952** | **0,965** |

Reranking je najväčšie zlepšenie: zachráni jednu anglickú otázku, ktorú čistý hybrid
minul, a zvýši strednú recipročnú hodnotu poradia o približne 34 %.

Reprodukcia:

```bash
bdata eval                     # reranking zapnutý (predvolené)
bdata eval --no-rerank         # iba hybrid
```

## Dátová otázka (end-to-end)

Na otázku *„Koľko priestupkov bolo v Ružinove v roku 2025?"* router zvolí dátovú rovinu,
model vygeneruje

```sql
SELECT POCET_PRIESTUPKOV FROM ds_db2bc2a556af4a3dbb1d76107769a089_csv
WHERE MESTSKA_CAST = 'Ružinov' AND ROK = 2025
```

a odpoveď je správna hodnota, **14 302**.

## Čo meriame a ako

- **recall@k** – podiel otázok, kde je relevantný dataset v top *k*.
- **MRR** – priemer `1 / poradie` prvého relevantného výsledku.
- **nDCG@k** – kvalita poradia vážená pozíciou.
- **Dátová cesta** – overená proti známym hodnotám (napr. vyššie uvedený počet) a proti
  živému ArcGIS serveru.

## Obmedzenia

- Zlatá množina je malá a ručne písaná; pred silnými závermi ju treba rozšíriť.
- Hodnotenie pokrýva vyhľadávanie, nie vernosť odpovede. Pridanie metrík na úrovni
  odpovede (napr. Ragas) je v pláne.
- Niektoré datasety sa menia v čase, preto presné očakávané hodnoty treba overiť proti
  živému serveru.
