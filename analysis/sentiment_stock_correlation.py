"""
analysis/sentiment_stock_correlation.py

Combine daily news-sentiment scores (produced by the NLP pipeline, Layer 2) with
historical stock-price data (pulled live from Yahoo Finance via yfinance) and
measure whether sentiment is correlated with — and ideally *precedes* — price
movements.

The flow is split into six clearly-documented steps:

    STEP 1  Build a daily sentiment series per ticker from data/nlp_processed/*.json
    STEP 2  Pull historical OHLCV (+ best-effort EPS) per ticker from yfinance
    STEP 3  Merge sentiment with price on a *trading-day* calendar (date alignment)
    STEP 4  Measure Pearson correlation at several lags (lag>0 ⇒ sentiment leads)
    STEP 5  Visualise (time series, scatter, lag heatmap) with matplotlib/seaborn
    STEP 6  Write a markdown report + the merged panel CSV to data/analysis/

Run standalone:
    python -m analysis.sentiment_stock_correlation --tickers AAPL MSFT TSLA NVDA

Design notes
------------
* Each processed article carries a *query* `ticker` field that may list several
  symbols ("AAPL,MSFT,TSLA,NVDA"). We attribute the article's sentiment to every
  symbol in that list (an explode), since the article was surfaced for all of them.
* "Sentiment" here is a signed polarity in roughly [-1, +1] computed per article as
  mean(positive_score - negative_score) over its ORG entities, falling back to the
  article-level label when no entities exist. A daily score is the mean over that
  day's articles for the ticker.
* yfinance daily history has no EPS column. EPS is therefore *best effort*: we pull
  quarterly basic/diluted EPS (or trailing EPS from .info) and forward-fill it onto
  the daily index. It is informational only and not used in the core correlation.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence

import pandas as pd
from scipy import stats

# matplotlib + seaborn are imported lazily inside _plotting() so the JSON path
# (build_payload → web API) carries no plotting dependency and stays fast.

# ─────────────────────────────────────────────────────────────────────────────
# Paths / config
# ─────────────────────────────────────────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_THIS_DIR)
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "nlp_processed")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "analysis")

DEFAULT_TICKERS = ["AAPL", "MSFT", "TSLA", "NVDA"]
DEFAULT_MAX_LAG = 3  # test sentiment[t] vs return[t], t+1, t+2, t+3


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Daily sentiment series from the NLP-processed layer
# ─────────────────────────────────────────────────────────────────────────────
def _article_polarity(article: dict) -> Optional[float]:
    """Collapse one processed article into a single signed polarity in [-1, 1].

    Preference order:
      1. mean over ORG entities of (positive_score - negative_score)
      2. article-level label → sign, scaled by article_sentiment_score
    Returns None if neither signal is available.
    """
    entities = article.get("entities") or []
    polarities = [
        e.get("positive_score", 0.0) - e.get("negative_score", 0.0)
        for e in entities
        if ("positive_score" in e or "negative_score" in e)
    ]
    if polarities:
        return sum(polarities) / len(polarities)

    label = (article.get("article_sentiment_label") or "neutral").lower()
    score = float(article.get("article_sentiment_score", 0.0) or 0.0)
    sign = {"positive": 1.0, "negative": -1.0}.get(label, 0.0)
    return sign * score


def _parse_published(article: dict) -> Optional[date]:
    """Extract the article's publication calendar date (UTC), or None."""
    raw = article.get("published_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def load_daily_sentiment(
    processed_dir: str = PROCESSED_DIR,
    tickers: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """STEP 1: build a tidy daily sentiment table from data/nlp_processed/*.json.

    Returns a DataFrame with columns:
        date (datetime64), ticker, sentiment (mean signed polarity), article_count

    One row per (ticker, calendar-date). Articles tagged with multiple tickers are
    counted once for each ticker they reference.
    """
    wanted = {t.upper() for t in tickers} if tickers else None
    rows: List[dict] = []

    for path in glob.glob(os.path.join(processed_dir, "*.json")):
        try:
            with open(path, "r") as fh:
                art = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue

        day = _parse_published(art)
        polarity = _article_polarity(art)
        if day is None or polarity is None:
            continue

        # Explode the comma-joined query ticker list into individual symbols.
        symbols = {
            s.strip().upper()
            for s in str(art.get("ticker") or "").split(",")
            if s.strip()
        }
        for sym in symbols:
            if wanted is not None and sym not in wanted:
                continue
            rows.append({"date": day, "ticker": sym, "polarity": polarity})

    if not rows:
        return pd.DataFrame(columns=["date", "ticker", "sentiment", "article_count"])

    df = pd.DataFrame(rows)
    daily = (
        df.groupby(["ticker", "date"])
        .agg(sentiment=("polarity", "mean"), article_count=("polarity", "size"))
        .reset_index()
    )
    daily["date"] = pd.to_datetime(daily["date"])
    return daily.sort_values(["ticker", "date"]).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Historical stock data from yfinance
# ─────────────────────────────────────────────────────────────────────────────
def _fetch_eps(tk, index: pd.DatetimeIndex) -> pd.Series:
    """Best-effort EPS series aligned to `index` (forward-filled).

    yfinance daily history has no EPS, so we approximate: pull quarterly Basic/
    Diluted EPS from the income statement and forward-fill across trading days; if
    that is unavailable fall back to a flat trailing EPS from .info. Returns NaNs on
    total failure rather than raising — EPS is informational only.
    """
    eps = pd.Series(index=index, dtype="float64", name="eps")

    # (a) quarterly EPS from the income statement, if exposed by this yfinance build
    for attr in ("quarterly_income_stmt", "quarterly_financials"):
        try:
            stmt = getattr(tk, attr)
        except Exception:
            stmt = None
        if stmt is None or getattr(stmt, "empty", True):
            continue
        for row_name in ("Basic EPS", "Diluted EPS"):
            if row_name in stmt.index:
                q = stmt.loc[row_name].dropna()
                q.index = pd.to_datetime(q.index)
                q = q.sort_index()
                if not q.empty:
                    eps = q.reindex(index.union(q.index)).sort_index().ffill().reindex(index)
                    return eps.astype("float64")

    # (b) flat trailing EPS from .info as a last resort
    try:
        trailing = tk.info.get("trailingEps")
        if trailing is not None:
            eps[:] = float(trailing)
    except Exception:
        pass
    return eps


def fetch_stock_data(
    ticker: str,
    start: date,
    end: date,
    with_eps: bool = True,
) -> pd.DataFrame:
    """STEP 2: pull daily OHLCV for `ticker` over [start, end] from Yahoo Finance.

    Returns a DataFrame indexed by trading date with columns:
        open, close, volume, daily_return, intraday_return, [eps]

    * daily_return    = close-to-close pct change (the primary "price movement")
    * intraday_return = (close - open) / open
    Trading days only — weekends/holidays are simply absent (handled in STEP 3).
    """
    import yfinance as yf

    tk = yf.Ticker(ticker)
    # pad `end` by one day because yfinance's end is exclusive
    hist = tk.history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=True,
    )
    if hist.empty:
        return pd.DataFrame()

    hist.index = pd.to_datetime(hist.index).tz_localize(None).normalize()
    out = pd.DataFrame(index=hist.index)
    out["open"] = hist["Open"]
    out["close"] = hist["Close"]
    out["volume"] = hist["Volume"]
    out["daily_return"] = out["close"].pct_change()
    out["intraday_return"] = (out["close"] - out["open"]) / out["open"]

    if with_eps:
        out["eps"] = _fetch_eps(tk, out.index)

    out.index.name = "date"
    return out


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Merge on a trading-day calendar (proper date alignment)
# ─────────────────────────────────────────────────────────────────────────────
def merge_sentiment_price(
    sentiment: pd.DataFrame,
    price: pd.DataFrame,
) -> pd.DataFrame:
    """STEP 3: align a single ticker's daily sentiment to trading days and join.

    News published on a non-trading day (weekend/holiday) cannot move that day's
    price because the market is closed — so each sentiment date is rolled *forward*
    to the next available trading day before joining. When several calendar dates
    collapse onto the same trading day their sentiment is averaged (article counts
    summed).

    `sentiment` : columns [date, sentiment, article_count] for ONE ticker
    `price`     : indexed by trading date (output of fetch_stock_data)
    Returns the price frame left-joined with aligned sentiment + article_count.
    """
    if price.empty:
        return pd.DataFrame()

    merged = price.copy()
    merged["sentiment"] = pd.NA
    merged["article_count"] = 0

    if sentiment.empty:
        merged["article_count"] = merged["article_count"].astype(int)
        return merged

    trading_days = price.index  # sorted DatetimeIndex of trading days
    aligned: Dict[pd.Timestamp, List[float]] = {}
    counts: Dict[pd.Timestamp, int] = {}

    for _, r in sentiment.iterrows():
        d = pd.Timestamp(r["date"]).normalize()
        # first trading day on/after the publication date
        pos = trading_days.searchsorted(d, side="left")
        if pos >= len(trading_days):
            continue  # news after the last available trading day — drop it
        tday = trading_days[pos]
        aligned.setdefault(tday, []).append(float(r["sentiment"]))
        counts[tday] = counts.get(tday, 0) + int(r["article_count"])

    for tday, vals in aligned.items():
        merged.at[tday, "sentiment"] = sum(vals) / len(vals)
        merged.at[tday, "article_count"] = counts[tday]

    merged["sentiment"] = pd.to_numeric(merged["sentiment"], errors="coerce")
    merged["article_count"] = merged["article_count"].astype(int)
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Lagged Pearson correlation
# ─────────────────────────────────────────────────────────────────────────────
def compute_lagged_correlations(
    merged: pd.DataFrame,
    price_col: str = "daily_return",
    max_lag: int = DEFAULT_MAX_LAG,
) -> pd.DataFrame:
    """STEP 4: Pearson correlation of sentiment[t] vs price_col[t + lag].

    lag = 0  → same-day relationship
    lag > 0  → does sentiment *precede* the move? (the question we actually care about)

    Only rows where a sentiment score exists are used. Returns a DataFrame with
    columns [lag, n, pearson_r, p_value]; rows with too few paired points (<3) are
    reported with NaN r/p so the sparsity is visible rather than hidden.
    """
    records = []
    s = merged["sentiment"]
    for lag in range(0, max_lag + 1):
        shifted = merged[price_col].shift(-lag)  # bring future return back to date t
        pair = pd.concat([s, shifted], axis=1).dropna()
        n = len(pair)
        if n >= 3 and pair.iloc[:, 0].std() > 0 and pair.iloc[:, 1].std() > 0:
            r, p = stats.pearsonr(pair.iloc[:, 0], pair.iloc[:, 1])
        else:
            r, p = float("nan"), float("nan")
        records.append({"lag": lag, "n": n, "pearson_r": r, "p_value": p})
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Visualisation
# ─────────────────────────────────────────────────────────────────────────────
def _plotting():
    """Lazy-import matplotlib (Agg backend) + seaborn. Keeps the JSON/API path light."""
    import matplotlib

    matplotlib.use("Agg")  # headless: write PNGs, never open a window
    import matplotlib.pyplot as plt
    import seaborn as sns

    return plt, sns


def _plot_timeseries(merged: pd.DataFrame, ticker: str, path: str) -> None:
    """Dual-axis: closing price (line) vs daily sentiment (stems) over time."""
    plt, sns = _plotting()
    fig, ax1 = plt.subplots(figsize=(12, 5))
    # older matplotlib can't index a pandas DatetimeIndex directly → use numpy
    ax1.plot(merged.index.to_numpy(), merged["close"].to_numpy(),
             color="#1f77b4", lw=1.5, label="Close")
    ax1.set_ylabel("Close price ($)", color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")

    ax2 = ax1.twinx()
    pts = merged.dropna(subset=["sentiment"])
    colors = ["#2ca02c" if v >= 0 else "#d62728" for v in pts["sentiment"]]
    ax2.bar(pts.index.to_numpy(), pts["sentiment"].to_numpy(),
            width=2.0, color=colors, alpha=0.6)
    ax2.axhline(0, color="grey", lw=0.6, ls="--")
    ax2.set_ylabel("Daily news sentiment (signed)", color="grey")
    ax2.set_ylim(-1, 1)

    ax1.set_title(f"{ticker}: closing price vs news sentiment")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _plot_scatter(merged: pd.DataFrame, ticker: str, lag: int, path: str) -> None:
    """Scatter sentiment[t] vs next-`lag`-day return, with regression line."""
    pair = pd.concat(
        [merged["sentiment"], merged["daily_return"].shift(-lag)], axis=1
    ).dropna()
    pair.columns = ["sentiment", "future_return"]
    if len(pair) < 3:
        return
    plt, sns = _plotting()
    fig, ax = plt.subplots(figsize=(7, 6))
    sns.regplot(
        data=pair, x="sentiment", y="future_return", ax=ax,
        scatter_kws={"alpha": 0.7, "s": 45}, line_kws={"color": "#d62728"},
    )
    ax.axhline(0, color="grey", lw=0.6, ls="--")
    ax.axvline(0, color="grey", lw=0.6, ls="--")
    ax.set_xlabel("News sentiment (signed)")
    ax.set_ylabel(f"Return {lag} trading day(s) later")
    ax.set_title(f"{ticker}: sentiment vs +{lag}d return  (n={len(pair)})")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _plot_lag_heatmap(corr_by_ticker: Dict[str, pd.DataFrame], path: str) -> None:
    """Heatmap of Pearson r across tickers (rows) × lag (cols)."""
    if not corr_by_ticker:
        return
    plt, sns = _plotting()
    matrix = pd.DataFrame(
        {t: c.set_index("lag")["pearson_r"] for t, c in corr_by_ticker.items()}
    ).T
    matrix.columns = [f"+{c}d" for c in matrix.columns]
    fig, ax = plt.subplots(figsize=(1.6 * len(matrix.columns) + 2, 0.7 * len(matrix) + 2))
    sns.heatmap(
        matrix, annot=True, fmt=".2f", cmap="RdBu_r", center=0, vmin=-1, vmax=1,
        linewidths=0.5, cbar_kws={"label": "Pearson r"}, ax=ax,
    )
    ax.set_xlabel("Sentiment lead (trading days ahead of return)")
    ax.set_ylabel("Ticker")
    ax.set_title("Sentiment → return correlation by lag")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# JSON payload (for the web API / Market-Correlation dashboard tab)
# ─────────────────────────────────────────────────────────────────────────────
def _clean(seq) -> List[Optional[float]]:
    """JSON-safe list: NaN/inf → None, numpy scalars → python float."""
    out: List[Optional[float]] = []
    for v in seq:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            out.append(None)
        else:
            out.append(float(v))
    return out


def build_payload(
    tickers: Optional[Sequence[str]] = None,
    max_lag: int = DEFAULT_MAX_LAG,
    processed_dir: str = PROCESSED_DIR,
) -> dict:
    """Compute the sentiment↔price panel as a JSON-serialisable dict (no file I/O).

    Drives the dashboard's Market-Correlation tab. Reads the *current*
    nlp_processed store and pulls live prices on every call, so freshly-ingested
    news is reflected as soon as the cache expires.
    """
    tickers = list(tickers) if tickers else DEFAULT_TICKERS
    sentiment_all = load_daily_sentiment(processed_dir, tickers)
    payload: dict = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "max_lag": max_lag,
        "span": None,
        "tickers": {},
    }
    if sentiment_all.empty:
        return payload

    span_start = sentiment_all["date"].min().date()
    span_end = sentiment_all["date"].max().date()
    payload["span"] = {"start": span_start.isoformat(), "end": span_end.isoformat()}

    for ticker in tickers:
        s = sentiment_all[sentiment_all["ticker"] == ticker].drop(columns="ticker")
        if s.empty:
            continue
        try:
            price = fetch_stock_data(
                ticker, span_start, span_end + timedelta(days=10), with_eps=False
            )
        except Exception:
            continue
        if price.empty:
            continue

        merged = merge_sentiment_price(s, price)
        corr = compute_lagged_correlations(merged, "daily_return", max_lag)

        correlations = [
            {
                "lag": int(r["lag"]),
                "n": int(r["n"]),
                "r": None if pd.isna(r["pearson_r"]) else round(float(r["pearson_r"]), 4),
                "p": None if pd.isna(r["p_value"]) else round(float(r["p_value"]), 4),
            }
            for _, r in corr.iterrows()
        ]
        best = corr.dropna(subset=["pearson_r"])
        best_rec = None
        if not best.empty:
            b = best.loc[best["pearson_r"].abs().idxmax()]
            best_rec = {
                "lag": int(b["lag"]),
                "r": round(float(b["pearson_r"]), 4),
                "p": round(float(b["p_value"]), 4),
            }

        payload["tickers"][ticker] = {
            "dates": [d.strftime("%Y-%m-%d") for d in merged.index],
            "close": _clean(merged["close"].tolist()),
            "sentiment": _clean(merged["sentiment"].tolist()),
            "daily_return": _clean(merged["daily_return"].tolist()),
            "article_count": [int(x) for x in merged["article_count"].tolist()],
            "correlations": correlations,
            "best": best_rec,
            "n_sentiment_days": int(merged["sentiment"].notna().sum()),
        }
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Orchestration + report
# ─────────────────────────────────────────────────────────────────────────────
def run(
    tickers: Optional[Sequence[str]] = None,
    max_lag: int = DEFAULT_MAX_LAG,
    processed_dir: str = PROCESSED_DIR,
    output_dir: str = OUTPUT_DIR,
) -> Dict[str, pd.DataFrame]:
    """End-to-end driver: STEP 1 → STEP 6. Returns {ticker: merged panel}.

    Side effects: writes per-ticker plots, a lag heatmap, a combined panel CSV,
    and a markdown summary report into `output_dir`.
    """
    tickers = list(tickers) if tickers else DEFAULT_TICKERS
    os.makedirs(output_dir, exist_ok=True)
    _, sns = _plotting()
    sns.set_theme(style="whitegrid")

    print(f"\n{'='*70}\nSentiment ↔ Stock-price correlation\n{'='*70}")

    # STEP 1 — daily sentiment for all requested tickers at once
    sentiment_all = load_daily_sentiment(processed_dir, tickers)
    if sentiment_all.empty:
        print("No sentiment rows found — is data/nlp_processed/ populated?")
        return {}
    span_start = sentiment_all["date"].min().date()
    span_end = sentiment_all["date"].max().date()
    print(
        f"STEP 1  loaded sentiment: {len(sentiment_all)} ticker-days, "
        f"{span_start} → {span_end}"
    )

    merged_by_ticker: Dict[str, pd.DataFrame] = {}
    corr_by_ticker: Dict[str, pd.DataFrame] = {}

    for ticker in tickers:
        s = sentiment_all[sentiment_all["ticker"] == ticker].drop(columns="ticker")
        if s.empty:
            print(f"  · {ticker}: no sentiment, skipping")
            continue

        # STEP 2 — market data over the sentiment span (+5d tail for forward lags)
        try:
            price = fetch_stock_data(ticker, span_start, span_end + timedelta(days=10))
        except Exception as exc:  # network / yfinance hiccup
            print(f"  · {ticker}: yfinance error ({exc}); skipping")
            continue
        if price.empty:
            print(f"  · {ticker}: no price data returned; skipping")
            continue

        # STEP 3 — align + merge
        merged = merge_sentiment_price(s, price)

        # STEP 4 — lagged correlations
        corr = compute_lagged_correlations(merged, "daily_return", max_lag)

        merged_by_ticker[ticker] = merged
        corr_by_ticker[ticker] = corr

        n_days = int(merged["sentiment"].notna().sum())
        best = corr.dropna(subset=["pearson_r"])
        headline = ""
        if not best.empty:
            row = best.loc[best["pearson_r"].abs().idxmax()]
            headline = (
                f"  strongest |r|={row['pearson_r']:.2f} at lag +{int(row['lag'])}d "
                f"(p={row['p_value']:.2f}, n={int(row['n'])})"
            )
        print(f"  · {ticker}: {n_days} sentiment-days merged.{headline}")

        # STEP 5 — per-ticker plots
        _plot_timeseries(merged, ticker, os.path.join(output_dir, f"{ticker}_timeseries.png"))
        _plot_scatter(merged, ticker, 1, os.path.join(output_dir, f"{ticker}_scatter_lag1.png"))

    if not merged_by_ticker:
        print("No ticker produced a merged panel.")
        return {}

    # STEP 5 — cross-ticker lag heatmap
    _plot_lag_heatmap(corr_by_ticker, os.path.join(output_dir, "lag_correlation_heatmap.png"))

    # STEP 6 — persist combined panel + markdown report
    combined = pd.concat(
        [m.assign(ticker=t) for t, m in merged_by_ticker.items()]
    ).reset_index()
    combined.to_csv(os.path.join(output_dir, "merged_panel.csv"), index=False)
    _write_report(corr_by_ticker, merged_by_ticker, output_dir, span_start, span_end)

    print(f"\nDone. Outputs in {output_dir}\n{'='*70}")
    return merged_by_ticker


def _write_report(
    corr_by_ticker: Dict[str, pd.DataFrame],
    merged_by_ticker: Dict[str, pd.DataFrame],
    output_dir: str,
    span_start: date,
    span_end: date,
) -> None:
    """STEP 6: human-readable markdown summary of the correlation findings."""
    lines = [
        "# Sentiment ↔ Stock-price correlation report",
        "",
        f"_Generated {datetime.now():%Y-%m-%d %H:%M}_  ",
        f"Sentiment span: **{span_start} → {span_end}**",
        "",
        "Signed daily news sentiment vs close-to-close return, Pearson r at lags 0–"
        f"{max(len(c) - 1 for c in corr_by_ticker.values())} trading days "
        "(lag > 0 means sentiment *leads* the price move).",
        "",
        "| Ticker | Sentiment days | lag 0 r (p) | lag +1 r (p) | strongest |r| |",
        "|---|---|---|---|---|",
    ]
    for ticker, corr in corr_by_ticker.items():
        n_days = int(merged_by_ticker[ticker]["sentiment"].notna().sum())

        def cell(lag: int) -> str:
            row = corr[corr["lag"] == lag]
            if row.empty or pd.isna(row.iloc[0]["pearson_r"]):
                return "n/a"
            return f"{row.iloc[0]['pearson_r']:.2f} ({row.iloc[0]['p_value']:.2f})"

        best = corr.dropna(subset=["pearson_r"])
        if best.empty:
            strongest = "n/a"
        else:
            b = best.loc[best["pearson_r"].abs().idxmax()]
            strongest = f"{b['pearson_r']:.2f} @ +{int(b['lag'])}d"
        lines.append(
            f"| {ticker} | {n_days} | {cell(0)} | {cell(1)} | {strongest} |"
        )

    lines += [
        "",
        "## How to read this",
        "- **r > 0**: positive news sentiment tends to coincide with / precede price *gains*.",
        "- **r < 0**: positive sentiment precedes price *drops* (or the news lags the move).",
        "- **p-value**: probability of seeing this |r| by chance. With the current sparse",
        "  sample most p-values will be > 0.05, i.e. *not statistically significant yet* —",
        "  treat the numbers as directional until the processed-article corpus grows.",
        "",
        "## Caveats",
        "- Sentiment is attributed to every ticker an article's query referenced, so",
        "  multi-ticker articles add correlated noise across symbols.",
        "- EPS is best-effort (quarterly, forward-filled) and is not used in the correlation.",
        "- Non-trading-day news is rolled forward to the next trading day.",
        "",
        "Artifacts: `merged_panel.csv`, `*_timeseries.png`, `*_scatter_lag1.png`, "
        "`lag_correlation_heatmap.png`.",
    ]
    with open(os.path.join(output_dir, "report.md"), "w") as fh:
        fh.write("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Correlate daily news sentiment with historical stock prices."
    )
    parser.add_argument(
        "--tickers", nargs="+", default=DEFAULT_TICKERS,
        help="Ticker symbols to analyse (default: AAPL MSFT TSLA NVDA)",
    )
    parser.add_argument(
        "--max-lag", type=int, default=DEFAULT_MAX_LAG,
        help="Maximum sentiment→return lead in trading days (default: 3)",
    )
    parser.add_argument(
        "--processed-dir", default=PROCESSED_DIR,
        help="Directory of NLP-processed article JSON files",
    )
    parser.add_argument(
        "--output-dir", default=OUTPUT_DIR,
        help="Where to write plots, CSV, and report",
    )
    args = parser.parse_args(argv)
    run(
        tickers=args.tickers,
        max_lag=args.max_lag,
        processed_dir=args.processed_dir,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
