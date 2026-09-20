"""DuckDB spatial helper functions."""

from __future__ import annotations

import duckdb

_INITIALISED: set[int] = set()


def ensure_spatial(con: duckdb.DuckDBPyConnection) -> None:
    if id(con) in _INITIALISED:
        return
    con.execute("INSTALL spatial")
    con.execute("LOAD spatial")
    _INITIALISED.add(id(con))
