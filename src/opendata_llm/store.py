from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id VARCHAR PRIMARY KEY,
    item_id VARCHAR,
    dcat_id VARCHAR,
    slug VARCHAR,
    title VARCHAR,
    description VARCHAR,
    description_html VARCHAR,
    publisher VARCHAR,
    contact_name VARCHAR,
    contact_email VARCHAR,
    theme VARCHAR,
    access_rights VARCHAR,
    language VARCHAR,
    issued TIMESTAMP,
    modified TIMESTAMP,
    spatial_wkt VARCHAR,
    license VARCHAR,
    license_info VARCHAR,
    categories VARCHAR,
    tags VARCHAR,
    keywords VARCHAR,
    item_type VARCHAR,
    owner VARCHAR,
    org_id VARCHAR,
    source VARCHAR,
    culture VARCHAR,
    num_views BIGINT,
    size_bytes BIGINT,
    service_url VARCHAR,
    hub_url VARCHAR,
    dcat_url VARCHAR,
    search_id VARCHAR,
    in_dcat BOOLEAN,
    in_search BOOLEAN,
    ingested_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS distributions (
    dataset_id VARCHAR,
    item_id VARCHAR,
    idx INTEGER,
    title VARCHAR,
    fmt VARCHAR,
    format_uri VARCHAR,
    description VARCHAR,
    access_url VARCHAR,
    download_url VARCHAR,
    is_download BOOLEAN,
    PRIMARY KEY (dataset_id, idx)
);

CREATE TABLE IF NOT EXISTS keywords (
    dataset_id VARCHAR,
    keyword VARCHAR,
    PRIMARY KEY (dataset_id, keyword)
);

CREATE TABLE IF NOT EXISTS categories (
    dataset_id VARCHAR,
    category VARCHAR,
    PRIMARY KEY (dataset_id, category)
);

CREATE TABLE IF NOT EXISTS layers (
    item_id VARCHAR,
    layer_id INTEGER,
    name VARCHAR,
    geom_type VARCHAR,
    max_record_count INTEGER,
    extent VARCHAR,
    fetched_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (item_id, layer_id)
);

CREATE TABLE IF NOT EXISTS fields (
    item_id VARCHAR,
    layer_id INTEGER,
    name VARCHAR,
    alias VARCHAR,
    field_type VARCHAR,
    nullable BOOLEAN,
    domain VARCHAR,
    PRIMARY KEY (item_id, layer_id, name)
);

CREATE TABLE IF NOT EXISTS downloads (
    item_id VARCHAR,
    access_url VARCHAR,
    fmt VARCHAR,
    path VARCHAR,
    bytes BIGINT,
    status VARCHAR,
    error VARCHAR,
    fetched_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (item_id, access_url)
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    run_id VARCHAR,
    source VARCHAR,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    status VARCHAR,
    records INTEGER,
    detail VARCHAR
);
"""

DATASET_COLS: tuple[str, ...] = (
    "dataset_id",
    "item_id",
    "dcat_id",
    "slug",
    "title",
    "description",
    "description_html",
    "publisher",
    "contact_name",
    "contact_email",
    "theme",
    "access_rights",
    "language",
    "issued",
    "modified",
    "spatial_wkt",
    "license",
    "license_info",
    "categories",
    "tags",
    "keywords",
    "item_type",
    "owner",
    "org_id",
    "source",
    "culture",
    "num_views",
    "size_bytes",
    "service_url",
    "hub_url",
    "dcat_url",
    "search_id",
    "in_dcat",
    "in_search",
)

_DIST_COLS = (
    "dataset_id",
    "item_id",
    "idx",
    "title",
    "fmt",
    "format_uri",
    "description",
    "access_url",
    "download_url",
    "is_download",
)


def _json(value: Any) -> str | None:
    if value in (None, [], {}):
        return None
    return json.dumps(value, ensure_ascii=False)


class Catalog:
    """DuckDB-backed catalog of datasets, distributions and their schema."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(self.db_path))
        self.con.execute(SCHEMA)

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> Catalog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- writes ------------------------------------------------------------
    def replace_catalog(self, records: Sequence[dict[str, Any]]) -> None:
        dataset_rows: list[tuple[Any, ...]] = []
        dist_rows: list[tuple[Any, ...]] = []
        keyword_rows: list[tuple[str, str]] = []
        category_rows: list[tuple[str, str]] = []

        for record in records:
            dataset_id = record["dataset_id"]
            item_id = record.get("item_id")
            dataset_rows.append(
                tuple(_dataset_value(record, col) for col in DATASET_COLS)
            )
            for dist in record.get("distributions") or []:
                dist_rows.append(
                    (
                        dataset_id,
                        item_id,
                        dist["idx"],
                        dist.get("title"),
                        dist.get("fmt"),
                        dist.get("format_uri"),
                        dist.get("description"),
                        dist.get("access_url"),
                        dist.get("download_url"),
                        bool(dist.get("is_download")),
                    )
                )
            for keyword in dict.fromkeys(str(k) for k in record.get("keywords") or []):
                keyword_rows.append((dataset_id, keyword))
            for category in dict.fromkeys(str(c) for c in record.get("categories") or []):
                category_rows.append((dataset_id, category))

        self.con.execute("BEGIN")
        try:
            for table in ("datasets", "distributions", "keywords", "categories"):
                self.con.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed names
            self._insert("datasets", DATASET_COLS, dataset_rows)
            self._insert("distributions", _DIST_COLS, dist_rows)
            self._insert("keywords", ("dataset_id", "keyword"), keyword_rows)
            self._insert("categories", ("dataset_id", "category"), category_rows)
            self.con.execute("COMMIT")
        except Exception:
            self.con.execute("ROLLBACK")
            raise

    def replace_layers(
        self,
        item_id: str,
        layers: Iterable[tuple[int, dict[str, Any], list[dict[str, Any]]]],
    ) -> None:
        self.con.execute("DELETE FROM layers WHERE item_id = ?", [item_id])
        self.con.execute("DELETE FROM fields WHERE item_id = ?", [item_id])
        for layer_id, meta, fields in layers:
            self.con.execute(
                "INSERT INTO layers (item_id, layer_id, name, geom_type, "
                "max_record_count, extent) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    item_id,
                    layer_id,
                    meta.get("name"),
                    meta.get("geometryType"),
                    meta.get("maxRecordCount"),
                    _json(meta.get("extent")),
                ],
            )
            for field in fields:
                self.con.execute(
                    "INSERT INTO fields (item_id, layer_id, name, alias, field_type, "
                    "nullable, domain) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        item_id,
                        layer_id,
                        field.get("name"),
                        field.get("alias"),
                        field.get("type"),
                        field.get("nullable"),
                        _json(field.get("domain")),
                    ],
                )

    def record_download(
        self,
        item_id: str,
        access_url: str,
        fmt: str | None,
        path: str | None,
        size: int | None,
        status: str,
        error: str | None = None,
    ) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO downloads "
            "(item_id, access_url, fmt, path, bytes, status, error, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, now())",
            [item_id, access_url, fmt, path, size, status, error],
        )

    def log_run(
        self,
        run_id: str,
        source: str,
        started_at: datetime,
        finished_at: datetime,
        status: str,
        records: int,
        detail: str | None = None,
    ) -> None:
        self.con.execute(
            "INSERT INTO ingest_runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            [run_id, source, started_at, finished_at, status, records, detail],
        )

    # -- reads -------------------------------------------------------------
    def list_download_targets(
        self,
        formats: Sequence[str],
        item_ids: Sequence[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        conditions = ["access_url IS NOT NULL", "is_download = TRUE"]
        params: list[Any] = []
        if formats:
            placeholders = ", ".join("?" for _ in formats)
            conditions.append(f"upper(fmt) IN ({placeholders})")
            params.extend(fmt.upper() for fmt in formats)
        if item_ids:
            placeholders = ", ".join("?" for _ in item_ids)
            conditions.append(f"item_id IN ({placeholders})")
            params.extend(item_ids)
        sql = (
            "SELECT DISTINCT item_id, access_url, fmt FROM distributions "
            f"WHERE {' AND '.join(conditions)} ORDER BY item_id, fmt"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.con.execute(sql, params).fetchall()
        return [{"item_id": r[0], "access_url": r[1], "fmt": r[2]} for r in rows]

    def datasets_missing_layers(self, limit: int | None = None) -> list[dict[str, str]]:
        sql = (
            "SELECT item_id, service_url FROM datasets "
            "WHERE service_url IS NOT NULL "
            "AND item_id NOT IN (SELECT DISTINCT item_id FROM layers) "
            "ORDER BY item_id"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.con.execute(sql).fetchall()
        return [{"item_id": r[0], "service_url": r[1]} for r in rows]

    def stats(self) -> dict[str, Any]:
        def one(sql: str) -> Any:
            row = self.con.execute(sql).fetchone()
            assert row is not None
            return row[0]

        return {
            "datasets": one("SELECT count(*) FROM datasets"),
            "in_dcat": one("SELECT count(*) FROM datasets WHERE in_dcat"),
            "in_search": one("SELECT count(*) FROM datasets WHERE in_search"),
            "distributions": one("SELECT count(*) FROM distributions"),
            "layers": one("SELECT count(*) FROM layers"),
            "fields": one("SELECT count(*) FROM fields"),
            "downloads": one("SELECT count(*) FROM downloads WHERE status = 'ok'"),
        }

    def format_breakdown(self) -> list[tuple[str, int]]:
        rows = self.con.execute(
            "SELECT fmt, count(*) c FROM distributions GROUP BY fmt ORDER BY c DESC"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    # -- internals ---------------------------------------------------------
    def _insert(
        self, table: str, cols: Sequence[str], rows: Sequence[Sequence[Any]]
    ) -> None:
        if not rows:
            return
        placeholders = ", ".join("?" for _ in cols)
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"  # noqa: S608
        self.con.executemany(sql, rows)


def _dataset_value(record: dict[str, Any], col: str) -> Any:
    value = record.get(col)
    if col in ("categories", "tags", "keywords"):
        return _json(value)
    return value
