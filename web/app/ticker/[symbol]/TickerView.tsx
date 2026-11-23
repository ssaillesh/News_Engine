"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetcher, qs, send, useApi, writeErrorMessage, type PricesResponse, type Recommendation, type SecurityDetail } from "@/lib/api";
import { compact, dateTime, money, num, pct, shortDate, signedMoney, timeAgo, tone, toneText } from "@/lib/format";
import { PriceChart, type ChartMode, type NewsDay } from "@/components/PriceChart";
import { InfiniteNews } from "@/components/News";
import { buttonCls, Card, CardHeader, Change, ErrorBox, Logo, Segmented, Skeleton } from "@/components/ui";

const RANGES = ["1m", "3m", "6m", "ytd", "1y", "5y", "max"] as const;
type Range = (typeof RANGES)[number];

export function TickerSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Skeleton className="h-12 w-12" />
        <div className="space-y-2">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-3 w-64" />
        </div>
      </div>
      <Skeleton className="h-[460px] w-full rounded-xl" />
    </div>
  );
}

export function TickerView({ symbol }: { symbol: string }) {
  const [range, setRange] = useState<Range>("1y");
  const [mode, setMode] = useState<ChartMode>("candle");
  const [sort, setSort] = useState<"recent" | "impact">("recent");
  // A selected news day belongs to the range it was picked in.
  const [picked, setPicked] = useState<{ range: Range; day: NewsDay } | null>(null);
  const day = picked?.range === range ? picked.day : null;
  const setDay = (d: NewsDay | null) => setPicked(d ? { range, day: d } : null);
  const [busy, setBusy] = useState<"watch" | "refresh" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const secKey = `/api/hub/securities/${encodeURIComponent(symbol)}`;
  const sec = useApi<SecurityDetail>(secKey);
  const prices = useApi<PricesResponse>(`${secKey}/prices${qs({ range })}`);

  useEffect(() => {
    document.title = `${symbol} · Investment Hub`;
  }, [symbol]);

  if (sec.error && !sec.data) return <ErrorBox error={sec.error} onRetry={() => sec.mutate()} />;
  if (!sec.data) return <TickerSkeleton />;

  const s = sec.data;
  const q = s.quote;
  const currency = s.currency || "USD";

  const toggleWatch = async () => {
    setBusy("watch");
    setActionError(null);
    try {
      if (s.watched) await send("DELETE", `/api/hub/watchlist/${encodeURIComponent(symbol)}`);
      else await send("POST", "/api/hub/watchlist", { ticker: symbol });
    } catch (e) {
      setActionError(writeErrorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const refresh = async () => {
    setBusy("refresh");
    setActionError(null);
    try {
      const fresh = await fetcher<SecurityDetail>(`${secKey}?refresh=true`);
      await Promise.all([sec.mutate(fresh, { revalidate: false }), prices.mutate()]);
    } catch (e) {
      setActionError(writeErrorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const newsBase = day
    ? `/api/statuses${qs({ ticker: symbol, since: day.dates[0], until: day.dates[day.dates.length - 1], sort })}`
    : `${secKey}/news${qs({ sort })}`;

  const stats = prices.data?.stats;

  return (
    <div className="space-y-5">
      {/* ── header ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <Logo ticker={symbol} url={s.logo_url} size={48} />
          <div className="min-w-0">
            <div className="flex items-baseline gap-2">
              <h1 className="num text-2xl font-semibold tracking-tight">{symbol}</h1>
              {s.name ? <span className="truncate text-base text-muted">{s.name}</span> : null}
            </div>
            <p className="mt-0.5 truncate text-xs text-muted">
              {[s.exchange, s.industry, s.country].filter(Boolean).join(" · ") || "No profile stored yet"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-4">
          {q?.price != null ? (
            <div className="text-right">
              <div className="num text-3xl font-semibold tracking-tight">{money(q.price, currency)}</div>
              <div className={`num text-sm ${toneText[tone(q.change)]}`}>
                {signedMoney(q.change, currency)} ({pct(q.pct_change)})
                <span className="ml-2 text-xs text-faint" title={dateTime(q.at)}>
                  {q.at ? `as of ${dateTime(q.at)}` : ""}
                </span>
              </div>
            </div>
          ) : null}
          <div className="flex gap-2">
            <button onClick={toggleWatch} disabled={busy !== null} className={s.watched ? buttonCls.secondary : buttonCls.primary}>
              {busy === "watch" ? "Saving…" : s.watched ? "★ Watching" : "☆ Watch"}
            </button>
            <button onClick={refresh} disabled={busy !== null} className={buttonCls.secondary} title="Fetch a live quote (needs FINNHUB_API_KEY on the backend)">
              {busy === "refresh" ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </div>
      </div>

      {actionError ? (
        <p role="alert" className="rounded-lg border border-down/30 bg-down-soft px-3 py-2 text-sm text-down">
          {actionError}
        </p>
      ) : null}
      {!s.tracked_data ? (
        <p className="rounded-lg border border-warn/30 bg-warn-soft px-3 py-2 text-sm text-warn">
          No market data stored for {symbol} yet. Add it to your watchlist (or refresh) to fetch a profile, quote and price
          history — this needs a Finnhub key on the backend.
        </p>
      ) : s.last_error ? (
        <p className="rounded-lg border border-warn/30 bg-warn-soft px-3 py-2 text-sm text-warn">
          Last refresh failed: {s.last_error}
        </p>
      ) : null}

      {/* ── chart ──────────────────────────────────────────────── */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
            {stats ? (
              <>
                <span>
                  <span className="text-muted">Return </span>
                  <Change value={stats.return_pct} className="font-semibold" />
                </span>
                <span className="num text-muted">
                  H <span className="text-text">{num(stats.high)}</span>
                </span>
                <span className="num text-muted">
                  L <span className="text-text">{num(stats.low)}</span>
                </span>
              </>
            ) : (
              <span className="text-muted">Price history</span>
            )}
            {prices.data?.news_markers.length ? (
              <span className="flex items-center gap-2 text-xs text-muted">
                <span className="inline-block h-2 w-2 rounded-full bg-up" /> positive
                <span className="inline-block h-2 w-2 rounded-full bg-faint" /> neutral
                <span className="inline-block h-2 w-2 rounded-full bg-down" /> negative news
              </span>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <Segmented
              label="Chart type"
              size="xs"
              value={mode}
              onChange={setMode}
              options={[
                { value: "candle", label: "Candles" },
                { value: "area", label: "Line" },
              ]}
            />
            <Segmented label="Range" size="xs" value={range} onChange={setRange} options={RANGES.map((r) => ({ value: r, label: r.toUpperCase() }))} />
          </div>
        </div>
        {prices.error && !prices.data ? (
          <ErrorBox error={prices.error} onRetry={() => prices.mutate()} />
        ) : prices.data ? (
          <div className={`px-1 pt-2 transition-opacity ${prices.isValidating ? "opacity-60" : ""}`}>
            <PriceChart
              bars={prices.data.bars}
              markers={prices.data.news_markers}
              mode={mode}
              currency={currency}
              selected={day?.time ?? null}
              onSelectDay={setDay}
            />
          </div>
        ) : (
          <Skeleton className="m-4 h-[380px]" />
        )}
      </Card>

      {/* ── news + fundamentals ────────────────────────────────── */}
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title={`News mentioning ${symbol}`}
            sub={
              day ? (
                <span className="inline-flex items-center gap-1.5">
                  Showing {day.dates.length > 1 ? `${shortDate(day.dates[0])} – ${shortDate(day.dates[day.dates.length - 1])}` : shortDate(day.dates[0])}
                  <button onClick={() => setDay(null)} className="rounded bg-accent-soft px-1.5 text-accent hover:opacity-80">
                    Clear ✕
                  </button>
                </span>
              ) : (
                "Click a marker on the chart to see that day’s stories."
              )
            }
            right={
              <Segmented
                label="Sort news"
                size="xs"
                value={sort}
                onChange={setSort}
                options={[
                  { value: "recent", label: "Latest" },
                  { value: "impact", label: "Impact" },
                ]}
              />
            }
          />
          <InfiniteNews key={newsBase} base={newsBase} highlight={symbol} emptyTitle={`No stories mention ${symbol} yet`} />
        </Card>

        <div className="space-y-5">
          <Fundamentals s={s} currency={currency} />
          {s.recommendation ? <Analysts rec={s.recommendation} /> : null}
          <Card className="px-4 py-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted">Your position</span>
              <Link href="/portfolio" className="text-xs font-medium text-accent hover:underline">
                Manage →
              </Link>
            </div>
            <div className="num mt-1 text-lg font-semibold">
              {s.shares_held ? `${num(s.shares_held, 4)} shares` : "Not held"}
            </div>
            {s.shares_held && q?.price != null ? (
              <div className="num text-xs text-muted">{money(s.shares_held * q.price, currency)} market value</div>
            ) : null}
            {s.refreshed_at ? <p className="mt-2 text-xs text-faint">Profile refreshed {timeAgo(s.refreshed_at)}</p> : null}
          </Card>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <dt className="text-muted">{label}</dt>
      <dd className="num text-right">{value}</dd>
    </div>
  );
}

function Fundamentals({ s, currency }: { s: SecurityDetail; currency: string }) {
  const m = s.metrics ?? {};
  const q = s.quote;
  const lo = m["52WeekLow"];
  const hi = m["52WeekHigh"];
  const price = q?.price;
  const pos = lo != null && hi != null && price != null && hi > lo ? Math.min(1, Math.max(0, (price - lo) / (hi - lo))) : null;
  const pctMetric = (k: string) => (m[k] != null ? pct(m[k], 1, false) : "—");

  return (
    <Card>
      <CardHeader title="Key stats" />
      <div className="px-4 py-2 text-sm">
        {pos !== null ? (
          <div className="pb-3 pt-1">
            <div className="mb-1.5 flex justify-between text-xs text-muted">
              <span>52-week range</span>
              <span className="num">{pct(m["52WeekPriceReturnDaily"], 1)} 1y</span>
            </div>
            <div className="relative h-1.5 rounded-full bg-surface-2">
              <div className="absolute top-1/2 h-3 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent" style={{ left: `${pos * 100}%` }} />
            </div>
            <div className="num mt-1 flex justify-between text-xs text-muted">
              <span>{num(lo)}</span>
              <span>{num(hi)}</span>
            </div>
          </div>
        ) : null}
        <dl className="divide-y divide-border">
          <Row label="Open" value={money(q?.open, currency)} />
          <Row label="Day range" value={q?.low != null && q?.high != null ? `${num(q.low)} – ${num(q.high)}` : "—"} />
          <Row label="Prev close" value={money(q?.prev_close, currency)} />
          <Row label="Market cap" value={compact(s.market_cap, currency)} />
          <Row label="P/E (TTM)" value={num(m.peTTM)} />
          <Row label="EPS (TTM)" value={money(m.epsTTM, currency)} />
          <Row label="Beta" value={num(m.beta)} />
          <Row label="Dividend yield" value={pctMetric("dividendYieldIndicatedAnnual")} />
          <Row label="Net margin" value={pctMetric("netProfitMarginTTM")} />
          <Row label="Revenue growth (YoY)" value={pctMetric("revenueGrowthTTMYoy")} />
          <Row label="Avg volume (10d)" value={m["10DayAverageTradingVolume"] != null ? `${num(m["10DayAverageTradingVolume"], 1)}M` : "—"} />
        </dl>
      </div>
    </Card>
  );
}

function Analysts({ rec }: { rec: Recommendation }) {
  const parts = [
    { k: "Strong buy", v: rec.strongBuy, c: "bg-up" },
    { k: "Buy", v: rec.buy, c: "bg-up/60" },
    { k: "Hold", v: rec.hold, c: "bg-faint/60" },
    { k: "Sell", v: rec.sell, c: "bg-down/60" },
    { k: "Strong sell", v: rec.strongSell, c: "bg-down" },
  ];
  const total = parts.reduce((a, p) => a + p.v, 0);
  if (!total) return null;
  return (
    <Card>
      <CardHeader title="Analyst ratings" sub={`${total} analysts · ${shortDate(rec.period)}`} />
      <div className="px-4 py-3">
        <div className="flex h-2.5 overflow-hidden rounded-full">
          {parts.map((p) => (p.v ? <div key={p.k} className={p.c} style={{ width: `${(p.v / total) * 100}%` }} title={`${p.k}: ${p.v}`} /> : null))}
        </div>
        <ul className="mt-3 grid grid-cols-5 gap-1 text-center text-[11px] text-muted">
          {parts.map((p) => (
            <li key={p.k}>
              <div className="num text-sm font-semibold text-text">{p.v}</div>
              {p.k}
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}
