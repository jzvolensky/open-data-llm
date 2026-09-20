---
title: Data & Querying
sidebar_label: Data & Querying
---

# Data & Querying

## Where the data comes from

| Source | Endpoint | What we take |
| --- | --- | --- |
| DCAT-AP feed | `/api/feed/dcat-ap/2.1.1` | 669 datasets, distributions, keywords |
| Hub search (OGC API Records) | `/api/search/v1/collections/dataset/items` | 620 records: licence, categories, tags, views |
| Related links | `.../items/{id}/related` | curated dataset-to-dataset edges |
| FeatureServer metadata | `{item.url}/{layer}?f=json` | 619 layer schemas (fields, geometry, extent) |
| Distribution files | `/api/download/v1/items/{id}/...` | CSV, GeoJSON, XLSX, TXT, KML |

## Local cache vs live API

Datasets range from a few rows to hundreds of megabytes, so we do **not** mirror
everything. The choice is deliberate:

```mermaid
flowchart TD
    Q[Data question] --> N{Needs numbers?}
    N -->|no| CAT[Metadata / discovery retrieval]
    N -->|yes| SIZE{How big is the data?}
    SIZE -->|CSV ≤ 25 MB| CACHE[DuckDB view · cached]
    SIZE -->|larger file| LIVE[FeatureServer · live]
    SIZE -->|geometry| GEO[Cached GeoJSON + spatial]
    SIZE -->|fresh statistics| LIVE
```

| Situation | Approach | Why |
| --- | --- | --- |
| Small/medium tabular data (CSV ≤ 25 MB) | **Cached** as a DuckDB view | instant SQL, works offline |
| Large files | **Live** FeatureServer query | avoids multi-GB downloads |
| Fresh counts/statistics | **Live** FeatureServer query | always current |
| Geometry layers | **Cached** GeoJSON → DuckDB `spatial` | fast point-in-polygon |
| Text/metadata | **Cached** in the catalog | needed for retrieval |

### What was actually downloaded

- **2,061 files / ~785 MB** (CSV 611, GeoJSON 602, KML 436, XLSX 209, TXT 203).
- **38 skipped** because a single file exceeded the 25 MB cap.
- **~178 failed** – almost all are KML requests on non-spatial tables (HTTP 424), which
  is expected: tabular data cannot be rendered as KML.
- **611 CSVs** are exposed as DuckDB views (`ds_<item_id>_csv`), plus **14 spatial
  layers** (`geo_<item_id>`).

:::note Why a size cap?
A 25 MB per-file limit keeps the local cache small and fast while covering the large
majority of datasets. Anything bigger stays available through the live API.
:::

## Querying

Cached data (SQL):

```bash
bdata data sql "SELECT ROK, MESTSKA_CAST, POCET_PRIESTUPKOV
                     FROM ds_db2bc2a556af4a3dbb1d76107769a089_csv
                     WHERE MESTSKA_CAST = 'Ružinov' AND ROK = 2025"
```

Live ArcGIS:

```bash
bdata data live "počet priestupkov podľa mestských častí" \
  --where "MESTSKA_CAST='Ružinov' AND ROK=2025" \
  --columns "ROK,MESTSKA_CAST,POCET_PRIESTUPKOV"
```

The assistant uses the same paths automatically: for data questions it generates a
`SELECT`, runs it read-only, and feeds the result back to the model.

## Geospatial

- District boundaries are fetched once from the portal's "Mestská časť" layer into a
  `geo_places` table (17 districts + Bratislava).
- `place_slug` maps names tolerantly (Slovak inflection: "Ružinov" → "Ružinove").
- Dataset cards are linked to districts by text, and spatial layers by geometry.
- Extents from ArcGIS are in a projected CRS, so district matching uses real geometry
  (`ST_Intersects`) rather than bounding boxes.
