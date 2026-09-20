"""DuckDB storage for dataset cards, vectors and the BM25 full-text index."""

from __future__ import annotations

from collections.abc import Sequence

import duckdb

FTS_INDEX = "dataset_cards"


class SearchIndex:
    def __init__(self, con: duckdb.DuckDBPyConnection, dim: int) -> None:
        self.con = con
        self.dim = dim
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS dataset_cards ("
            "dataset_id VARCHAR PRIMARY KEY, text VARCHAR)"
        )
        self.con.execute(
            f"CREATE TABLE IF NOT EXISTS dataset_embeddings ("  # noqa: S608 - fixed dim
            f"dataset_id VARCHAR PRIMARY KEY, vec FLOAT[{dim}])"
        )

    def replace_cards(self, cards: Sequence[tuple[str, str]]) -> None:
        self.con.execute("BEGIN")
        try:
            self.con.execute("DELETE FROM dataset_cards")
            self.con.executemany("INSERT INTO dataset_cards VALUES (?, ?)", cards)
            self.con.execute("COMMIT")
        except Exception:
            self.con.execute("ROLLBACK")
            raise

    def replace_embeddings(self, rows: Sequence[tuple[str, list[float]]]) -> None:
        self.con.execute("BEGIN")
        try:
            self.con.execute("DELETE FROM dataset_embeddings")
            self.con.executemany(
                "INSERT INTO dataset_embeddings VALUES (?, ?)", rows
            )
            self.con.execute("COMMIT")
        except Exception:
            self.con.execute("ROLLBACK")
            raise

    def build_fts(self) -> None:
        self.con.execute("INSTALL fts")
        self.con.execute("LOAD fts")
        self.con.execute(
            f"PRAGMA create_fts_index('{FTS_INDEX}', 'dataset_id', 'text', "
            "stemmer='none', stopwords='none', overwrite=1)"
        )

    # -- queries -----------------------------------------------------------
    def vector_search(
        self, vector: list[float], limit: int
    ) -> list[tuple[str, float]]:
        rows = self.con.execute(
            "SELECT dataset_id, array_cosine_similarity(vec, ?::FLOAT["  # noqa: S608
            f"{self.dim}]) AS score FROM dataset_embeddings "
            "ORDER BY score DESC LIMIT ?",
            [vector, limit],
        ).fetchall()
        return [(r[0], float(r[1])) for r in rows]

    def bm25_search(self, query: str, limit: int) -> list[tuple[str, float]]:
        try:
            rows = self.con.execute(
                f"SELECT dataset_id, "
                f"fts_main_{FTS_INDEX}.match_bm25(dataset_id, ?) AS score "
                f"FROM {FTS_INDEX} "
                f"WHERE score IS NOT NULL ORDER BY score DESC LIMIT ?",
                [query, limit],
            ).fetchall()
            return [(r[0], float(r[1])) for r in rows]
        except duckdb.Error:
            return []

    def concept_search(
        self, concept_ids: list[str], limit: int
    ) -> list[tuple[str, float]]:
        if not concept_ids:
            return []
        try:
            placeholders = ", ".join("?" for _ in concept_ids)
            rows = self.con.execute(
                "SELECT dataset_id, count(DISTINCT concept_id) AS score FROM dataset_concepts "
                f"WHERE concept_id IN ({placeholders}) "  # noqa: S608 - placeholders only
                "GROUP BY dataset_id ORDER BY score DESC LIMIT ?",
                [*concept_ids, limit],
            ).fetchall()
            return [(r[0], float(r[1])) for r in rows]
        except duckdb.Error:
            return []

    def card(self, dataset_id: str) -> str | None:
        row = self.con.execute(
            "SELECT text FROM dataset_cards WHERE dataset_id = ?", [dataset_id]
        ).fetchone()
        return row[0] if row else None

    def stats(self) -> dict[str, int]:
        def one(sql: str) -> int:
            row = self.con.execute(sql).fetchone()
            return int(row[0]) if row else 0

        return {
            "cards": one("SELECT count(*) FROM dataset_cards"),
            "embeddings": one("SELECT count(*) FROM dataset_embeddings"),
        }
