"""Read-only SQL execution over the catalog and cached data tables."""

from __future__ import annotations

import re
from typing import Any

import duckdb

_READ_START = re.compile(r"^(select|with|describe|show|summarize|from)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|copy|pragma|call|"
    r"export|import|install|load|truncate|replace)\b",
    re.IGNORECASE,
)


class UnsafeQueryError(ValueError):
    pass


def run_sql(
    con: duckdb.DuckDBPyConnection, sql: str, max_rows: int = 200
) -> tuple[list[str], list[tuple[Any, ...]]]:
    statement = sql.strip().rstrip(";").strip()
    if not _READ_START.match(statement):
        raise UnsafeQueryError("only read-only statements (SELECT/WITH/DESCRIBE) are allowed")
    if _FORBIDDEN.search(statement):
        raise UnsafeQueryError("statement contains a forbidden keyword")
    cursor = con.execute(statement)
    columns = [d[0] for d in cursor.description] if cursor.description else []
    rows = cursor.fetchmany(max_rows)
    return columns, rows
