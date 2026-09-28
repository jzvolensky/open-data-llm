#!/usr/bin/env python
"""Build or restore a shareable knowledge pack.

A knowledge pack bundles the retrieval side of the RAG — the catalog, dataset
cards, embeddings, knowledge graph and gazetteer — so it can be shared
independently of the (large, swappable) generation model.

Examples
--------
    uv run python scripts/pack.py --out release
    uv run python scripts/pack.py --out release --full      # include downloads
    uv run python scripts/pack.py --restore release/bdata-pack-20260920.tar.gz
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from opendata_llm.config import Config

PACK_NAME = "bdata-knowledge-pack"
VERSION = 1
NOTICE = (
    "Knowledge pack for the Bratislava Open Data LLM.\n"
    "Data source: OpenData Bratislava (https://data.bratislava.sk),\n"
    "Magistrát hlavného mesta SR Bratislava, licensed under CC BY 4.0.\n"
    "Models (EuroLLM, bge-m3, bge-reranker) retain their own licences.\n"
)

_STAT_TABLES = (
    "datasets",
    "distributions",
    "dataset_cards",
    "dataset_embeddings",
    "graph_nodes",
    "graph_edges",
    "dataset_concepts",
    "data_tables",
    "column_values",
    "geo_tables",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_rev(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return out.stdout.strip() or None
    except OSError:
        return None


def stats(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in _STAT_TABLES:
        try:
            row = con.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
            counts[table] = int(row[0]) if row else 0
        except duckdb.Error:
            continue
    return counts


def _strip_views(db_path: Path) -> None:
    """Drop cached-table views so a metadata-only pack is self-consistent."""
    con = duckdb.connect(str(db_path))
    try:
        views = con.execute(
            "SELECT view_name FROM duckdb_views() WHERE NOT internal"
        ).fetchall()
        for (name,) in views:
            if name.startswith(("ds_", "geo_")):
                con.execute(f'DROP VIEW IF EXISTS "{name}"')  # noqa: S608
        for table in ("data_tables", "column_values", "geo_tables"):
            try:
                con.execute(f"DELETE FROM {table}")  # noqa: S608
            except duckdb.Error:
                continue
        con.execute("CHECKPOINT")
    finally:
        con.close()


def build(config_path: str, out_dir: Path, full: bool) -> Path:
    config = Config.load(config_path)
    root = Path(config.root)
    db = Path(config.paths.db)
    if not db.exists():
        raise SystemExit(f"catalog not found: {db} — run `make build` first")

    work = Path(tempfile.mkdtemp(prefix="bdata-pack-"))
    pack_root = work / "bdata-pack"
    pack_root.mkdir()
    try:
        shutil.copy2(db, pack_root / "catalog.duckdb")
        if not full:
            _strip_views(pack_root / "catalog.duckdb")
        shutil.copy2(root / "config.yaml", pack_root / "config.yaml")

        downloads_meta: dict[str, int] | None = None
        if full:
            src = Path(config.paths.downloads)
            if src.exists():
                copied = pack_root / "data" / "downloads"
                shutil.copytree(src, copied)
                data_files = [p for p in copied.rglob("*") if p.is_file()]
                downloads_meta = {
                    "files": len(data_files),
                    "bytes": sum(p.stat().st_size for p in data_files),
                }

        con = duckdb.connect(str(pack_root / "catalog.duckdb"), read_only=True)
        try:
            table_stats = stats(con)
        finally:
            con.close()

        files = [
            {"path": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)}
            for p in (pack_root / "catalog.duckdb", pack_root / "config.yaml")
        ]
        manifest = {
            "pack": PACK_NAME,
            "version": VERSION,
            "created_at": datetime.now(UTC).isoformat(),
            "full": full,
            "git_rev": git_rev(root),
            "stats": table_stats,
            "downloads": downloads_meta,
            "models": {
                "generation": config.generation.model,
                "embeddings": config.embeddings.model,
                "embeddings_dim": config.embeddings.dim,
                "rerank": config.search.rerank_model,
            },
            "files": files,
            "attribution": "OpenData Bratislava (CC BY 4.0)",
        }
        (pack_root / "MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (pack_root / "NOTICE").write_text(NOTICE, encoding="utf-8")

        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d")
        suffix = "-full" if full else ""
        archive = out_dir / f"bdata-pack-{stamp}{suffix}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(pack_root, arcname="bdata-pack")
        return archive
    finally:
        shutil.rmtree(work, ignore_errors=True)


def restore(pack_path: str, dest: str) -> None:
    destination = Path(dest).resolve()
    with tempfile.TemporaryDirectory(prefix="bdata-restore-") as tmp:
        with tarfile.open(pack_path, "r:gz") as tar:
            tar.extractall(tmp, filter="data")
        src = Path(tmp) / "bdata-pack"
        if not src.is_dir():
            raise SystemExit("invalid pack: missing bdata-pack/ directory")

        (destination / "data").mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / "catalog.duckdb", destination / "data" / "catalog.duckdb")
        for name in ("MANIFEST.json", "NOTICE"):
            if (src / name).exists():
                shutil.copy2(src / name, destination / name)
        config_target = destination / "config.yaml"
        if not config_target.exists():
            shutil.copy2(src / "config.yaml", config_target)
        elif (src / "config.yaml").exists():
            shutil.copy2(src / "config.yaml", destination / "config.pack.yaml")

        if (src / "data" / "downloads").exists():
            target = destination / "data" / "downloads"
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src / "data" / "downloads", target)
            print("restored cached downloads")
    print(f"restored pack into {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--out", default="release", help="Output directory for the pack")
    parser.add_argument("--full", action="store_true", help="Include downloaded data")
    parser.add_argument("--restore", metavar="PACK", help="Restore this pack instead")
    parser.add_argument("--dest", default=".", help="Restore destination (default: .)")
    args = parser.parse_args()

    if args.restore:
        restore(args.restore, args.dest)
        return

    archive = build(args.config, Path(args.out), args.full)
    size_mb = archive.stat().st_size / (1 << 20)
    print(f"pack written: {archive} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
