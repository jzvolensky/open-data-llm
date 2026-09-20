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
│   ├── query/                 # load.py (CSV->DuckDB), sql.py, arcgis.py
│   ├── geo/                   # gazetteer.py, layers.py, query.py, spatial.py
│   ├── generate/              # router.py, prompts.py, rag.py, mlx_provider.py
│   ├── app/api.py             # FastAPI (/search, /ask, /ask/stream)
│   ├── mcp_server.py          # MCP nástroje
│   └── eval/                  # run.py, questions.jsonl
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
| Geopriestor | `geo/` | gazetteer + `ST_Intersects` / `ST_Within` |
| Odpovedanie | `generate/rag.py` | vyhľadanie, voliteľné SQL, zostavenie promptu |
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
- `generation.temperature` – 0,2 sa používa na vecné, podložené odpovede.
- Znenie promptov je v `generate/prompts.py` (`SYSTEM`, `SQL_SYSTEM`,
  `build_context`). Veľkosť kontextu obmedzujú `CONTEXT_SOURCES` a `max_chars`.

## Ladenie ingestu a sťahovania

- `download.max_bytes` – limit na súbor (25 MB). Väčšie súbory zostávajú cez API.
- `download.data_formats` – ktoré formáty sťahovať (CSV, GEOJSON, XLSX, TXT, KML).
- `ingest.feature_concurrency` – paralelné dopyty na schémy vrstiev (ohľaduplne).
- `ingest.feature_request_delay` – pridajte pauzu pri rate limitoch.

## Ochrany dátovej cesty

Pri numerických otázkach model píše SQL, ale výsledok sa pred použitím **validuje**
(`generate/rag.py`):

- SQL musí odkazovať na kandidátsku tabuľku;
- ak otázka spomína mestskú časť, musí filtrovať stĺpec typu územia
  (`Katastrálne územie`, `KU`, `MESTSKA_CAST`, …) — presný stĺpec a hodnota sa zistia
  a model dostane nápovedu;
- výsledok musí byť neprázdny; a
- druhé prebehnutie modelu potvrdí, že SQL naozaj odpovedá na otázku.

Kandidátske tabuľky sa zoraďujú podľa sémantického vyhľadania + prieniku konceptov +
slovenského stemmera (`semantic/vocab.py`) a používajú **reálne stĺpce uloženého CSV**.
Ak neprejde žiadny kandidát, asistent povie, že to z uložených dát nevie, namiesto
hádania. Vypočítané výsledky sa vracajú spolu s SQL, tabuľkou a filtrom ako dôkaz.

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

Rozšírte `src/opendata_llm/eval/questions.jsonl` o položky
`{id, lang, query, expect}` (`expect` je podreťazec názvu malými písmenami). Spustite
`bdata eval` a porovnajte MRR/nDCG.

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
