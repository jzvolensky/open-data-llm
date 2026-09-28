---
title: Príručka pre vývojárov
sidebar_label: Pre vývojárov
---

# Príručka pre vývojárov

Ako je projekt usporiadaný a kde čo meniť.

## Štruktúra repozitára

```
.
├── config.yaml                # všetky runtime voľby (nižšie)
├── Makefile                   # ciele setup / pipeline / pack / docs
├── pyproject.toml             # závislosti, extra, vstupný bod `bdata`
├── scripts/pack.py            # vytvorenie/obnovenie vedomostného balíka
├── src/opendata_llm/
│   ├── cli.py                 # Typer príkazy
│   ├── config.py              # typovaný loader konfigurácie
│   ├── http.py                # httpx klient (retry, limitované sťahovanie)
│   ├── store.py               # DuckDB katalóg + schéma
│   ├── text.py                # HTML, JSON-LD, parsovanie dátumov
│   ├── ingest/                # dcat.py, search.py, features.py, download.py, catalog.py
│   ├── semantic/              # vocab.py (koncepty), graph.py (znalostný graf)
│   ├── index/                 # cards.py, embed.py, store.py, pipeline.py
│   ├── retrieve/              # hybrid.py (RRF), rerank.py (cross-encoder)
│   ├── query/                 # load.py (CSV->DuckDB), profile.py (slovník hodnôt), sql.py, arcgis.py
│   ├── geo/                   # gazetteer.py, layers.py, query.py, spatial.py
│   ├── generate/              # router.py, prompts.py, rag.py, verify.py, mlx_provider.py
│   ├── app/api.py             # FastAPI (/search, /ask, /ask/stream)
│   ├── mcp_server.py          # MCP nástroje
│   └── eval/                  # run.py (typované prípady), questions.jsonl
├── tests/
├── data/                      # catalog.duckdb, downloads/, raw/ (gitignored)
├── models/                    # lokálny model (gitignored)
└── docs/                      # táto Docusaurus stránka (EN + SK)
```

## Mapa modulov

| Oblasť | Vstupný bod | Poznámka |
| --- | --- | --- |
| Ingest | `ingest/catalog.py` | spája DCAT + Hub vyhľadávanie do `datasets` |
| Slovník | `semantic/vocab.py` | 19 konceptov SK/EN, mestské časti, skloňovanie |
| Graf | `semantic/graph.py` | uzly/hrany: koncepty, vydavatelia, podobnosť, related |
| Karty | `index/cards.py` | text, ktorý sa embeduje a indexuje |
| Vyhľadávanie | `retrieve/hybrid.py` | vektory + BM25 + koncepty + mestské časti, RRF |
| Dátová rovina | `query/` | CSV→DuckDB pohľady, SQL iba na čítanie, živý ArcGIS |
| Slovník hodnôt | `query/profile.py` | `column_values` pre nízkokardinalitné stĺpce |
| Geopriestor | `geo/` | gazetteer + `ST_Intersects` / `ST_Within` |
| Odpovedanie | `generate/rag.py` | prepis, vyhľadanie, voliteľné SQL, zostavenie promptu |
| Overenie | `generate/verify.py` | deterministické kontroly čísel/URL v odpovediach |
| Routing | `generate/router.py` | rozhoduje `data` / `geospatial` / `discovery` |

## Konfigurácia

Všetko je v `config.yaml`; `config.py` poskytuje typované predvolené hodnoty.

```yaml
portal:      # base_url, dcat_feed, veľkosť stránky, user agent, timeouty
paths:       # db, raw cache, downloads
ingest:      # feature_concurrency, feature_request_delay
download:    # max_bytes na súbor, data_formats
embeddings:  # provider, model, host, dim, batch_size
search:      # top_k, candidates, rrf_k, rerank, rerank_model
generation:  # provider, model, max_tokens, temperature
```

Iný config zadáte cez `--config cesta.yaml` (alebo `make build CONFIG=...`).

## Ladenie vyhľadávania

- `search.candidates` – koľko výsledkov pridá každý vyhľadávač pred zlúčením.
  Menej = rýchlejší reranking; viac = lepšia úplnosť. Predvolene 20.
- `search.top_k` – počet výsledkov pre odpoveď / UI.
- `search.rrf_k` – vyhladzovacia konštanta RRF (60 je bezpečná hodnota).
- `search.rerank` – zapnutie/vypnutie cross-encodera. Je to najväčší páka na kvalitu
  (pozri [Vyhodnotenie](/evaluation)), ale pridáva latenciu.
- Signály konceptov a mestských častí sa pridávajú automaticky z `semantic/vocab.py`.

## Ladenie generovania

- `generation.max_tokens` – hlavný dial latencie. Čas rastie s ním; 384 drží odpovede
  krátke.
- `generation.temperature` – 0,2 sa používa na vecné, podložené odpovede. Generovanie SQL
  a prepis nadväzujúcej otázky bežia s `temperature=0` (greedy), takže výsledky sú stabilné.
- Znenie promptov je v `generate/prompts.py` (`SYSTEM`, `SQL_SYSTEM`, `REWRITE_SYSTEM`,
  `build_context`, `build_sql_messages`, `build_rewrite_messages`). Veľkosť kontextu
  obmedzujú `CONTEXT_SOURCES` a `max_chars`.

## Ladenie ingestu a sťahovania

- `download.max_bytes` – limit na súbor (25 MB). Väčšie súbory zostávajú cez API.
- `download.data_formats` – ktoré formáty sťahovať (CSV, GEOJSON, XLSX, TXT, KML).
- `ingest.feature_concurrency` – paralelné dopyty na schémy vrstiev (ohľaduplne).
- `ingest.feature_request_delay` – pridajte pauzu pri rate limitoch.

## Ochrany dátovej cesty

Pri numerických otázkach model píše SQL, ale každý krok okolo neho je deterministický
(`generate/rag.py`). Dátová cesta sa použije len vtedy, keď router otázku klasifikuje ako
`data`, a potom:

1. **Relevantnostná brána** – kandidátska tabuľka sa zváži len vtedy, ak sa korene
   obsahových slov otázky prekrývajú s jej názvom, kartou alebo schémou. Ak žiadna nie,
   asistent odmietne namiesto vynútenia SQL nad nesúvisiacou tabuľkou.
2. **Slovník hodnôt** – `query/profile.py` ukladá rôzne hodnoty nízkokardinalitných
   stĺpcov do `column_values`. Hodnoty, ktoré otázka cituje doslovne, sa ponúknu modelu,
   aby si nevymýšľal hodnoty filtra.
3. **Určenie mestskej časti** – mestská časť z otázky sa priradí k presnému uloženému
   tvaru (cez `column_values`, s fallbackom `ILIKE`) a model dostane stĺpec aj hodnotu.
4. **Podloženie** – SQL musí odkazovať na kandidátsku tabuľku a, ak bola uvedená mestská
   časť, filtrovať stĺpec typu územia (`Katastrálne územie`, `KU`, `MESTSKA_CAST`, …).
   Identifikátory, ktoré model obalil jednoduchými úvodzovkami, sa normalizujú na dvojité.
5. **Neprázdny výsledok** – inak asistent odmietne, okrem prípadu, keď bola hodnotou filtra
   **kategória, ktorá neexistuje**: vtedy vráti skutočné rozloženie daného stĺpca a uvedie,
   že kategória nie je definovaná.
6. **Deterministické overenie** – vygenerovaný text skontroluje `generate/verify.py`:
   každé číslo musí byť prítomné v evidencii alebo z nej odvoditeľné a každá citovaná URL
   musí byť získaný zdroj. Zlyhania sa anotujú ako `warnings`; nerobí sa druhé volanie
   modelu.

Kandidátske tabuľky sa zoraďujú podľa sémantického vyhľadania + prieniku konceptov +
slovenského stemmera (`semantic/vocab.py`) a používajú **reálne stĺpce uloženého CSV**.
Vypočítané výsledky sa vracajú spolu s SQL, tabuľkou a filtrom ako dôkaz.

## Politika routera

`generate/router.py` rozhoduje, či sa spustí SQL cesta. Pravidlá sú zámerne
konzervatívne: numerické signály → `data`; **konkrétna mestská časť** alebo výslovná
priestorová fráza → `geospatial`; inak `discovery`. Správanie zmeníte v `DATA_CUES` /
`GEO_CUES` a nezabudnite na guard `intent == "data"` v `rag.py` — práve ten drží otázky na
objavovanie lacné.

## Pridanie konceptu alebo aliasu

Koncepty prepájajú slovenčinu a angličtinu. Pridajte alebo rozšírte záznam v
`semantic/vocab.py` (`Concept(...)`) a znova zostavte graf a index:

```bash
make graph && make index
```

`category_concept` mapuje štítky ArcGIS `/Categories/...`; `places_in` / `place_slug`
riešia mestské časti so skloňovaním.

## Zmena kariet datasetov

Karty sa tvoria v `index/cards.py` (`render_card`). Čokoľvek sem pridáte, stane sa
vyhľadateľným (BM25) aj embedovaným, preto to držte krátke a vecné. Znovu zostavte cez
`make index`.

## Evaluačná množina

`src/opendata_llm/eval/questions.jsonl` je typovaná zlatá množina (`discovery`, `data`,
`geo`, `abstain`, `followup`). Prípady `discovery` používajú `{id, lang, query, expect}`;
odpovedové pridávajú `gold`, `dataset`, `district` a pri nadväzujúcich aj `history`. Úplnú
schému a definície metrík nájdete vo [Vyhodnotení](/evaluation).

```bash
bdata eval --type discovery    # iba poradie (rýchle, bez modelu)
bdata eval --type data         # presnosť vykonania (načíta model)
bdata eval                     # všetky typy; zapíše reports/eval/eval-<ts>.json
```

Pri `data` použite hodnotu, ktorú viete overiť proti uložené tabuľke
(`bdata data sql "SELECT …"`). Nové odpovedové prípady neovplyvnia metriky vyhľadávania,
ktoré sa počítajú podľa typu.

## Rozširovanie rozhraní

- **Nový generatívny backend** – implementujte `generate(messages, **kwargs)` (prípadne
  `stream`) v triede a zapojte ju do `build_generator` v `generate/__init__.py`.
- **Nová API routa / MCP nástroj** – pridajte do `app/api.py` alebo `mcp_server.py`; oba
  použijú tie isté pomocné funkcie vyhľadávania a dátovej roviny.
- **Nový CLI príkaz** – pridajte `@app.command()` (alebo pod-`Typer`) do `cli.py`.

## Vývojový postup

```bash
make lint        # ruff
make typecheck   # mypy src
make test        # pytest
make docs-serve  # táto stránka na http://localhost:3000
```

## Na čo pozor

- **DuckDB je single-writer** – nespúšťajte dva pipeline príkazy nad `catalog.duckdb`
  naraz.
- **Jeden MLX worker** – uvicorn spúšťajte s jedným procesom; 12 GB model sa nedá
  zdieľať medzi workermi.
- **Sťahovanie modelu** – použite `HF_HUB_DISABLE_XET=1` (Makefile to robí), ak sa prenos
  zasekne.
- **`models/` a `data/` sú gitignored** – zdieľajte ich cez vedomostný balík alebo
  release artefakt, nie cez git.
- **`column_values` je odvodená** – keď `make download` pridá tabuľky, znova spustite
  `make data` (alebo `bdata data profile`), aby presné priraďovanie hodnôt zostalo aktuálne.
  Metadatové balíky ju odstraňujú, preto po obnovení spustite `make data`.
