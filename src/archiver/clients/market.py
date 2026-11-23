"""Market data clients: Finnhub (quotes, profiles, fundamentals, news) and Yahoo
(daily price history).

Why two providers: Finnhub's free tier covers everything the hub needs except
historical candles, which it reserves for paid plans. Yahoo's chart endpoint
fills that gap. It is unofficial and can change without notice, so it is kept
behind the same small interface and every failure surfaces as a ClientError.

Both clients only parse; nothing here touches the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import httpx

from archiver.clients.base import BaseHttpClient
from archiver.clients.exceptions import ClientError, NotFoundError
from archiver.clients.rate_limit import RateLimiter, TokenBucket

if TYPE_CHECKING:
    from archiver.config.settings import Settings

FINNHUB_BASE = "https://finnhub.io/api/v1"
POLYGON_BASE = "https://api.polygon.io"  # Massive; api.massive.com is equivalent
YAHOO_BASE = "https://query1.finance.yahoo.com"
POLYMARKET_BASE = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB_BASE = "https://clob.polymarket.com"

# The fundamentals worth showing on a ticker page, out of Finnhub's ~130.
METRIC_KEYS = (
    "peTTM",
    "epsTTM",
    "pbAnnual",
    "psTTM",
    "beta",
    "52WeekHigh",
    "52WeekLow",
    "52WeekPriceReturnDaily",
    "dividendYieldIndicatedAnnual",
    "grossMarginTTM",
    "operatingMarginTTM",
    "netProfitMarginTTM",
    "roeTTM",
    "revenueGrowthTTMYoy",
    "epsGrowthTTMYoy",
    "totalDebt/totalEquityQuarterly",
    "currentRatioQuarterly",
    "10DayAverageTradingVolume",
)

# Yahoo range strings accepted by the price endpoint.
YAHOO_RANGES = ("1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max")


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out  # drop NaN


def _with_transport(
    client: BaseHttpClient, transport: httpx.AsyncBaseTransport | None, headers: dict[str, str]
) -> None:
    """Swap in extra headers and, for tests, a mock transport."""
    base = client._client  # noqa: SLF001 - one place that reaches in
    merged = {**base.headers, **headers}
    if transport is None:
        base.headers.update(headers)
        return
    client._client = httpx.AsyncClient(  # noqa: SLF001
        base_url=base.base_url, headers=merged, transport=transport, timeout=base.timeout
    )


# ── Finnhub ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Quote:
    price: float | None
    change: float | None
    pct_change: float | None
    day_open: float | None
    day_high: float | None
    day_low: float | None
    prev_close: float | None
    at: datetime | None


class FinnhubClient(BaseHttpClient):
    """Thin async wrapper over the free Finnhub REST endpoints.

    The key goes in the ``X-Finnhub-Token`` header rather than the query string,
    so it never appears in a logged URL or an error message.
    """

    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        **kwargs: Any,
    ) -> None:
        if not api_key:
            raise ClientError("FINNHUB_API_KEY is not set")
        super().__init__(FINNHUB_BASE, **kwargs)
        _with_transport(self, transport, {"X-Finnhub-Token": api_key})

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        rate_limiter: RateLimiter | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> FinnhubClient:
        return cls(
            settings.finnhub_api_key,
            transport=transport,
            user_agent=settings.user_agent,
            timeout_s=min(settings.http_timeout_s, 15.0),
            # Fail fast: a blocked or down provider should cost seconds, not
            # minutes. The shared defaults (5 retries, 60s cap) suit bulk archiving.
            max_retries=min(settings.http_max_retries, 2),
            backoff_base_s=settings.backoff_base_s,
            backoff_cap_s=min(settings.backoff_cap_s, 8.0),
            rate_limiter=rate_limiter or TokenBucket(settings.finnhub_rps),
        )

    async def _get(self, path: str, **params: Any) -> Any:
        return (await self.request_json("GET", path, params=params)).data

    async def quote(self, ticker: str) -> Quote:
        data = await self._get("/quote", symbol=ticker)
        # Unknown symbols come back as all zeros rather than an error.
        if not data or not _num(data.get("c")):
            raise NotFoundError(f"no quote for {ticker}", url="/quote")
        stamp = data.get("t")
        return Quote(
            price=_num(data.get("c")),
            change=_num(data.get("d")),
            pct_change=_num(data.get("dp")),
            day_open=_num(data.get("o")),
            day_high=_num(data.get("h")),
            day_low=_num(data.get("l")),
            prev_close=_num(data.get("pc")),
            at=datetime.fromtimestamp(stamp, UTC) if stamp else None,
        )

    async def profile(self, ticker: str) -> dict[str, Any]:
        """Company profile mapped onto ``securities`` columns ({} if unknown)."""
        data = await self._get("/stock/profile2", symbol=ticker) or {}
        if not data:
            return {}
        cap_m = _num(data.get("marketCapitalization"))  # Finnhub reports millions
        shares_m = _num(data.get("shareOutstanding"))
        return {
            "name": data.get("name"),
            "exchange": data.get("exchange"),
            "currency": data.get("currency"),
            "country": data.get("country"),
            "industry": data.get("finnhubIndustry"),
            "logo_url": data.get("logo") or None,
            "web_url": data.get("weburl") or None,
            "ipo_date": data.get("ipo") or None,
            "market_cap": cap_m * 1e6 if cap_m is not None else None,
            "shares_outstanding": shares_m * 1e6 if shares_m is not None else None,
        }

    async def metrics(self, ticker: str) -> dict[str, float]:
        data = await self._get("/stock/metric", symbol=ticker, metric="all") or {}
        raw = data.get("metric") or {}
        return {k: v for k in METRIC_KEYS if (v := _num(raw.get(k))) is not None}

    async def recommendation(self, ticker: str) -> dict[str, Any] | None:
        """The most recent monthly analyst recommendation trend, if any."""
        rows = await self._get("/stock/recommendation", symbol=ticker) or []
        if not rows:
            return None
        latest = max(rows, key=lambda r: r.get("period") or "")
        keys = ("period", "strongBuy", "buy", "hold", "sell", "strongSell")
        return {k: latest.get(k) for k in keys}

    async def company_news(self, ticker: str, start: date, end: date) -> list[dict[str, Any]]:
        rows = await self._get(
            "/company-news", symbol=ticker, **{"from": start.isoformat(), "to": end.isoformat()}
        )
        return list(rows or [])

    async def symbols(self, exchange: str = "US") -> list[dict[str, Any]]:
        """Every listed symbol on an exchange group (~30k for US) in one call."""
        return list(await self._get("/stock/symbol", exchange=exchange) or [])

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, str]]:
        data = await self._get("/search", q=query) or {}
        out = []
        for row in data.get("result") or []:
            symbol = row.get("symbol") or ""
            # US listings only: a one-letter share class ("BRK.B") is fine, an
            # exchange suffix ("AAPL.MX") is a foreign listing.
            suffix = symbol.rsplit(".", 1)[1] if "." in symbol else ""
            if row.get("type") not in ("Common Stock", "ADR", "ETP") or len(suffix) > 1:
                continue
            out.append({"ticker": symbol, "name": row.get("description") or ""})
            if len(out) >= limit:
                break
        return out


# ── Yahoo (daily bars) ───────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Bar:
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adj_close: float | None
    volume: int | None


def parse_chart(payload: dict[str, Any], ticker: str) -> list[Bar]:
    """Turn a Yahoo v8 chart response into bars, oldest first."""
    chart = (payload or {}).get("chart") or {}
    if chart.get("error"):
        raise NotFoundError(f"yahoo chart error for {ticker}: {chart['error']}", url="/chart")
    results = chart.get("result") or []
    if not results:
        raise NotFoundError(f"no price data for {ticker}", url="/chart")
    result = results[0]
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    adj = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
    bars: list[Bar] = []
    for i, ts in enumerate(stamps):
        close = _num(quote.get("close", [None] * len(stamps))[i])
        if close is None:  # holidays and partial rows
            continue
        volume = _num(quote.get("volume", [None] * len(stamps))[i])
        bars.append(
            Bar(
                date=datetime.fromtimestamp(ts, UTC).date(),
                open=_num(quote.get("open", [None] * len(stamps))[i]),
                high=_num(quote.get("high", [None] * len(stamps))[i]),
                low=_num(quote.get("low", [None] * len(stamps))[i]),
                close=close,
                adj_close=_num(adj[i]) if i < len(adj) else close,
                volume=int(volume) if volume is not None else None,
            )
        )
    return bars


SPARK_BATCH = 20  # Yahoo's spark endpoint accepts up to 20 symbols per call

# ── non-US listings ──────────────────────────────────────────────────────────
# Exchange suffixes, as Yahoo writes them: Toronto, TSX Venture, Cboe Canada
# (NEO), Canadian Securities Exchange. Finnhub's free plan refuses all of these,
# so their profile, quote and history come from Yahoo alone.
EXCHANGE_SUFFIXES = (".TO", ".V", ".NE", ".CN")


def is_foreign(ticker: str) -> bool:
    """True for a symbol carrying a non-US exchange suffix (``VFV.TO``)."""
    return ticker.upper().endswith(EXCHANGE_SUFFIXES)


def yahoo_symbol(ticker: str) -> str:
    """Our ticker -> Yahoo's. Share-class dots become dashes (``BRK.B`` ->
    ``BRK-B``), but an exchange suffix keeps its dot (``BBD.B.TO`` -> ``BBD-B.TO``)."""
    if is_foreign(ticker):
        base, suffix = ticker.rsplit(".", 1)
        return f"{base.replace('.', '-')}.{suffix}"
    return ticker.replace(".", "-")


def from_yahoo_symbol(symbol: str) -> str:
    """Yahoo's symbol -> ours; the inverse of :func:`yahoo_symbol`."""
    if is_foreign(symbol):
        base, suffix = symbol.rsplit(".", 1)
        return f"{base.replace('-', '.')}.{suffix}"
    return symbol.replace("-", ".")


_YAHOO_TYPE = {"ETF": "ETP", "EQUITY": "Common Stock", "MUTUALFUND": "Mutual Fund"}


def parse_chart_meta(payload: dict[str, Any]) -> dict[str, Any] | None:
    """A 1-day chart's ``meta`` -> a ``securities`` row's profile and quote fields.

    With ``range=1d`` Yahoo's ``chartPreviousClose`` is the prior session's
    close, so the change it implies is the day's change.
    """
    results = ((payload or {}).get("chart") or {}).get("result") or []
    meta = results[0].get("meta") if results and isinstance(results[0], dict) else None
    if not isinstance(meta, dict):
        return None
    price = _num(meta.get("regularMarketPrice"))
    if price is None:
        return None
    prev = _num(meta.get("chartPreviousClose")) or _num(meta.get("previousClose"))
    at = _num(meta.get("regularMarketTime"))
    kind = meta.get("instrumentType")
    return {
        "name": meta.get("longName") or meta.get("shortName"),
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
        "currency": meta.get("currency"),
        "security_type": _YAHOO_TYPE.get(str(kind), kind),
        "price": price,
        "prev_close": prev,
        "change": price - prev if prev else None,
        "pct_change": (price / prev - 1) * 100 if prev else None,
        "day_high": _num(meta.get("regularMarketDayHigh")),
        "day_low": _num(meta.get("regularMarketDayLow")),
        "quote_at": datetime.fromtimestamp(at, UTC) if at else None,
    }


def parse_spark(payload: dict[str, Any]) -> dict[str, Quote]:
    """Spark response -> {ticker: Quote} with price, change and previous close
    (no open/high/low). Yahoo share-class dashes are mapped back: BRK-B -> BRK.B."""
    out: dict[str, Quote] = {}
    for symbol, row in (payload or {}).items():
        if not isinstance(row, dict):
            continue
        closes = [c for c in row.get("close") or [] if c is not None]
        price = _num(row.get("fulldayPrice")) or (_num(closes[-1]) if closes else None)
        prev = _num(row.get("chartPreviousClose")) or _num(row.get("previousClose"))
        if price is None:
            continue
        stamps = row.get("timestamp") or []
        change = _num(row.get("fulldayChange"))
        pct_change = _num(row.get("fulldayChangePercent"))
        if change is None and prev:
            change = price - prev
        if pct_change is None and prev:
            pct_change = (price / prev - 1) * 100
        out[from_yahoo_symbol(symbol)] = Quote(
            price=price,
            change=change,
            pct_change=pct_change,
            day_open=None,
            day_high=None,
            day_low=None,
            prev_close=prev,
            at=datetime.fromtimestamp(stamps[-1], UTC) if stamps else None,
        )
    return out


class YahooChartClient(BaseHttpClient):
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None, **kwargs: Any):
        kwargs.setdefault("user_agent", "Mozilla/5.0")  # Yahoo rejects bare script UAs
        super().__init__(YAHOO_BASE, **kwargs)
        _with_transport(self, transport, {})

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> YahooChartClient:
        return cls(
            transport=transport,
            timeout_s=min(settings.http_timeout_s, 15.0),
            # Fail fast: a blocked or down provider should cost seconds, not
            # minutes. The shared defaults (5 retries, 60s cap) suit bulk archiving.
            max_retries=min(settings.http_max_retries, 2),
            backoff_base_s=settings.backoff_base_s,
            backoff_cap_s=min(settings.backoff_cap_s, 8.0),
            rate_limiter=TokenBucket(1.0),
        )

    async def daily_bars(self, ticker: str, *, range_: str = "5y") -> list[Bar]:
        if range_ not in YAHOO_RANGES:
            raise ValueError(f"range must be one of {YAHOO_RANGES}")
        resp = await self.request_json(
            "GET",
            f"/v8/finance/chart/{yahoo_symbol(ticker)}",
            params={"range": range_, "interval": "1d", "events": "split,div"},
        )
        return parse_chart(resp.data, ticker)

    async def snapshot(self, ticker: str) -> dict[str, Any] | None:
        """Name, exchange, currency, type and the latest quote for one symbol
        (any listing Yahoo carries, ``VFV.TO`` included); None if unknown."""
        resp = await self.request_json(
            "GET",
            f"/v8/finance/chart/{yahoo_symbol(ticker)}",
            params={"range": "1d", "interval": "1d"},
        )
        return parse_chart_meta(resp.data)

    async def fx_rate(self, from_ccy: str, to_ccy: str) -> float | None:
        """Units of ``to_ccy`` per one ``from_ccy`` (USD->CAD reads ``USDCAD=X``)."""
        if from_ccy == to_ccy:
            return 1.0
        snap = await self.snapshot(f"{from_ccy}{to_ccy}=X")
        return snap["price"] if snap else None

    async def spark(self, tickers: list[str]) -> dict[str, Quote]:
        """Latest price for up to :data:`SPARK_BATCH` symbols in one call."""
        if not tickers:
            return {}
        resp = await self.request_json(
            "GET",
            "/v8/finance/spark",
            params={
                "symbols": ",".join(yahoo_symbol(t) for t in tickers[:SPARK_BATCH]),
                "range": "1d",
                "interval": "1d",
            },
        )
        return parse_spark(resp.data)


# ── Polygon / Massive (whole-market end-of-day bars) ─────────────────────────
def parse_grouped(payload: dict[str, Any], day: date) -> dict[str, Bar]:
    """Grouped-daily response -> {ticker: Bar}. Empty on weekends and holidays."""
    out: dict[str, Bar] = {}
    for row in (payload or {}).get("results") or []:
        ticker = row.get("T")
        close = _num(row.get("c"))
        if not ticker or close is None:
            continue
        volume = _num(row.get("v"))
        out[ticker] = Bar(
            date=day,
            open=_num(row.get("o")),
            high=_num(row.get("h")),
            low=_num(row.get("l")),
            close=close,
            adj_close=close,  # split-adjusted; dividends not applied
            volume=int(volume) if volume is not None else None,
        )
    return out


class PolygonClient(BaseHttpClient):
    """Free Basic plan: end-of-day data, 2 years of history, 5 calls a minute."""

    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        **kwargs: Any,
    ) -> None:
        if not api_key:
            raise ClientError("POLYGON_API_KEY is not set")
        super().__init__(POLYGON_BASE, **kwargs)
        _with_transport(self, transport, {"Authorization": f"Bearer {api_key}"})

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> PolygonClient:
        return cls(
            settings.polygon_api_key,
            transport=transport,
            user_agent=settings.user_agent,
            timeout_s=min(settings.http_timeout_s, 30.0),
            max_retries=min(settings.http_max_retries, 2),
            backoff_base_s=settings.backoff_base_s,
            backoff_cap_s=min(settings.backoff_cap_s, 15.0),
            rate_limiter=TokenBucket(5 / 60),
        )

    async def grouped_daily(self, day: date) -> dict[str, Bar]:
        resp = await self.request_json(
            "GET",
            f"/v2/aggs/grouped/locale/us/market/stocks/{day.isoformat()}",
            params={"adjusted": "true"},
        )
        return parse_grouped(resp.data, day)


# ── Polymarket (prediction-market odds) ──────────────────────────────────────
class PolymarketClient(BaseHttpClient):
    """Polymarket's public Gamma API: open events by tag, busiest first. No key."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None, **kwargs: Any) -> None:
        super().__init__(POLYMARKET_BASE, **kwargs)
        _with_transport(self, transport, {})

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> PolymarketClient:
        return cls(
            transport=transport,
            user_agent=settings.user_agent,
            timeout_s=min(settings.http_timeout_s, 10.0),
            max_retries=min(settings.http_max_retries, 1),
            backoff_base_s=settings.backoff_base_s,
            backoff_cap_s=min(settings.backoff_cap_s, 4.0),
        )

    async def event(self, event_id: str) -> dict[str, Any] | None:
        """One event, with all of its markets, by Gamma id."""
        resp = await self.request_json("GET", f"/events/{event_id}")
        return resp.data if isinstance(resp.data, dict) else None

    async def events(self, tag: str, *, limit: int = 12) -> list[dict[str, Any]]:
        resp = await self.request_json(
            "GET",
            "/events",
            params={
                "tag_slug": tag,
                "active": "true",
                "closed": "false",
                "order": "volume24hr",
                "ascending": "false",
                "limit": limit,
            },
        )
        return [e for e in resp.data or [] if isinstance(e, dict)]


class PolymarketHistoryClient(BaseHttpClient):
    """Polymarket's public CLOB price history for one outcome token. No key."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None, **kwargs: Any) -> None:
        super().__init__(POLYMARKET_CLOB_BASE, **kwargs)
        _with_transport(self, transport, {})

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> PolymarketHistoryClient:
        return cls(
            transport=transport,
            user_agent=settings.user_agent,
            timeout_s=min(settings.http_timeout_s, 10.0),
            max_retries=min(settings.http_max_retries, 1),
            backoff_base_s=settings.backoff_base_s,
            backoff_cap_s=min(settings.backoff_cap_s, 4.0),
        )

    async def history(
        self, token_id: str, *, interval: str = "1m", fidelity_min: int = 60
    ) -> list[tuple[datetime, float]]:
        """``[(at, price 0–1)]`` oldest first: the last month at hourly resolution."""
        resp = await self.request_json(
            "GET",
            "/prices-history",
            params={"market": token_id, "interval": interval, "fidelity": fidelity_min},
        )
        rows = resp.data.get("history") if isinstance(resp.data, dict) else None
        out: list[tuple[datetime, float]] = []
        for row in rows or []:
            t, p = _num(row.get("t")), _num(row.get("p"))
            if t is not None and p is not None and 0.0 <= p <= 1.0:
                out.append((datetime.fromtimestamp(t, UTC), p))
        out.sort(key=lambda r: r[0])
        return out
