---
title: Balenie a zdieľanie
sidebar_label: Balenie
---

# Balenie a zdieľanie

## Dá sa RAG uložiť do modelu?

Nie — RAG je **vyhľadávanie plus model** a znalosť žije v **indexe**, nie vo váhach
modelu. Bez trénovania nie je čo do modelu zapísať. Reálne sú tri možnosti:

| Možnosť | Čo získate | Nevýhody |
| --- | --- | --- |
| **Fine-tuning / LoRA** | fakty a štýl zapečené vo váhach | rýchlo zastará (portál sa mení); **žiadne citácie**; nevie SQL dátovú rovinu; treba trénovať |
| **Vedomostný balík** (tento projekt) | prenosný index: karty, embeddingy, graf, uložené tabuľky | potrebuje model vedľa seba; po aktualizácii treba prebaliť |
| **Oboje** | balík na fakty, malá LoRA na správanie | najviac práce; najlepší výsledok |

Fine-tuning sa na fakty nehodí: dátumy `dct:modified` sa neustále menia, citácie sú
dôležité a numerické otázky rieši SQL, nie generovanie. Použite balík a model držte
vymeniiteľný.

## Čo balík obsahuje

`make pack` vytvorí `release/bdata-pack-<dátum>.tar.gz` s obsahom:

```
bdata-pack/
  catalog.duckdb     # datasety, karty, embeddingy, graf, gazetteer
  config.yaml        # konfigurácia, ktorá balík vytvorila
  MANIFEST.json      # počty, id modelov, kontrolné súčty, git rev, čas
  NOTICE             # atribúcia CC BY 4.0
```

Metadatový balík je malý (~5 MB). Pohľady na uložené tabuľky, register `data_tables` aj
odvodený slovník `column_values` sa zámerne vynechávajú, aby bol balík konzistentný aj bez
CSV; ak chcete dátovú rovinu offline (vrátane presného priraďovania hodnôt), po obnovení
spustite `make download && make data`.

## Vytvorenie a obnovenie

```bash
make pack            # metadatový balík (~5 MB)
make pack FULL=1     # aj data/downloads (offline dátová rovina, ~800 MB)

# na inom stroji / v inom checkoute
make restore PACK=release/bdata-pack-20260920.tar.gz
```

`restore` zapíše `data/catalog.duckdb`, `config.yaml` (existujúci neprepíše),
`MANIFEST.json`, `NOTICE` a pri plnom balíku aj `data/downloads`. Potom nainštalujte
závislosti a model ako zvyčajne (`make setup`, `make model`).

## Aktuálnosť

Balík je snímka. Obnovíte ho opätovným spustením pipeline a zabalením:

```bash
make ingest && make graph && make index
make pack
```

Metadáta sa menia denne; čas v `MANIFEST.json` a `git_rev` presne určujú, čo balík
obsahuje.
