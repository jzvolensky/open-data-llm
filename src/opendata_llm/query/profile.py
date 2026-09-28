"""Profile low-cardinality columns into a value dictionary for exact filtering.

The model often guesses a filter value (a district spelling, a category label) that
does not exist in the data. ``column_values`` records the actual distinct values of
low-cardinality columns so they can be offered to the model, used to resolve districts
exactly, and to detect requests for categories that do not exist.
"""

from __future__ import annotations

from typing import Any

from ..store import Catalog

SCHEMA = """
CREATE TABLE IF NOT EXISTS column_values (
    dataset_id VARCHAR,
    column_name VARCHAR,
    value VARCHAR,
    n BIGINT,
    PRIMARY KEY (dataset_id, column_name, value)
);
"""

#: Columns with more distinct values than this are not profiled.
MAX_DISTINCT = 50
#: Only the first N rows of a table are scanned (bounds cost on large tables).
ROW_CAP = 200_000
#: Values longer than this are ignored (free text, blobs).
MAX_VALUE_LEN = 200


def ensure(catalog: Catalog) -> None:
    catalog.con.execute(SCHEMA)


def _qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def profile_columns(
    catalog: Catalog,
    max_distinct: int = MAX_DISTINCT,
    row_cap: int = ROW_CAP,
    limit: int | None = None,
) -> dict[str, Any]:
    """(Re)build ``column_values`` from every loaded CSV table."""
    ensure(catalog)
    targets = catalog.con.execute(
        "SELECT dataset_id, table_name FROM data_tables WHERE status = 'ok' "
        "ORDER BY dataset_id"
    ).fetchall()
    if limit:
        targets = targets[:limit]

    catalog.con.execute("DELETE FROM column_values")
    ok = failed = 0
    skipped = 0
    inserted = 0
    profiled: set[tuple[str, str]] = set()
    errors: list[str] = []

    for dataset_id, table in targets:
        try:
            described = catalog.con.execute(f"DESCRIBE {table}").fetchall()  # noqa: S608
        except Exception as exc:  # noqa: BLE001 - recorded per dataset
            failed += 1
            errors.append(f"{dataset_id}: {type(exc).__name__}: {exc}")
            continue
        rows: list[tuple[str, str, str, int]] = []
        for described_row in described:
            name = described_row[0]
            quoted = _qident(name)
            try:
                values = catalog.con.execute(
                    f"SELECT {quoted}, count(*) c "  # noqa: S608
                    f"FROM (SELECT {quoted} FROM {table} LIMIT {int(row_cap)}) t "
                    f"GROUP BY 1 ORDER BY c DESC LIMIT {int(max_distinct) + 1}"
                ).fetchall()
            except Exception:  # noqa: BLE001 - skip unreadable columns
                continue
            if not values or len(values) > max_distinct:
                skipped += 1
                continue
            for value, count in values:
                if value is None:
                    continue
                text = str(value)
                if not text.strip() or len(text) > MAX_VALUE_LEN:
                    continue
                rows.append((dataset_id, name, text, int(count)))
        if rows:
            catalog.con.executemany(
                "INSERT OR REPLACE INTO column_values "
                "(dataset_id, column_name, value, n) VALUES (?, ?, ?, ?)",
                rows,
            )
            profiled.update((dataset_id, name) for _d, name, _v, _c in rows)
            inserted += len(rows)
        ok += 1

    return {
        "targets": len(targets),
        "ok": ok,
        "failed": failed,
        "skipped_columns": skipped,
        "columns": len(profiled),
        "values": inserted,
        "errors_sample": errors[:5],
    }


def values_for(catalog: Catalog, dataset_id: str) -> dict[str, list[str]]:
    """Return ``{column: [values]}`` for a dataset, most frequent first."""
    ensure(catalog)
    rows = catalog.con.execute(
        "SELECT column_name, value FROM column_values WHERE dataset_id = ? "
        "ORDER BY column_name, n DESC",
        [dataset_id],
    ).fetchall()
    values: dict[str, list[str]] = {}
    for column, value in rows:
        values.setdefault(column, []).append(value)
    return values
