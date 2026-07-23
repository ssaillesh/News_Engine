"""Command-line interface (Phase 1: introspection only, no collection).

Commands:
    archiver version   Print the package version.
    archiver config    Show the resolved configuration (secrets masked).
    archiver doctor    Validate that configuration loads and is consistent.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table

from archiver import __version__
from archiver.clients import BlockedError, ClientError, MastodonClient
from archiver.config.logging import configure_logging
from archiver.config.settings import get_settings
from archiver.sources.federal_register import ingest_federal_register
from archiver.sources.presidential_documents import ingest_presidential_documents
from archiver.sources.trump_news import ingest_news
from archiver.sources.white_house import ingest_white_house
from archiver.storage.db import Database

app = typer.Typer(
    help="Truth Social single-account archiver — Phase 1 scaffold (no collection code).",
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
    console.print(f"  target_handle     : {settings.target_handle}")
    console.print(f"  respect_robots    : {settings.respect_robots}")
    console.print(f"  enable_auth       : {settings.enable_auth}")
    console.print(f"  enable_html_fallbk: {settings.enable_html_fallback}")
    console.print(f"  download_media    : {settings.download_media}")
    console.print(
        "\n[dim]Note: no collection is implemented yet. "
        "See DESIGN.md §16 for the phased roadmap.[/]"
    )


@app.command()
def probe(
    acct: str = typer.Argument(..., help="Handle to look up on the configured API_BASE_URL"),
) -> None:
    """Look up an account on the configured Mastodon instance (exercises the client).

    Uses API_BASE_URL from config. If the instance blocks automated access, this
    reports the block and exits — it never attempts to circumvent it (docs/adr/0004).
    """
    settings = get_settings()
    configure_logging(settings)

    async def _run() -> None:
        async with MastodonClient.from_settings(settings) as client:
            account = await client.lookup_account(acct)
            table = Table(title=f"{acct} @ {settings.api_base_url}")
            table.add_column("field", style="cyan", no_wrap=True)
            table.add_column("value")
            fields = ("id", "username", "display_name", "followers_count", "statuses_count", "url")
            for key in fields:
                table.add_row(key, str(account.get(key)))
            console.print(table)

            count = 0
            async for _status in client.iter_account_statuses(
                str(account["id"]), limit=5, max_pages=1
            ):
                count += 1
            console.print(f"[green]✓[/] fetched {count} recent status(es) on the first page")

    try:
        asyncio.run(_run())
    except BlockedError as exc:
        console.print(f"[bold red]✗ Access blocked:[/] {exc}")
        console.print(
            "[dim]This instance blocks automated access. Halting without "
            "circumvention (see docs/adr/0004).[/]"
        )
        raise typer.Exit(code=2) from exc
    except ClientError as exc:
        console.print(f"[bold red]✗ Request failed:[/] {exc}")
        raise typer.Exit(code=1) from exc


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
