"""Command-line interface.

Commands:
    archiver version          Print the package version.
    archiver config           Show the resolved configuration (secrets masked).
    archiver doctor           Validate that configuration loads and is consistent.
    archiver ingest-*         Pull from one of the live sources into the archive.
    archiver score-sentiment  Run FinBERT over archived articles.
    archiver serve            Browse the archive in the web UI.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table

from archiver import __version__
from archiver.analysis import (
    DEFAULT_SOURCES,
    FINBERT_MODEL,
    SUMMARY_MODEL,
    ModelUnavailableError,
    ScoreReport,
    SummaryReport,
    score_statuses,
    summarize_statuses,
)
from archiver.analysis.stocks import (
    DEFAULT_MENTION_SOURCES,
    MentionReport,
    detect_mentions,
)
from archiver.clients import BlockedError, ClientError
from archiver.config.logging import configure_logging, mask_url
from archiver.config.settings import get_settings
from archiver.sources.federal_register import ingest_federal_register
from archiver.sources.nasdaq import refresh_market
from archiver.sources.presidential_documents import ingest_presidential_documents
from archiver.sources.publishers import ingest_publishers
from archiver.sources.trump_news import ingest_news
from archiver.sources.white_house import ingest_white_house
from archiver.storage.db import Database

app = typer.Typer(
    help="Trump news archiver — ingest official documents and news coverage, then browse them.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def version() -> None:
    """Print the package version."""
    console.print(f"archiver {__version__}")


@app.command()
def config() -> None:
    """Show the resolved configuration with secrets and URL credentials masked."""
    settings = get_settings()
    table = Table(title=f"Resolved configuration (profile: {settings.env})")
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    for key, value in settings.masked_dict().items():
        table.add_row(key, str(value))
    console.print(table)


@app.command()
def doctor() -> None:
    """Validate configuration loads and is internally consistent."""
    try:
        settings = get_settings()
        configure_logging(settings)
    except Exception as exc:  # noqa: BLE001 - surface any config error to the user
        console.print(f"[bold red]✗ Configuration invalid:[/] {exc}")
        raise typer.Exit(code=1) from exc

    console.print("[bold green]✓ Configuration valid.[/]")
    console.print(f"  profile           : {settings.env}")
    console.print(f"  database_url      : {mask_url(settings.database_url)}")
    console.print(f"  respect_robots    : {settings.respect_robots}")
    console.print(f"  rate_limit_rps    : {settings.rate_limit_rps}")
    console.print(f"  sentiment_model   : {settings.sentiment_model}")


@app.command(name="ingest-federal-register")
def ingest_federal_register_cmd(
    since: str = typer.Option(
        None, help="Only ingest documents published on/after this ISO date (YYYY-MM-DD)."
    ),
    max_pages: int = typer.Option(None, help="Cap the number of API pages (for a quick run)."),
    president: str = typer.Option("donald-trump", help="Federal Register president slug."),
    incremental: bool = typer.Option(
        False, "--incremental", help="Only fetch documents newer than the last run (checkpointed)."
    ),
) -> None:
    """Ingest Trump's official presidential documents from the Federal Register API.

    A free, open, public-domain government source — the compliant live feed of
    what Trump issues officially. Writes into the archive; safe to re-run (idempotent).
    Use --incremental on a schedule (cron/systemd) to pull only what's new.
    """
    settings = get_settings()
    configure_logging(settings)

    async def _run() -> int:
        database = Database(settings.database_url)
        try:
            await database.create_all()  # dev convenience; production uses `alembic upgrade head`
            return await ingest_federal_register(
                database,
                settings=settings,
                since=since,
                max_pages=max_pages,
                president=president,
                incremental=incremental,
            )
        finally:
            await database.dispose()

    count = asyncio.run(_run())
    console.print(f"[green]✓[/] ingested {count} presidential document(s) into the archive")


@app.command(name="ingest-white-house")
def ingest_white_house_cmd() -> None:
    """Ingest official statements/releases/messages from whitehouse.gov RSS.

    A robots-permitted, structured RSS source (no anti-bot barrier). Captures the
    latest ~30 items per feed, so run it on a schedule to accumulate history.
    Safe to re-run (idempotent).
    """
    settings = get_settings()
    configure_logging(settings)

    async def _run() -> int:
        database = Database(settings.database_url)
        try:
            await database.create_all()  # dev convenience; production uses `alembic upgrade head`
            return await ingest_white_house(database, settings=settings)
        finally:
            await database.dispose()

    try:
        count = asyncio.run(_run())
    except BlockedError as exc:
        console.print(f"[bold red]✗ Access blocked:[/] {exc}")
        raise typer.Exit(code=2) from exc
    except ClientError as exc:
        console.print(f"[bold red]✗ Request failed:[/] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]✓[/] ingested {count} White House item(s) into the archive")


@app.command(name="ingest-presidential-documents")
def ingest_presidential_documents_cmd(
    since: str = typer.Option(
        None, help="Only ingest documents issued on/after this ISO date (default: 120 days ago)."
    ),
    max_pages: int = typer.Option(None, help="Cap the number of API pages."),
) -> None:
    """Ingest Trump's remarks, statements, and messages from the Compilation of
    Presidential Documents (GovInfo API) — the official record of his own words.

    Uses GOVINFO_API_KEY (free from api.data.gov; DEMO_KEY works but is rate-limited).
    Safe to re-run (idempotent).
    """
    settings = get_settings()
    configure_logging(settings)
    start = since or (datetime.now(UTC) - timedelta(days=120)).date().isoformat()

    async def _run() -> int:
        database = Database(settings.database_url)
        try:
            await database.create_all()  # dev convenience; production uses `alembic upgrade head`
            return await ingest_presidential_documents(
                database, settings=settings, since=start, max_pages=max_pages
            )
        finally:
            await database.dispose()

    try:
        count = asyncio.run(_run())
    except BlockedError as exc:
        console.print(f"[bold red]✗ Access blocked:[/] {exc}")
        raise typer.Exit(code=2) from exc
    except ClientError as exc:
        console.print(f"[bold red]✗ Request failed:[/] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]✓[/] ingested {count} presidential document(s) since {start}")


@app.command(name="ingest-news")
def ingest_news_cmd(
    query: str = typer.Option("Donald Trump", help="Google News search query."),
    keyword: list[str] = typer.Option(
        None, "--keyword", help="Keep only items mentioning these (repeatable; default: trump)."
    ),
) -> None:
    """Ingest news coverage ABOUT Donald Trump from Google News RSS.

    Queries Google News for the given phrase, then keeps only items whose title or
    summary mentions the keyword(s) — a strict Donald-Trump guard. Stored under
    source 'news' with the publisher as the badge. Safe to re-run (idempotent).
    """
    settings = get_settings()
    configure_logging(settings)
    keywords = keyword or ["trump"]

    async def _run() -> int:
        database = Database(settings.database_url)
        try:
            await database.create_all()  # dev convenience; production uses `alembic upgrade head`
            return await ingest_news(database, settings=settings, query=query, keywords=keywords)
        finally:
            await database.dispose()

    try:
        count = asyncio.run(_run())
    except BlockedError as exc:
        console.print(f"[bold red]✗ Access blocked:[/] {exc}")
        raise typer.Exit(code=2) from exc
    except ClientError as exc:
        console.print(f"[bold red]✗ Request failed:[/] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]✓[/] ingested {count} Trump news item(s) matching {keywords}")


@app.command(name="ingest-publishers")
def ingest_publishers_cmd(
    keyword: list[str] = typer.Option(
        None, "--keyword", help="Keep only items mentioning these (repeatable; default: trump)."
    ),
    allow_duplicates: bool = typer.Option(
        False,
        "--allow-duplicates",
        help="Keep items whose headline already exists in the archive.",
    ),
) -> None:
    """Ingest Trump coverage from publishers' own RSS feeds, WITH summaries.

    Unlike Google News (whose RSS carries only a headline and an unresolvable
    redirect), outlets' own feeds include a publisher-written summary and a direct
    article link. Stored under source 'news' alongside the Google News items, with
    near-identical headlines skipped so the two sources don't double up.
    Safe to re-run (idempotent).
    """
    settings = get_settings()
    configure_logging(settings)
    keywords = keyword or ["trump"]

    async def _run() -> int:
        database = Database(settings.database_url)
        try:
            await database.create_all()  # dev convenience; production uses `alembic upgrade head`
            return await ingest_publishers(
                database,
                settings=settings,
                keywords=keywords,
                skip_duplicate_titles=not allow_duplicates,
            )
        finally:
            await database.dispose()

    try:
        count = asyncio.run(_run())
    except BlockedError as exc:
        console.print(f"[bold red]✗ Access blocked:[/] {exc}")
        raise typer.Exit(code=2) from exc
    except ClientError as exc:
        console.print(f"[bold red]✗ Request failed:[/] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]✓[/] ingested {count} publisher article(s) matching {keywords}")


@app.command()
def summarize(
    source: list[str] = typer.Option(
        None, "--source", help="Sources to summarize (repeatable; default: news)."
    ),
    model: str = typer.Option(SUMMARY_MODEL, help="HuggingFace summarization model id."),
    batch_size: int = typer.Option(4, min=1, help="Articles per forward pass."),
    limit: int = typer.Option(None, help="Cap how many items to summarize this run."),
    min_chars: int = typer.Option(
        400, help="Skip articles whose body is shorter than this (nothing to condense)."
    ),
    regenerate: bool = typer.Option(
        False, "--regenerate", help="Redo everything, not just new/changed items."
    ),
    device: str = typer.Option(
        None, help="Torch device, e.g. 'mps' or 'cuda' (default: CPU)."
    ),
) -> None:
    """Generate short abstractive summaries of archived articles.

    Offline enrichment — reads what's already archived, fetches nothing. The
    generated text is stored separately from the publisher's own summary and is
    labelled as machine-generated in the UI, because an abstractive paraphrase of
    political reporting is an interpretation, not a record.
    Needs the ML extra: pip install -e ".[sentiment]".
    """
    settings = get_settings()
    configure_logging(settings)
    sources = source or list(DEFAULT_SOURCES)

    async def _run() -> SummaryReport:
        database = Database(settings.database_url)
        try:
            await database.create_all()  # dev convenience; production uses `alembic upgrade head`
            return await summarize_statuses(
                database,
                sources=sources,
                model_name=model,
                batch_size=batch_size,
                limit=limit,
                min_chars=min_chars,
                regenerate=regenerate,
                device=device,
            )
        finally:
            await database.dispose()

    try:
        report = asyncio.run(_run())
    except ModelUnavailableError as exc:
        console.print(f"[bold red]✗ {exc}[/]")
        raise typer.Exit(code=1) from exc

    if report.summarized:
        console.print(f"[green]✓[/] summarized {report.summarized} article(s) with {model}")
    else:
        console.print("[green]✓[/] nothing to summarize — every article is already up to date")
    if report.skipped_short:
        console.print(
            f"[dim]skipped {report.skipped_short} item(s) with too little body text "
            f"(< {min_chars} chars) — nothing to condense[/]"
        )


@app.command(name="score-sentiment")
def score_sentiment_cmd(
    source: list[str] = typer.Option(
        None, "--source", help="Sources to score (repeatable; default: news)."
    ),
    model: str = typer.Option(FINBERT_MODEL, help="HuggingFace model id."),
    batch_size: int = typer.Option(16, min=1, help="Texts per forward pass."),
    limit: int = typer.Option(None, help="Cap how many items to score this run."),
    rescore: bool = typer.Option(
        False, "--rescore", help="Re-score everything, not just new/changed items."
    ),
    device: str = typer.Option(
        None, help="Torch device, e.g. 'mps' or 'cuda' (default: CPU)."
    ),
) -> None:
    """Score archived articles with FinBERT and store the sentiment readings.

    Offline enrichment — reads what's already archived, fetches nothing. Only new
    or edited items are scored unless --rescore is passed, so running this after
    each ingest is cheap. Needs the ML extra: pip install -e ".[sentiment]".
    """
    settings = get_settings()
    configure_logging(settings)
    sources = source or list(DEFAULT_SOURCES)

    async def _run() -> ScoreReport:
        database = Database(settings.database_url)
        try:
            await database.create_all()  # dev convenience; production uses `alembic upgrade head`
            return await score_statuses(
                database,
                sources=sources,
                model_name=model,
                batch_size=batch_size,
                limit=limit,
                rescore=rescore,
                device=device,
            )
        finally:
            await database.dispose()

    try:
        report = asyncio.run(_run())
    except ModelUnavailableError as exc:
        console.print(f"[bold red]✗ {exc}[/]")
        raise typer.Exit(code=1) from exc

    if not report.scored:
        console.print("[green]✓[/] nothing to score — every item is already up to date")
    else:
        console.print(f"[green]✓[/] scored {report.scored} item(s) with {model}")
        table = Table(title="Sentiment")
        table.add_column("label", style="cyan")
        table.add_column("count", justify="right")
        for label in ("positive", "neutral", "negative"):
            table.add_row(label, str(report.label_counts.get(label, 0)))
        console.print(table)
    if report.skipped_empty:
        console.print(f"[dim]skipped {report.skipped_empty} item(s) with no text[/]")


@app.command(name="detect-stocks")
def detect_stocks_cmd(
    source: list[str] = typer.Option(
        None,
        "--source",
        help="Sources to scan (repeatable; default: his words + coverage).",
    ),
) -> None:
    """Detect publicly-traded companies Trump named, forming the watchlist.

    Scans archived text with a curated ticker dictionary (word-boundary matched,
    so 'Intel' never fires on 'intelligence'). The distinct companies found drive
    the market refresh and the Upcoming Reports tab. Offline; safe to re-run.
    """
    settings = get_settings()
    configure_logging(settings)
    sources = source or list(DEFAULT_MENTION_SOURCES)

    async def _run() -> MentionReport:
        database = Database(settings.database_url)
        try:
            await database.create_all()  # dev convenience; production uses `alembic upgrade head`
            return await detect_mentions(database, sources=sources)
        finally:
            await database.dispose()

    report = asyncio.run(_run())
    console.print(
        f"[green]✓[/] scanned {report.scanned} item(s); "
        f"found {report.mentions} mention(s) of {len(report.ticker_counts)} company(ies)"
    )
    if report.ticker_counts:
        table = Table(title="Watchlist (companies Trump mentioned)")
        table.add_column("ticker", style="cyan")
        table.add_column("mentions", justify="right")
        for ticker, count in sorted(
            report.ticker_counts.items(), key=lambda kv: kv[1], reverse=True
        ):
            table.add_row(ticker, str(count))
        console.print(table)


@app.command(name="refresh-market")
def refresh_market_cmd(
    horizon_days: int = typer.Option(
        75, help="How many days ahead to scan for the next earnings date."
    ),
) -> None:
    """Refresh live quotes and next-earnings dates for the watchlist (Nasdaq).

    Reads the watchlist produced by `detect-stocks`, fetches a quote and the next
    quarterly report date for each company from Nasdaq's public API (no key), and
    caches them so the dashboard never blocks on the network. Run `detect-stocks`
    first. Safe to re-run; overwrites the cache in place.
    """
    settings = get_settings()
    configure_logging(settings)

    async def _run() -> int:
        database = Database(settings.database_url)
        try:
            await database.create_all()  # dev convenience; production uses `alembic upgrade head`
            return await refresh_market(database, settings=settings, horizon_days=horizon_days)
        finally:
            await database.dispose()

    try:
        count = asyncio.run(_run())
    except BlockedError as exc:
        console.print(f"[bold red]✗ Access blocked:[/] {exc}")
        raise typer.Exit(code=2) from exc
    except ClientError as exc:
        console.print(f"[bold red]✗ Request failed:[/] {exc}")
        raise typer.Exit(code=1) from exc

    if count:
        console.print(f"[green]✓[/] refreshed market data for {count} company(ies)")
    else:
        console.print(
            "[yellow]No watchlist yet.[/] Run [bold]archiver detect-stocks[/] first "
            "to find companies Trump mentioned."
        )


@app.command()
def serve(
    host: str = typer.Option(None, help="Bind host (default from config: web_host)."),
    port: int = typer.Option(None, help="Bind port (default from config: web_port)."),
) -> None:
    """Launch the read-only web UI for browsing the archive.

    Defaults to 127.0.0.1:8137 (not :8000, which commonly collides with other dev
    servers/SSH tunnels). If the chosen port is busy, the next free one is used.
    """
    import uvicorn

    from archiver.web import create_app, find_free_port

    settings = get_settings()
    configure_logging(settings)

    bind_host = host or settings.web_host
    requested = port or settings.web_port
    bind_port = find_free_port(bind_host, requested)
    if bind_port != requested:
        console.print(f"[yellow]Port {requested} is busy — using {bind_port} instead.[/]")

    application = create_app(Database(settings.database_url))
    console.print(
        f"[green]Trump News Archive[/] → [bold]http://{bind_host}:{bind_port}[/]  (Ctrl+C to stop)"
    )
    uvicorn.run(application, host=bind_host, port=bind_port, log_level="warning")
