"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { fetcher, movesLookup, qs, reactionsKey, send, useApi, writeErrorMessage, type NewsPage, type PricesResponse, type ReactionsResponse, type Recommendation, type SecuritiesPage, type SecurityDetail } from "@/lib/api";
import { big, cls, fixed, num, pct, shortDate, signed } from "@/lib/format";
import { useHotkeys } from "@/lib/hotkeys";
import { impact100, srcShort } from "@/lib/news";
import { shortSector } from "@/lib/sectors";
import { dayMonth } from "@/lib/time";
import { PriceChart, snapNewsDays, type ChartMode, type NewsDay } from "@/components/PriceChart";
import { LAST_TICKER_KEY } from "@/components/Shell";
import { Empty, Pane, PaneError, SkRows, Tabs, Toolbar } from "@/components/term";

const RANGES = ["1m", "3m", "6m", "ytd", "1y", "5y", "max"] as const;
type Range = (typeof RANGES)[number];
const NEWS_PAGE = 25;

export function TickerSkeleton() {
  return (
    <>
      <div className="r" style={{ padding: "10px" }}>
        <div className="sk" style={{ height: 22, width: 360 }} />
      </div>
      <div className="grid-term g-stock">
        <Pane title="Price with news markers" style={{ gridColumn: "1 / span 2" }}>
          <SkRows rows={8} />
        </Pane>
        <Pane title="Key stats">
          <SkRows rows={8} />
        </Pane>
        <Pane title="In the news">
          <SkRows rows={5} />
        </Pane>
        <Pane title="News vs price">
          <SkRows rows={5} />
        </Pane>
        <Pane title="Peers">
          <SkRows rows={5} />
        </Pane>
      </div>
    </>
  );
}

export function TickerView({ symbol }: { symbol: string }) {
  const router = useRouter();
  const [range, setRange] = useState<Range>("1y");
  const [mode, setMode] = useState<ChartMode>("area");
  // A selected news day belongs to the range it was picked in.
  const [picked, setPicked] = useState<{ range: Range; day: NewsDay } | null>(null);
  const day = picked?.range === range ? picked.day : null;
  const setDay = (d: NewsDay | null) => setPicked(d ? { range, day: d } : null);
  const [busy, setBusy] = useState<"watch" | "refresh" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const secKey = `/api/hub/securities/${encodeURIComponent(symbol)}`;
  const sec = useApi<SecurityDetail>(secKey);
  const prices = useApi<PricesResponse>(`${secKey}/prices${qs({ range })}`);
  const year = useApi<PricesResponse>(`${secKey}/prices?range=1y`);

  useEffect(() => {
    document.title = `${symbol} · Investment Hub`;
    try {
      localStorage.setItem(LAST_TICKER_KEY, symbol);
    } catch {}
  }, [symbol]);

  const s = sec.data;
  const toggleWatch = async () => {
    if (!s || busy) return;
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
    if (busy) return;
    setBusy("refresh");
    setActionError(null);
    try {
      const fresh = await fetcher<SecurityDetail>(`${secKey}?refresh=true`);
      await Promise.all([sec.mutate(fresh, { revalidate: false }), prices.mutate(), year.mutate()]);
    } catch (e) {
      setActionError(writeErrorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  useHotkeys({
    w: () => void toggleWatch(),
    h: () => router.push(`/portfolio${qs({ add: symbol })}`),
    r: () => void refresh(),
  });

  if (sec.error && !s) {
    return (
      <div className="grid-term">
        <Pane title={symbol}>
          <PaneError error={sec.error} onRetry={() => sec.mutate()} />
        </Pane>
      </div>
    );
  }
  if (!s) return <TickerSkeleton />;

  const q = s.quote;
  const lastBar = year.data?.bars[year.data.bars.length - 1];
  const meta = [s.exchange, s.sector ? shortSector(s.sector) : s.industry, s.market_cap ? `MKT CAP ${big(s.market_cap)}` : null, lastBar?.volume ? `VOL ${big(lastBar.volume)}` : null]
    .filter(Boolean)
    .join(" · ")
    .toUpperCase();
  const stats = prices.data?.stats;

  return (
    <>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "6px 24px", padding: "8px 10px", borderBottom: "1px solid var(--rule)" }}>
        <h1 className="m amb" style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>
          {symbol}
        </h1>
        {s.name ? <span style={{ fontSize: 16, fontWeight: 600 }}>{s.name}</span> : null}
        {q?.price != null ? (
          <>
            <span className="m" style={{ fontSize: 22, fontWeight: 600 }}>
              {fixed(q.price)}
              {s.currency && s.currency !== "USD" ? (
                <span className="dim" style={{ fontSize: 13, marginLeft: 4 }}>
                  {s.currency}
                </span>
              ) : null}
            </span>
            <span className={`m ${cls(q.change)}`} style={{ fontSize: 15 }}>
              {signed(q.change)} {pct(q.pct_change)}
            </span>
          </>
        ) : null}
        <span className="m dim" style={{ fontSize: 12 }}>
          {meta || "NO PROFILE STORED YET"}
          {s.shares_held ? ` · HELD ${num(s.shares_held, 4)} SH` : ""}
        </span>
        <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          <button type="button" className={s.watched ? "btn on" : "btn"} onClick={toggleWatch} disabled={busy !== null} aria-pressed={s.watched}>
            {busy === "watch" ? "SAVING…" : s.watched ? "★ WATCHING" : "☆ WATCH"}
          </button>
          <Link className="btn" href={`/portfolio${qs({ add: symbol })}`}>
            + HOLDING
          </Link>
          <button type="button" className="btn" onClick={refresh} disabled={busy !== null} title="Fetch a live quote (needs FINNHUB_API_KEY on the backend)">
            {busy === "refresh" ? "REFRESHING…" : "REFRESH"}
          </button>
        </span>
      </div>
      {actionError || !s.tracked_data || s.last_error ? (
        <div role="alert" className="m" style={{ padding: "5px 10px", fontSize: 12, borderBottom: "1px solid var(--rule)", color: actionError ? "var(--dn)" : "var(--hot)" }}>
          {actionError
            ? actionError
            : !s.tracked_data
              ? `NO MARKET DATA STORED FOR ${symbol} YET. WATCH IT OR REFRESH TO FETCH A PROFILE, QUOTE AND HISTORY (NEEDS A FINNHUB KEY ON THE BACKEND).`
              : `LAST REFRESH FAILED: ${s.last_error}`}
        </div>
      ) : null}

      <div className="grid-term g-stock">
        <Pane
          title="Price with news markers"
          right={
            <>
              {range.toUpperCase()} · RETURN <span>{stats ? pct(stats.return_pct) : "—"}</span>
            </>
          }
          style={{ gridColumn: "1 / span 2", gridRow: 1 }}
        >
          <Toolbar>
            <Tabs label="Range" value={range} onChange={setRange} options={RANGES.map((r) => ({ value: r, label: r.toUpperCase() }))} />
            <Tabs
              label="Chart type"
              value={mode}
              onChange={setMode}
              options={[
                { value: "area", label: "LINE" },
                { value: "candle", label: "CANDLE" },
              ]}
            />
            <span className="m dim" style={{ marginLeft: "auto", fontSize: 11 }}>
              <span className="up">●</span> POSITIVE NEWS&nbsp; <span className="dn">●</span> NEGATIVE&nbsp; <span className="amb">●</span> HIGH IMPACT
            </span>
          </Toolbar>
          <div style={{ flex: 1, minHeight: 0, padding: "4px 4px 2px", display: "flex", flexDirection: "column", opacity: prices.isValidating && prices.data ? 0.6 : 1 }}>
            {prices.error && !prices.data ? (
              <PaneError error={prices.error} onRetry={() => prices.mutate()} />
            ) : prices.data ? (
              <PriceChart bars={prices.data.bars} markers={prices.data.news_markers} mode={mode} currency={s.currency || "USD"} selected={day?.time ?? null} onSelectDay={setDay} />
            ) : (
              <SkRows rows={8} />
            )}
          </div>
        </Pane>

        <KeyStats s={s} />
        <TickerNews symbol={symbol} day={day} clearDay={() => setDay(null)} />
        <NewsVsPrice year={year.data} rec={s.recommendation ?? null} />
        <Peers symbol={symbol} sector={s.sector ?? null} />
      </div>
    </>
  );
}

// ── key stats ─────────────────────────────────────────────────────────────
function KeyStats({ s }: { s: SecurityDetail }) {
  const m = s.metrics ?? {};
  const p = (k: string, d = 1) => (m[k] != null ? `${num(m[k], d)}%` : "—");
  const n = (k: string, d = 2) => (m[k] != null ? num(m[k], d) : "—");
  const q = s.quote;
  const rows: [string, string][] = [
    ["P/E", n("peTTM", 1)],
    ["EPS", n("epsTTM")],
    ["P/B", n("pbAnnual", 1)],
    ["P/S", n("psTTM", 1)],
    ["52W HIGH", n("52WeekHigh")],
    ["52W LOW", n("52WeekLow")],
    ["BETA", n("beta")],
    ["DIV YLD", p("dividendYieldIndicatedAnnual", 2)],
    ["GROSS MGN", p("grossMarginTTM")],
    ["OP MGN", p("operatingMarginTTM")],
    ["NET MGN", p("netProfitMarginTTM")],
    ["ROE", p("roeTTM", 0)],
    ["REV GR", m.revenueGrowthTTMYoy != null ? pct(m.revenueGrowthTTMYoy, 1) : "—"],
    ["EPS GR", m.epsGrowthTTMYoy != null ? pct(m.epsGrowthTTMYoy, 1) : "—"],
    ["DEBT/EQ", n("totalDebt/totalEquityQuarterly")],
    ["CURR RATIO", n("currentRatioQuarterly")],
    ["OPEN", fixed(q?.open)],
    ["PREV CLOSE", fixed(q?.prev_close)],
    ["DAY LOW", fixed(q?.low)],
    ["DAY HIGH", fixed(q?.high)],
  ];
  return (
    <Pane title="Key stats" right="TTM" style={{ gridColumn: 3, gridRow: 1 }}>
      <div className="body">
        <div className="kv m">
          {rows.map(([k, v]) => (
            <div key={k}>
              <span className="dim">{k}</span>
              <span>{v}</span>
            </div>
          ))}
        </div>
        {!Object.keys(m).length ? <Empty>FUNDAMENTALS ARRIVE WITH A FINNHUB REFRESH (WATCH OR REFRESH THIS TICKER).</Empty> : null}
      </div>
    </Pane>
  );
}

// ── news ──────────────────────────────────────────────────────────────────
function TickerNews({ symbol, day, clearDay }: { symbol: string; day: NewsDay | null; clearDay: () => void }) {
  const [sort, setSort] = useState<"impact" | "recent">("impact");
  const [limit, setLimit] = useState(NEWS_PAGE);
  const base = day
    ? `/api/statuses${qs({ ticker: symbol, since: day.dates[0], until: day.dates[day.dates.length - 1], sort, limit })}`
    : `/api/hub/securities/${encodeURIComponent(symbol)}/news${qs({ sort, limit })}`;
  const res = useApi<NewsPage>(base);
  const items = res.data?.items ?? [];
  const reactions = useApi<ReactionsResponse>(reactionsKey(items.map((i) => i.created_at), [symbol]));
  const move = movesLookup(reactions.data);

  return (
    <Pane
      title={day ? `${symbol} · ${day.dates.length > 1 ? `${shortDate(day.dates[0])} – ${shortDate(day.dates[day.dates.length - 1])}` : shortDate(day.dates[0])}` : `${symbol} in the news`}
      right={
        day ? (
          <button type="button" onClick={clearDay}>
            CLEAR DAY ×
          </button>
        ) : (
          <button type="button" onClick={() => setSort(sort === "impact" ? "recent" : "impact")} title="Toggle sort">
            {sort === "impact" ? "BY IMPACT ⇅" : "LATEST ⇅"}
          </button>
        )
      }
      style={{ gridColumn: 1, gridRow: 2 }}
    >
      <div className="body">
        {res.error && !res.data ? (
          <PaneError error={res.error} onRetry={() => res.mutate()} />
        ) : !res.data ? (
          <SkRows rows={6} h={48} />
        ) : !items.length ? (
          <Empty>NO STORIES MENTION {symbol} {day ? "ON THIS DAY" : "YET"}. CLICK A MARKER ON THE CHART TO SEE A DAY.</Empty>
        ) : (
          <>
            {items.map((n) => {
              const r = move(n.created_at, symbol)?.d1;
              return (
                <Link key={n.id} href={`/news${qs({ id: n.id })}`} className="st" style={{ display: "grid", gridTemplateColumns: "36px minmax(0, 1fr) 70px", gap: 10, padding: 8, borderBottom: "1px solid var(--rule)" }}>
                  <span className="m amb" style={{ fontWeight: 600, fontSize: 15 }}>
                    {impact100(n) ?? "—"}
                  </span>
                  <span style={{ minWidth: 0 }}>
                    <span className="m dim trunc" style={{ fontSize: 11, display: "block" }}>
                      {srcShort(n)} · {dayMonth(n.created_at)}
                    </span>
                    <span style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.3 }}>{n.title}</span>
                  </span>
                  <span className={`m ${cls(r)}`} style={{ fontSize: 12, textAlign: "right" }}>
                    {reactions.data ? pct(r, 1) : ""}
                    <span className="dim" style={{ display: "block", fontSize: 10 }}>
                      +1D
                    </span>
                  </span>
                </Link>
              );
            })}
            {items.length >= limit ? (
              <div style={{ padding: 8, textAlign: "center" }}>
                <button type="button" className="btn" onClick={() => setLimit(limit + NEWS_PAGE)} disabled={res.isValidating}>
                  {res.isValidating ? "LOADING…" : "LOAD MORE"}
                </button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </Pane>
  );
}

// ── news vs price ─────────────────────────────────────────────────────────
function NewsVsPrice({ year, rec }: { year: PricesResponse | undefined; rec: Recommendation | null }) {
  const rows = useMemo(() => {
    if (!year) return null;
    const bars = year.bars
      .filter((b) => b.close !== null)
      .map((b) => ({ time: b.date, open: b.open ?? b.close!, high: b.high ?? b.close!, low: b.low ?? b.close!, close: b.close!, volume: b.volume }));
    const idx = new Map(bars.map((b, i) => [b.time, i]));
    const days = [...snapNewsDays(bars, year.news_markers).values()];
    const ret = (d: NewsDay) => {
      const i = idx.get(d.time);
      if (i === undefined || i === 0) return null;
      return (bars[i].close / bars[i - 1].close - 1) * 100;
    };
    const bucket = (k: string, test: (d: NewsDay) => boolean) => {
      const sel = days.filter(test);
      const moves = sel.map(ret).filter((v): v is number => v !== null);
      return { k, n: sel.reduce((a, d) => a + d.count, 0), v: moves.length ? moves.reduce((a, b) => a + b, 0) / moves.length : null };
    };
    return [
      bucket("Positive (tone above +0.3)", (d) => d.sentiment !== null && d.sentiment > 0.3),
      bucket("Neutral", (d) => d.sentiment !== null && d.sentiment >= -0.3 && d.sentiment <= 0.3),
      bucket("Negative (tone below −0.3)", (d) => d.sentiment !== null && d.sentiment < -0.3),
      bucket("High impact (70+)", (d) => (d.impact ?? 0) >= 0.7),
    ];
  }, [year]);

  const parts = rec
    ? [
        { k: "STRONG BUY", v: rec.strongBuy, bg: "var(--up)", c: "up" },
        { k: "BUY", v: rec.buy, bg: "color-mix(in srgb, var(--up) 55%, var(--pane))", c: "" },
        { k: "HOLD", v: rec.hold, bg: "var(--rule)", c: "dim" },
        { k: "SELL", v: rec.sell, bg: "color-mix(in srgb, var(--dn) 55%, var(--pane))", c: "" },
        { k: "STRONG SELL", v: rec.strongSell, bg: "var(--dn)", c: "dn" },
      ]
    : [];
  const total = parts.reduce((a, p) => a + (p.v || 0), 0);

  return (
    <Pane title="News vs price" right="LAST 12 MONTHS" style={{ gridColumn: 2, gridRow: 2 }}>
      <div className="body">
        <div className="r m dim" style={{ fontSize: 11 }}>
          <span style={{ flex: 1 }}>AFTER NEWS THAT IS…</span>
          <span style={{ width: 60, textAlign: "right" }}>STORIES</span>
          <span style={{ width: 92, textAlign: "right" }}>AVG +1D</span>
        </div>
        {!rows ? (
          <SkRows rows={4} />
        ) : (
          rows.map((x) => (
            <div key={x.k} className="r m" style={{ fontSize: 13 }}>
              <span style={{ flex: 1, fontFamily: "var(--font-archivo)" }}>{x.k}</span>
              <span style={{ width: 60, textAlign: "right" }}>{x.n}</span>
              <span className={cls(x.v)} style={{ width: 92, textAlign: "right" }}>
                {pct(x.v)}
              </span>
            </div>
          ))
        )}
        <div className="m dim" style={{ padding: "10px 8px 4px", fontSize: 11 }}>
          ANALYST RATINGS{rec ? ` · ${shortDate(rec.period).toUpperCase()}` : ""}
        </div>
        {total ? (
          <>
            <div style={{ display: "flex", height: 22, margin: "0 8px", gap: 2 }} role="img" aria-label={parts.map((p) => `${p.k.toLowerCase()} ${p.v}`).join(", ")}>
              {parts.map((p) => (p.v ? <div key={p.k} style={{ flex: p.v, background: p.bg }} /> : null))}
            </div>
            <div className="m" style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 6, padding: "6px 8px", fontSize: 11 }}>
              {parts.map((p) => (
                <span key={p.k} className={p.c}>
                  {p.k} {p.v}
                </span>
              ))}
            </div>
          </>
        ) : (
          <Empty>NO ANALYST RATINGS STORED.</Empty>
        )}
      </div>
    </Pane>
  );
}

// ── peers ─────────────────────────────────────────────────────────────────
function Peers({ symbol, sector }: { symbol: string; sector: string | null }) {
  const res = useApi<SecuritiesPage>(sector && sector !== "ETF" ? `/api/hub/securities${qs({ sector, kind: "stock", sort: "market_cap", limit: 9 })}` : null);
  const peers = (res.data?.items ?? []).filter((x) => x.ticker !== symbol).slice(0, 8);
  return (
    <Pane title="Peers" right={sector && sector !== "ETF" ? `${shortSector(sector).toUpperCase()} · DAY · P/E` : "DAY · P/E"} style={{ gridColumn: 3, gridRow: 2 }}>
      <div className="body">
        {!sector || sector === "ETF" ? (
          <Empty>NO SECTOR ON FILE, SO NO PEER GROUP.</Empty>
        ) : res.error && !res.data ? (
          <PaneError error={res.error} onRetry={() => res.mutate()} />
        ) : !res.data ? (
          <SkRows rows={7} />
        ) : (
          peers.map((x) => (
            <Link key={x.ticker} href={`/ticker/${encodeURIComponent(x.ticker)}`} className="r m" style={{ fontSize: 13 }}>
              <span style={{ fontWeight: 600, width: 56 }}>{x.ticker}</span>
              <span style={{ flex: 1, textAlign: "right" }}>{fixed(x.price)}</span>
              <span className={cls(x.pct_change)} style={{ width: 68, textAlign: "right" }}>
                {pct(x.pct_change)}
              </span>
              <span className="dim" style={{ width: 44, textAlign: "right" }}>
                {num(x.pe, 1)}
              </span>
            </Link>
          ))
        )}
      </div>
    </Pane>
  );
}
