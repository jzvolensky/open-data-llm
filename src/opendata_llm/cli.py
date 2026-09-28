from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import Config
from .http import HttpClient
from .store import Catalog

app = typer.Typer(add_completion=False, help="Bratislava open data RAG toolkit.")
ingest_app = typer.Typer(help="Ingest catalog metadata and layer schemas.")
graph_app = typer.Typer(help="Build and query the semantic knowledge graph.")
index_app = typer.Typer(help="Build and inspect the retrieval index.")
data_app = typer.Typer(help="Query cached tables and live ArcGIS services.")
geo_app = typer.Typer(help="District gazetteer and spatial queries.")
app.add_typer(ingest_app, name="ingest")
app.add_typer(graph_app, name="graph")
app.add_typer(index_app, name="index")
app.add_typer(data_app, name="data")
app.add_typer(geo_app, name="geo")
console = Console()


def _open(config_path: str | None) -> tuple[Config, Catalog, HttpClient]:
    config = Config.load(config_path)
    catalog = Catalog(config.paths.db)
    client = HttpClient(
        base_url=config.portal.base_url,
        user_agent=config.portal.user_agent,
        timeout=config.portal.request_timeout,
        max_retries=config.portal.max_retries,
    )
    return config, catalog, client


@graph_app.command("build")
def graph_build(
    config: str | None = typer.Option(None, "--config", "-c"),
    with_related: bool = typer.Option(False, help="Fetch curated Hub 'related' links"),
    top_k: int = typer.Option(10, help="Similarity neighbours per dataset"),
    concurrency: int = typer.Option(6, help="Parallel requests for curated links"),
) -> None:
    """Build the knowledge graph from the catalog."""
    from .semantic.graph import Graph

    cfg, catalog, client = _open(config)
    graph = Graph(catalog.con)
    with catalog, console.status("Building knowledge graph..."):
        try:
            stats = graph.build(
                client=client if with_related else None,
                search_collection=cfg.portal.search_collection,
                with_related=with_related,
                top_k=top_k,
                concurrency=concurrency,
            )
        finally:
            client.close()
    console.print(f"[green]Graph built.[/green] {stats}")


@graph_app.command("related")
def graph_related(
    dataset: str = typer.Argument(..., help="dataset_id or prefix"),
    config: str | None = typer.Option(None, "--config", "-c"),
    rel: str | None = typer.Option(None, help="Filter by relation type"),
    limit: int = typer.Option(20, help="Max neighbours"),
) -> None:
    """Show graph neighbours of a dataset."""
    from .semantic.graph import Graph

    cfg, catalog, client = _open(config)
    client.close()
    with catalog:
        dataset_id = _resolve_dataset(catalog, dataset)
        if not dataset_id:
            raise typer.BadParameter(f"no dataset matches {dataset!r}")
        graph = Graph(catalog.con)
        table = Table(title=f"Neighbours of {dataset_id}")
        table.add_column("rel")
        table.add_column("weight", justify="right")
        table.add_column("type")
        table.add_column("label")
        for node in graph.neighbours(dataset_id, rel, limit):
            table.add_row(
                node["rel"], f"{node['weight']:.3f}", node["node_type"], node["label"] or ""
            )
        console.print(table)


@index_app.command("build")
def index_build(config: str | None = typer.Option(None, "--config", "-c")) -> None:
    """Generate dataset cards, embeddings and the BM25 index."""
    from .index.pipeline import build_index

    cfg, catalog, client = _open(config)
    client.close()
    with catalog, console.status("Building cards + embeddings (Ollama)..."):
        stats = build_index(cfg, catalog)
    console.print(f"[green]Index built.[/green] {stats}")


@app.command("card")
def card_cmd(
    dataset: str = typer.Argument(..., help="dataset_id or prefix"),
    config: str | None = typer.Option(None, "--config", "-c"),
) -> None:
    """Print the retrieval card for a dataset."""
    from .index.store import SearchIndex

    cfg, catalog, client = _open(config)
    client.close()
    with catalog:
        dataset_id = _resolve_dataset(catalog, dataset)
        if not dataset_id:
            raise typer.BadParameter(f"no dataset matches {dataset!r}")
        index = SearchIndex(catalog.con, cfg.embeddings.dim)
        text = index.card(dataset_id)
    console.print(text or f"[yellow]No card for {dataset_id}[/yellow]")


@app.command("search")
def search_cmd(
    query: str = typer.Argument(..., help="Natural-language query (SK or EN)"),
    config: str | None = typer.Option(None, "--config", "-c"),
    top_k: int | None = typer.Option(None, help="Number of results"),
    candidates: int | None = typer.Option(None, help="Candidates per retriever"),
    rerank: bool | None = typer.Option(None, "--rerank/--no-rerank"),
) -> None:
    """Hybrid search over the dataset cards."""
    from .index.embed import OllamaEmbedder
    from .index.store import SearchIndex
    from .retrieve.hybrid import HybridRetriever

    cfg, catalog, client = _open(config)
    client.close()
    index = SearchIndex(catalog.con, cfg.embeddings.dim)
    embedder = OllamaEmbedder(
        model=cfg.embeddings.model,
        host=cfg.embeddings.host,
        timeout=cfg.embeddings.timeout,
        batch_size=cfg.embeddings.batch_size,
    )
    try:
        with catalog:
            retriever = HybridRetriever(catalog, index, embedder, cfg)
            results = retriever.search(query, top_k, candidates, rerank)
    finally:
        embedder.close()

    table = Table(title=f"Results for: {query}")
    table.add_column("#", justify="right")
    table.add_column("score", justify="right")
    table.add_column("title")
    table.add_column("témy")
    table.add_column("type")
    for rank, result in enumerate(results, start=1):
        table.add_row(
            str(rank),
            f"{result.score:.4f}",
            (result.title or "")[:60],
            ", ".join(result.concept_labels("sk")[:3]),
            result.item_type or "",
        )
    console.print(table)
    for result in results:
        console.print(f"[dim]{result.dataset_id}[/dim]  {result.url or ''}")


@geo_app.command("build")
def geo_build(config: str | None = typer.Option(None, "--config", "-c")) -> None:
    """Fetch district boundaries and link datasets to districts."""
    from .geo.gazetteer import build_gazetteer

    cfg, catalog, client = _open(config)
    with catalog, client, console.status("Building gazetteer..."):
        stats = build_gazetteer(cfg, catalog, client)
    console.print(f"[green]Gazetteer built.[/green] {stats}")


@geo_app.command("load")
def geo_load(
    config: str | None = typer.Option(None, "--config", "-c"),
    limit: int | None = typer.Option(None, help="Max spatial layers"),
) -> None:
    """Load spatial GeoJSON layers into DuckDB."""
    from .geo.layers import load_spatial_layers

    cfg, catalog, client = _open(config)
    client.close()
    with catalog, console.status("Loading spatial layers..."):
        stats = load_spatial_layers(catalog, limit=limit)
    console.print(
        f"[green]Spatial layers loaded.[/green] {stats['ok']} ok / {stats['failed']} failed"
    )
    for error in stats.get("errors_sample", []):
        console.print(f"[yellow]  {error}[/yellow]")


@geo_app.command("places")
def geo_places(config: str | None = typer.Option(None, "--config", "-c")) -> None:
    """List districts in the gazetteer."""
    from .geo.query import list_places

    cfg, catalog, client = _open(config)
    client.close()
    with catalog:
        rows = list_places(catalog)
    table = Table(title=f"{len(rows)} districts")
    table.add_column("slug")
    table.add_column("name")
    for row in rows:
        table.add_row(row["slug"] or "", row["name"] or "")
    console.print(table)


@geo_app.command("datasets")
def geo_datasets(
    place: str = typer.Option(..., "--place", help="District slug or name"),
    config: str | None = typer.Option(None, "--config", "-c"),
    limit: int = typer.Option(20, help="Max results"),
) -> None:
    """Datasets covering a district (by extent or text mention)."""
    from .geo.query import datasets_in_district
    from .semantic import vocab

    cfg, catalog, client = _open(config)
    client.close()
    with catalog:
        slug = vocab.place_slug(place) or place.lower()
        rows = datasets_in_district(catalog, slug, limit=limit)
    table = Table(title=f"Datasets for {slug} ({len(rows)})")
    table.add_column("source")
    table.add_column("dataset")
    for row in rows:
        table.add_row(row["source"], (row["title"] or row["dataset_id"])[:70])
    console.print(table)


@geo_app.command("point")
def geo_point(
    lon: float = typer.Option(..., "--lon"),
    lat: float = typer.Option(..., "--lat"),
    config: str | None = typer.Option(None, "--config", "-c"),
    limit: int = typer.Option(20, help="Max results"),
) -> None:
    """Which district and spatial datasets contain a coordinate."""
    from .geo.query import datasets_at_point, district_at

    cfg, catalog, client = _open(config)
    client.close()
    with catalog:
        district = district_at(catalog, lon, lat)
        rows = datasets_at_point(catalog, lon, lat, limit=limit)
    console.print(f"District: [bold]{district['name'] if district else 'unknown'}[/bold]")
    table = Table(title=f"{len(rows)} datasets contain the point")
    table.add_column("matches", justify="right")
    table.add_column("dataset")
    for row in rows:
        table.add_row(str(row["matches"]), (row["title"] or "")[:70])
    console.print(table)


@data_app.command("load")
def data_load(
    config: str | None = typer.Option(None, "--config", "-c"),
    limit: int | None = typer.Option(None, help="Max CSV datasets to load"),
    materialize: bool = typer.Option(False, help="Copy data into tables instead of views"),
) -> None:
    """Expose downloaded CSV files as DuckDB tables/views."""
    from .query.load import load_csv_tables

    cfg, catalog, client = _open(config)
    client.close()
    with catalog, console.status("Loading CSV tables..."):
        stats = load_csv_tables(catalog, limit=limit, materialize=materialize)
    console.print(
        f"[green]Loaded CSV tables.[/green] {stats['ok']} ok / {stats['failed']} failed"
    )
    for error in stats.get("errors_sample", []):
        console.print(f"[yellow]  {error}[/yellow]")


@data_app.command("profile")
def data_profile(
    config: str | None = typer.Option(None, "--config", "-c"),
    limit: int | None = typer.Option(None, help="Max datasets to profile"),
    max_distinct: int | None = typer.Option(None, help="Max distinct values per column"),
) -> None:
    """Build the low-cardinality value dictionary (column_values)."""
    from .query.profile import MAX_DISTINCT, profile_columns

    cfg, catalog, client = _open(config)
    client.close()
    with catalog, console.status("Profiling column values..."):
        stats = profile_columns(
            catalog, max_distinct=max_distinct or MAX_DISTINCT, limit=limit
        )
    console.print(
        f"[green]Profiled columns.[/green] {stats['columns']} columns / "
        f"{stats['values']} values from {stats['ok']} tables"
    )
    for error in stats.get("errors_sample", []):
        console.print(f"[yellow]  {error}[/yellow]")


@data_app.command("list")
def data_list(config: str | None = typer.Option(None, "--config", "-c")) -> None:
    """List cached data tables."""
    from .query.load import list_tables

    cfg, catalog, client = _open(config)
    client.close()
    with catalog:
        rows = list_tables(catalog)
    table = Table(title=f"{len(rows)} cached tables")
    table.add_column("rows", justify="right")
    table.add_column("status")
    table.add_column("table")
    table.add_column("dataset")
    for row in rows[:100]:
        table.add_row(
            str(row["rows"]), str(row["status"]), row["table_name"], row["dataset_id"][:50]
        )
    console.print(table)


@data_app.command("sql")
def data_sql(
    sql: str = typer.Argument(..., help="Read-only SQL over the catalog/tables"),
    config: str | None = typer.Option(None, "--config", "-c"),
    max_rows: int = typer.Option(50, help="Max rows to display"),
) -> None:
    """Run a read-only SQL query against DuckDB."""
    from .query.sql import run_sql

    cfg, catalog, client = _open(config)
    client.close()
    with catalog:
        columns, rows = run_sql(catalog.con, sql, max_rows=max_rows)
    _print_rows(columns, rows)


@data_app.command("live")
def data_live(
    dataset: str = typer.Argument(..., help="dataset_id or prefix"),
    config: str | None = typer.Option(None, "--config", "-c"),
    where: str = typer.Option("1=1", help="ArcGIS WHERE clause"),
    columns: str = typer.Option("*", help="Comma-separated fields"),
    limit: int = typer.Option(25, help="Max rows"),
    count_only: bool = typer.Option(False, "--count", help="Return only the count"),
    order_by: str | None = typer.Option(None, help="ArcGIS orderByFields"),
) -> None:
    """Query a dataset's live ArcGIS FeatureServer."""
    from .query.arcgis import ArcGISClient

    cfg, catalog, client = _open(config)
    with catalog:
        dataset_id = _resolve_dataset(catalog, dataset)
        if not dataset_id:
            client.close()
            raise typer.BadParameter(f"no dataset matches {dataset!r}")
        row = catalog.con.execute(
            "SELECT service_url, title FROM datasets WHERE dataset_id = ?", [dataset_id]
        ).fetchone()
        if not row or not row[0]:
            client.close()
            raise typer.BadParameter(f"dataset {dataset_id} has no ArcGIS service")
        service_url, title = row
        arcgis = ArcGISClient(client)
        try:
            if count_only:
                console.print(f"{title}: {arcgis.count(service_url, where)}")
                return
            payload = arcgis.query(
                service_url, where=where, out_fields=columns, limit=limit, order_by=order_by
            )
        finally:
            client.close()
    features = payload.get("features", [])
    fields = [f["name"] for f in payload.get("fields", [])] or ["attributes"]
    rows = [tuple(f.get("attributes", {}).get(name) for name in fields) for f in features]
    _print_rows(fields, rows)


def _print_rows(columns: list[str], rows: list[tuple[object, ...]]) -> None:
    table = Table(show_lines=False)
    for column in columns:
        table.add_column(str(column))
    for row in rows:
        table.add_row(*[str(value) for value in row])
    console.print(table)


@app.command("eval")
def eval_cmd(
    config: str | None = typer.Option(None, "--config", "-c"),
    questions: str | None = typer.Option(None, help="Path to questions.jsonl"),
    qtype: str = typer.Option(
        "all", "--type", help="all|discovery|data|geo|abstain|followup"
    ),
    top_k: int | None = typer.Option(None, help="Results per query"),
    candidates: int | None = typer.Option(None, help="Candidates per retriever"),
    rerank: bool | None = typer.Option(None, "--rerank/--no-rerank"),
    report: bool = typer.Option(True, "--report/--no-report", help="Write a dated JSON report"),
    provider: str | None = typer.Option(None, help="Override generation provider"),
) -> None:
    """Evaluate retrieval and data answering against the typed gold set."""
    from .eval.run import DATA_TYPES, TYPES, evaluate, load_questions, write_report
    from .generate import build_generator

    if qtype != "all" and qtype not in TYPES:
        raise typer.BadParameter(f"--type must be all or one of {', '.join(TYPES)}")

    cfg, catalog, client = _open(config)
    client.close()
    selected = load_questions(questions)
    if qtype != "all":
        selected = [q for q in selected if q.type == qtype]

    generator = None
    rewrite = None
    if any(q.type in DATA_TYPES for q in selected):
        if provider:
            cfg.generation.provider = provider
        generator = build_generator(cfg)

        def rewrite(query: str, turns: list[dict[str, str]]) -> str:
            from .generate.rag import rewrite_query

            assert generator is not None
            return rewrite_query(generator, query, turns)

    with catalog, console.status(f"Evaluating ({qtype})..."):
        result = evaluate(
            cfg,
            catalog,
            selected,
            top_k,
            candidates,
            rerank,
            generator=generator,
            rewrite=rewrite,
        )

    table = Table(
        title=f"Eval ({qtype}, top_k={result['top_k']}, rerank={result['rerank']})"
    )
    table.add_column("id")
    table.add_column("type")
    table.add_column("ok", justify="center")
    table.add_column("ms", justify="right")
    table.add_column("query")
    for row in result["details"]:
        if row.get("skipped"):
            mark = "·"
        else:
            mark = "✓" if row.get("passed") else "✗"
        ms = row.get("data_ms", row["retrieval_ms"])
        table.add_row(row["id"], row["type"], mark, f"{ms:.0f}", row["query"][:44])
    console.print(table)
    console.print(
        f"[bold]recall@k={result['recall@k']:.3f}  MRR={result['mrr']:.3f}  "
        f"nDCG@k={result['ndcg@k']:.3f}  exec={result['execution_accuracy']:.3f}  "
        f"abstain={result['abstention_accuracy']:.3f}  "
        f"resolve={result['resolution_accuracy']:.3f}  "
        f"geo={result['geo_accuracy']:.3f}  ({result['questions']} questions)[/bold]"
    )
    latency = result["latency"]
    console.print(
        f"[dim]latency ms · retrieval p50={latency['retrieval_ms']['p50']} "
        f"p90={latency['retrieval_ms']['p90']} p95={latency['retrieval_ms']['p95']} · "
        f"data p50={latency['data_ms']['p50']} p90={latency['data_ms']['p90']} "
        f"p95={latency['data_ms']['p95']}[/dim]"
    )
    if report:
        path = write_report(result, Path(cfg.root) / "reports" / "eval")
        console.print(f"[dim]report: {path}[/dim]")


@app.command("ask")
def ask_cmd(
    query: str = typer.Argument(..., help="Question in Slovak or English"),
    config: str | None = typer.Option(None, "--config", "-c"),
    top_k: int | None = typer.Option(None, help="Number of datasets for context"),
    rerank: bool | None = typer.Option(None, "--rerank/--no-rerank"),
    provider: str | None = typer.Option(None, help="Override generation provider"),
    turn: list[str] | None = typer.Option(
        None, "--turn", help="Previous turn as role:content (repeatable)"
    ),
) -> None:
    """Answer a question grounded in the catalog."""
    from .generate import build_generator
    from .generate.rag import rag_answer

    cfg, catalog, client = _open(config)
    client.close()
    if provider:
        cfg.generation.provider = provider
    generator = build_generator(cfg)
    history = _parse_turns(turn)
    with catalog, console.status("Retrieving and generating..."):
        result = rag_answer(
            cfg, catalog, query, generator, top_k=top_k, rerank=rerank, history=history
        )

    console.print(Panel(result.answer, title=f"ask (intent={result.intent})"))
    if result.data:
        console.print(f"[dim]SQL: {result.data.get('sql')}[/dim]")
    table = Table(title="Sources")
    table.add_column("#", justify="right")
    table.add_column("dataset")
    table.add_column("url")
    for index, source in enumerate(result.sources[:8], start=1):
        table.add_row(str(index), (source["title"] or "")[:45], source["url"] or "")
    console.print(table)


@app.command("serve")
def serve_cmd(
    config: str | None = typer.Option(None, "--config", "-c"),
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(8000, help="Bind port"),
) -> None:
    """Serve the web API."""
    import uvicorn

    from .app.api import create_app

    uvicorn.run(create_app(config), host=host, port=port)


@app.command("mcp")
def mcp_cmd(config: str | None = typer.Option(None, "--config", "-c")) -> None:
    """Run the MCP server over stdio."""
    from .mcp_server import create_server

    create_server(config).run()


def _parse_turns(turns: list[str] | None) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for turn in turns or []:
        role, separator, content = turn.partition(":")
        if not separator:
            role, content = "user", turn
        history.append({"role": role.strip() or "user", "content": content.strip()})
    return history


def _resolve_dataset(catalog: Catalog, needle: str) -> str | None:
    row = catalog.con.execute(
        "SELECT dataset_id FROM datasets WHERE dataset_id = ? OR item_id = ? "
        "OR dataset_id LIKE ? OR lower(title) LIKE ? "
        "ORDER BY length(dataset_id) LIMIT 1",
        [needle, needle, f"%{needle}%", f"%{needle.lower()}%"],
    ).fetchone()
    return row[0] if row else None


@app.command()
def status(config: str | None = typer.Option(None, "--config", "-c")) -> None:
    """Show catalog contents."""
    cfg, catalog, client = _open(config)
    client.close()
    with catalog:
        table = Table(title=f"Catalog: {cfg.paths.db}")
        table.add_column("metric")
        table.add_column("value", justify="right")
        for key, value in catalog.stats().items():
            table.add_row(key, str(value))
        console.print(table)

        formats = catalog.format_breakdown()
        if formats:
            fmt_table = Table(title="Distribution formats")
            fmt_table.add_column("format")
            fmt_table.add_column("count", justify="right")
            for fmt, count in formats:
                fmt_table.add_row(str(fmt), str(count))
            console.print(fmt_table)


@ingest_app.command("catalog")
def ingest_catalog_cmd(config: str | None = typer.Option(None, "--config", "-c")) -> None:
    """Fetch DCAT + Hub search records and rebuild the catalog."""
    from .ingest.catalog import ingest_catalog

    cfg, catalog, client = _open(config)
    with catalog, client, console.status("Fetching DCAT + search records..."):
        stats = ingest_catalog(cfg, catalog, client)
    console.print(f"[green]Catalog ingested.[/green] {stats}")


@ingest_app.command("features")
def ingest_features_cmd(
    config: str | None = typer.Option(None, "--config", "-c"),
    limit: int | None = typer.Option(None, help="Max datasets to fetch"),
    concurrency: int | None = typer.Option(None, help="Parallel requests"),
) -> None:
    """Fetch ArcGIS layer schemas (fields, geometry, extent) for datasets."""
    from .ingest.features import ingest_features

    cfg, catalog, client = _open(config)
    with catalog, client, console.status("Fetching layer metadata..."):
        stats = ingest_features(cfg, catalog, client, limit=limit, concurrency=concurrency)
    console.print(
        f"[green]Layer metadata fetched.[/green] "
        f"{stats['ok']} ok / {stats['failed']} failed of {stats['targets']}"
    )
    for error in stats.get("errors_sample", []):
        console.print(f"[yellow]  {error}[/yellow]")


@app.command()
def download(
    config: str | None = typer.Option(None, "--config", "-c"),
    item: list[str] | None = typer.Option(None, "--item", help="Only this item id"),
    fmt: list[str] | None = typer.Option(None, "--format", help="Only this format"),
    max_bytes: int | None = typer.Option(None, help="Per-file size limit in bytes"),
    limit: int | None = typer.Option(None, help="Max files to download"),
    concurrency: int = typer.Option(6, help="Parallel downloads"),
) -> None:
    """Download distribution files (CSV/GeoJSON/...) with a size cap."""
    from .ingest.download import download_datasets

    cfg, catalog, client = _open(config)
    with catalog, client, console.status("Downloading distributions..."):
        stats = download_datasets(
            cfg,
            catalog,
            client,
            item_ids=item,
            formats=fmt,
            max_bytes=max_bytes,
            limit=limit,
            concurrency=concurrency,
        )
    console.print(f"[green]Download complete.[/green] {stats}")
    console.print(f"Files in {Path(cfg.paths.downloads)}")


if __name__ == "__main__":
    app()
