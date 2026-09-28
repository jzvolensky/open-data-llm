---
title: Vyhodnotenie
sidebar_label: Vyhodnotenie
---

# Vyhodnotenie

Vyhodnotenie odpovedá na dve oddelené otázky:

1. **Vyhľadávanie** – nájde systém správny dataset pre otázku?
2. **Odpovedanie** – vráti správnu hodnotu, odmietne, keď má, a vyrieši nadväzujúce otázky?

Zlatá množina je jediný súbor, `src/opendata_llm/eval/questions.jsonl`, jeden JSON objekt
na riadok. Každý prípad má `type`; behy sa vyhodnocujú podľa typu a agregujú.

## Typovaná zlatá množina

| Typ | Význam | Hlavná metrika | Potrebuje model |
| --- | --- | --- | --- |
| `discovery` | nájdenie datasetu | recall@k / MRR / nDCG@k | nie |
| `data` | číselná otázka s `gold` hodnotou | `execution_accuracy` | áno |
| `geo` | určenie mestskej časti | `geo_accuracy` | nie |
| `abstain` | nezodpovedateľná otázka | `abstention_accuracy` | áno |
| `followup` | nadväzujúca otázka s `history` | `resolution_accuracy` | áno |

Typy `data`, `abstain` a `followup` prechádzajú cez SQL/dátovú rovinu, ktorá je
generovaná modelom; bez generátora sa označia ako **preskočené** a vylúčia z príslušnej
metriky. Metriky vyhľadávania sa počítajú iba z `discovery` prípadov, takže pridanie
ďalších typov ich nikdy nezhorší.

### Polia prípadu

| Pole | Používa | Význam |
| --- | --- | --- |
| `id` | všetky | jedinečné id prípadu |
| `type` | všetky | jeden z typov vyššie (predvolene `discovery`) |
| `lang` | report | `sk` alebo `en` |
| `query` | všetky | otázka |
| `expect` | `discovery` | podreťazce názvu (malými písmenami), ktoré sa počítajú ako relevantné |
| `gold` | `data`, `followup` | očakávaná hodnota (číslo alebo text) |
| `dataset` | `data`, `followup` | voliteľná kontrola podreťazca id/názvu datasetu |
| `district` | `data`, `geo`, `followup` | očakávaná mestská časť |
| `year` | `data` | iba metadata (priamo sa nehodnotí) |
| `tolerance` | `data` | povolený číselný rozdiel (predvolene `0`) |
| `history` | `followup` | predchádzajúce ťahy `{role, content}` |
| `note` | ľubovoľné | voľné zdôvodnenie |

### Príklady

```json
{"id": "q01", "lang": "sk", "query": "Koľko priestupkov eviduje mestská polícia podľa mestských častí?", "expect": ["počet priestupkov podľa mestských častí"]}
{"id": "d01", "type": "data", "lang": "sk", "query": "Koľko priestupkov eviduje mestská polícia v Ružinove v roku 2025?", "gold": 14302, "dataset": "priestupk", "district": "Ružinov", "year": 2025}
{"id": "g01", "type": "geo", "lang": "sk", "query": "Ktoré datasety pokrývajú územie Petržalky?", "district": "Petržalka"}
{"id": "a02", "type": "abstain", "lang": "en", "query": "How many private jets are registered in Bratislava open data?", "note": "nie je na portáli"}
{"id": "f02", "type": "followup", "lang": "sk", "query": "A koľko v Ružinove?", "gold": 4514, "dataset": "pozemk", "district": "Ružinov", "year": 2020, "history": [{"role": "user", "content": "Koľko pozemkov vlastní mesto v Petržalke k 31.12.2020?"}, {"role": "assistant", "content": "V Petržalke to bolo 7 056 pozemkov."}]}
```

## Spustenie

```bash
bdata eval                     # všetky typy, reranking zapnutý (predvolené), zapíše report
bdata eval --type discovery    # iba poradové metriky (model netreba)
bdata eval --type data         # presnosť vykonania (načíta generačný model)
bdata eval --type followup     # prepis na samostatnú otázku + SQL
bdata eval --no-rerank         # iba hybridné vyhľadávanie
bdata eval --no-report         # bez dátumového JSON reportu
make eval                      # to isté ako `bdata eval`; prepíšte cez EVAL_TYPE=data
```

Každý beh zapíše dátumový JSON report do `reports/eval/eval-YYYYMMDD-HHMMSS.json`
(gitignored). SQL a prepis bežia pri `temperature=0`, takže pevný build je reprodukovateľný
okrem záverečnej formulácie odpovede.

## Metriky

| Metrika | Definícia |
| --- | --- |
| **recall@k** | podiel `discovery` prípadov, kde je `expect` dataset v top *k* |
| **MRR** | priemer `1 / poradie` prvého relevantného výsledku |
| **nDCG@k** | kvalita poradia vážená pozíciou |
| **execution_accuracy** | podiel `data` prípadov, kde výsledok dátovej cesty zodpovedá `gold` (po normalizácii čísel, napr. `14 302` ↔ `14302`) a, ak sú uvedené, aj `dataset` a `district` |
| **abstention_accuracy** | podiel `abstain` prípadov, kde dátová cesta nevráti podložený výsledok |
| **resolution_accuracy** | podiel `followup` prípadov správne vyriešených pomocou `history` |
| **geo_accuracy** | podiel `geo` prípadov so správnou mestskou časťou |
| **latencia** | p50/p90/p95 času v ms, rozdelené na `retrieval_ms` a `data_ms` |

Presnosť vykonania hodnotí **výsledok dátovej cesty**, nie text: používa ten istý intent
router, poradie kandidátov a SQL cestu ako `/ask`, a potom porovná vrátené riadky s `gold`.
Tým sa oddelí správnosť SQL/dát od kvality generovania a behy zostanú rýchle.

## Aktuálne výsledky

Najnovší plný beh (40 prípadov, reranker zapnutý):

| Metrika | Hodnota |
| --- | --- |
| recall@10 | **1,000** |
| MRR | **0,935** |
| nDCG@10 | **0,951** |
| execution_accuracy | **1,000** (5/5) |
| abstention_accuracy | **1,000** (2/2) |
| resolution_accuracy | **1,000** (2/2) |
| geo_accuracy | **1,000** (3/3) |

Latencia (ms):

| Fáza | p50 | p90 | p95 |
| --- | --- | --- | --- |
| Vyhľadávanie (BM25 + vektory + koncepty + rerank) | 1052 | 2454 | 4475 |
| Dátová cesta (generovanie SQL + vykonanie) | 10691 | 15705 | 17128 |

Počty podľa typu: 28 `discovery`, 5 `data`, 3 `geo`, 2 `abstain`, 2 `followup`.

### Kvalita vyhľadávania

Výsledok pre `discovery` je správny, ak sa očakávaný dataset objaví v top *k*.

| Konfigurácia | recall@10 | MRR | nDCG@10 |
| --- | --- | --- | --- |
| Hybrid (BM25 + vektory + koncepty) | 0,964 | 0,712 | 0,769 |
| **+ `bge-reranker-v2-m3`** | **1,000** | **0,935** | **0,951** |

Reranking je najväčšie zlepšenie: zachráni jednu anglickú otázku, ktorú čistý hybrid
minul, a výrazne zvýši strednú recipročnú hodnotu poradia.

## Vzorové príklady

### Podložená dátová odpoveď

Na otázku *„Koľko priestupkov eviduje mestská polícia v Ružinove v roku 2025?"* router
zvolí dátovú rovinu, model vygeneruje

```sql
SELECT POCET_PRIESTUPKOV
FROM ds_db2bc2a556af4a3dbb1d76107769a089_csv
WHERE "MESTSKA_CAST" = 'Ružinov' AND ROK = 2025
```

a odpoveď uvádza **14 302**, spolu s SQL, tabuľkou a filtrom mestskej časti ako evidenciou.
Deterministický overovač číslo prijme, pretože je prítomné vo výsledných riadkoch.

### Požadovaná kategória, ktorá neexistuje

*„Koľko obytných pozemkov vlastní hlavné mesto v Petržalke k 31.12.2020?"* menuje kategóriu
(`obytné`), ktorú stĺpec `Druh pozemku` neobsahuje. Namiesto hádania alebo odmietnutia
dátová cesta vráti skutočné rozloženie:

| Druh pozemku – názov | pocet |
| --- | --- |
| Zastavané plochy a nádvoria | 4021 |
| Ostatné plochy | 2510 |
| Záhrady | 274 |
| … | … |

a uvedie, že požadovaná kategória nie je definovaná. Práve `column_values` (slovník
nízkokardinalitných hodnôt) robí túto detekciu deterministickou.

### Nezodpovedateľná otázka

*„How many private jets are registered in Bratislava open data?"* nemá zodpovedajúci
dataset. Relevantnostná brána nenájde kandidáta, ktorého názov, karta alebo schéma by sa
prekrývali s obsahovými koreňmi otázky, takže dátová cesta okamžite odmietne – negeneruje
SQL a nevymyslí hodnotu.

### Nadväzujúca otázka

S históriou *„Koľko pozemkov vlastní mesto v Petržalke k 31.12.2020?"* → *„7 056"* sa
otázka *„A koľko v Ružinove?"* prepíše na samostatnú otázku, ktorá prenáša rok, SQL filtruje
mestskú časť aj dátum a odpoveď uvádza **4 514**.

## Deterministické overenie odpovede

Presnosť vykonania sa zastaví na výsledku dátovej cesty. Nezávisle od toho sa **každá**
vygenerovaná odpoveď pred vrátením overí v `generate/verify.py`:

- každé číslo v odpovedi musí byť prítomné v evidencii alebo z nej odvoditeľné
  (výsledné riadky, SQL, počet riadkov; povolené sú percentá a súčty dvojíc);
- každá citovaná URL musí byť jedným zo získaných zdrojov.

Zlyhania nespúšťajú ďalšie volanie modelu: stanú sa `warnings`, odpoveď sa anotuje a
`answer_verified` sa vystaví na `/ask` a v udalosti `verification`. Je to signál dôvery,
zatiaľ nie hodnotená metrika.

## Reporty a porovnávanie behov

Každý report obsahuje konfiguráciu, agregáty podľa typu, percentily latencie a pole
`details` s efektívnou otázkou, vygenerovaným SQL, výslednými riadkami a výsledkom
úspech/neúspech pre každý prípad. Dva behy porovnáte cez `jq`:

```bash
jq -r '[.generated_at, .recall@k, .execution_accuracy, .resolution_accuracy] | @tsv' \
  reports/eval/*.json
```

## Pridanie prípadov

Pridajte JSON objekt do `questions.jsonl` so správnym `type`. Pri `data` použite hodnotu,
ktorú viete overiť proti uložené tabuľke (`bdata data sql "SELECT …"`). `expect` držte ako
podreťazec názvu datasetu malými písmenami. Potom spustite:

```bash
bdata eval --type data
```

## Obmedzenia

- Zlatá množina je malá a ručne písaná; pred silnými závermi ju treba rozšíriť.
- `abstain` a `followup` majú málo prípadov, takže jeden omyl výrazne pohne ich presnosťou.
- Presnosť vykonania nehodnotí formuláciu odpovede; sémantická metrika vernosti (napr.
  Ragas) je stále v pláne.
- Záverečný text odpovede je nedeterministický (temperature 0,2); SQL a prepis sú greedy.
- Niektoré datasety sa menia v čase, preto presné očakávané hodnoty treba overiť proti
  živému serveru.
