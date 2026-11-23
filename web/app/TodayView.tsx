"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { qs, send, useApi, writeErrorMessage, type NewsItem, type NewsPage, type OddsResponse, type Portfolio, type SecuritiesPage, type SecurityRow, type WatchItem } from "@/lib/api";
import { cls, fixed, pct, pts, signed } from "@/lib/format";
import { useHotkeys } from "@/lib/hotkeys";
import { impact100, sectorWords, srcShort, toneOf, topicShort, WASHINGTON_SOURCES, kindShort } from "@/lib/news";
import { SECTOR_ETFS, TAPE } from "@/lib/sectors";
import { hoursAgo, storyTime, useNow } from "@/lib/time";
import { Bar, Empty, heat, Pane, PaneError, SkRows } from "@/components/term";

const WASH = WASHINGTON_SOURCES.join(",");

function useQuotes(tickers: readonly string[]) {
  const key = tickers.length ? `/api/hub/securities${qs({ scope: "all", tickers: tickers.join(","), limit: 200 })}` : null;
  const res = useApi<SecuritiesPage>(key);
  const map = new Map<string, SecurityRow>((res.data?.items ?? []).map((r) => [r.ticker, r]));
  return { ...res, map };
}

export function TodayView() {
  const now = useNow();
  const router = useRouter();
  const since48 = now !== null ? hoursAgo(now, 48) : null;
  const stories = useApi<NewsPage>(since48 ? `/api/statuses${qs({ sort: "impact", since: since48, limit: 12 })}` : null);
  const items = stories.data?.items ?? [];
  const [sel, setSel] = useState(0);
  const cur = Math.min(sel, Math.max(items.length - 1, 0));

  useHotkeys({
    j: () => setSel((i) => Math.min(i + 1, items.length - 1)),
    k: () => setSel((i) => Math.max(i - 1, 0)),
    Enter: () => {
      if (items[cur]) router.push(`/news${qs({ id: items[cur].id })}`);
    },
  });

  return (
    <>
      <div className="grid-term g-today">
        <Stories items={items} loading={!stories.data} error={stories.error} retry={() => stories.mutate()} sel={cur} now={now} />
        <Sectors />
        <OddsPane />
        <Movers />
        <Washington now={now} />
        <Watchlist />
      </div>
      <Tape />
    </>
  );
}

// ── what moved markets ─────────────────────────────────────────────────────
function Stories({ items, loading, error, retry, sel, now }: { items: NewsItem[]; loading: boolean; error: unknown; retry: () => void; sel: number; now: number | null }) {
  const tickers = [...new Set(items.flatMap((s) => s.stocks.map((x) => x.ticker)))];
  const quotes = useQuotes(tickers);
  return (
    <Pane title="What moved markets · 48h" right={<Link href="/news">3 NEWS ›</Link>} style={{ gridColumn: 1, gridRow: 1 }}>
      <div className="body">
        {error && loading ? (
          <PaneError error={error} onRetry={retry} />
        ) : loading ? (
          <SkRows rows={6} h={64} />
        ) : !items.length ? (
          <Empty>NO SCORED STORIES IN THE LAST 48 HOURS. RUN AN INGEST TO REFRESH.</Empty>
        ) : (
          items.map((s, i) => {
            const t = toneOf(s);
            return (
              <Link
                key={s.id}
                href={`/news${qs({ id: s.id })}`}
                className="st"
                style={{ display: "grid", gridTemplateColumns: "44px 1fr", gap: 10, padding: "10px 8px", borderBottom: "1px solid var(--rule)", background: i === sel ? "var(--sel)" : undefined, borderLeft: `3px solid ${i === sel ? "var(--amb)" : "transparent"}` }}
              >
                <div className="m" style={{ textAlign: "center" }}>
                  <div className="amb" style={{ fontSize: 20, fontWeight: 600, lineHeight: 1.1 }}>
                    {impact100(s) ?? "—"}
                  </div>
                  <div className="dim" style={{ fontSize: 9 }}>
                    IMP
                  </div>
                </div>
                <div style={{ minWidth: 0 }}>
                  <div className="m trunc" style={{ fontSize: 11 }}>
                    <span className="amb">{srcShort(s)}</span>
                    <span className="dim">
                      {" "}
                      {storyTime(s.created_at, now)} · {topicShort(s)}
                      {t ? " · " : ""}
                    </span>
                    {t ? <span className={t.cls}>{t.tone}</span> : null}
                  </div>
                  <div style={{ fontWeight: 600, fontSize: 15, lineHeight: 1.3, margin: "3px 0 4px" }}>{s.title}</div>
                  <div className="m" style={{ fontSize: 12, display: "flex", flexWrap: "wrap", gap: "2px 14px" }}>
                    {s.stocks.slice(0, 4).map((k) => {
                      const q = quotes.map.get(k.ticker);
                      return (
                        <span key={k.ticker}>
                          {k.ticker} <span className={cls(q?.pct_change)}>{q ? pct(q.pct_change) : ""}</span>
                        </span>
                      );
                    })}
                    <span className="dim">{sectorWords(s)}</span>
                  </div>
                </div>
              </Link>
            );
          })
        )}
      </div>
    </Pane>
  );
}

// ── movers ────────────────────────────────────────────────────────────────
function MoverList({ order }: { order: "desc" | "asc" }) {
  const res = useApi<SecuritiesPage>(`/api/hub/securities${qs({ kind: "stock", sort: "pct_change", order, limit: 12 })}`);
  const up = order === "desc";
  return (
    <div className="pane">
      <div className="r m" style={{ fontSize: 11 }}>
        <span className={up ? "up" : "dn"}>{up ? "▲ GAINERS" : "▼ LOSERS"}</span>
        <span className="dim">DAY</span>
      </div>
      <div className="body">
        {res.error && !res.data ? (
          <PaneError error={res.error} onRetry={() => res.mutate()} />
        ) : !res.data ? (
          <SkRows rows={7} />
        ) : (
          res.data.items.map((x) => (
            <Link key={x.ticker} href={`/ticker/${encodeURIComponent(x.ticker)}`} className="r m" style={{ fontSize: 13 }}>
              <span style={{ fontWeight: 600, width: 52, flexShrink: 0 }}>{x.ticker}</span>
              <span className="dim trunc" style={{ flex: 1, fontFamily: "var(--font-archivo)", fontSize: 12 }}>
                {x.name}
              </span>
              <span className={cls(x.pct_change)}>{pct(x.pct_change)}</span>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

function Movers() {
  const total = useApi<SecuritiesPage>("/api/hub/securities?kind=stock&limit=1");
  return (
    <Pane
      title={`Top movers · ${total.data ? total.data.total.toLocaleString() : "—"} core stocks`}
      right={<Link href="/markets">4 MKTS ›</Link>}
      style={{ gridColumn: 1, gridRow: 2 }}
    >
      <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 2, background: "var(--rule)" }}>
        <MoverList order="desc" />
        <MoverList order="asc" />
      </div>
    </Pane>
  );
}

// ── sectors ───────────────────────────────────────────────────────────────
function Sectors() {
  const quotes = useQuotes([...SECTOR_ETFS.map((s) => s.etf), "SPY"]);
  const tiles = [...SECTOR_ETFS.map((s) => ({ n: s.name, t: s.etf, href: `/markets${qs({ sector: s.gics })}` })), { n: "S&P 500", t: "SPY", href: "/markets" }];
  return (
    <Pane title="Sectors · day" right={<Link href="/markets">4 MKTS ›</Link>} style={{ gridColumn: 2, gridRow: 1 }}>
      {quotes.error && !quotes.data ? (
        <PaneError error={quotes.error} onRetry={() => quotes.mutate()} />
      ) : (
        <div className="body" style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gridAutoRows: "minmax(54px, 1fr)", gap: 2, padding: 2, background: "var(--rule)" }}>
          {tiles.map((x) => {
            const v = quotes.map.get(x.t)?.pct_change;
            return (
              <Link key={x.t} href={x.href} title={`${x.t} sector ETF`} style={{ ...heat(quotes.data ? v : null), padding: "6px 8px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                <span style={{ fontSize: 12, fontWeight: 500 }}>{x.n}</span>
                <span className="m" style={{ fontWeight: 600, fontSize: 14 }}>
                  {quotes.data ? pct(v, 1) : ""}
                </span>
              </Link>
            );
          })}
        </div>
      )}
    </Pane>
  );
}

// ── odds ──────────────────────────────────────────────────────────────────
function OddsPane() {
  const res = useApi<OddsResponse>("/api/hub/odds?limit=6", { refreshInterval: 300_000 });
  return (
    <Pane title="Market odds" right="POLYMARKET" style={{ gridColumn: 3, gridRow: 1 }}>
      <div className="body">
        {res.error && !res.data ? (
          <PaneError error={res.error} onRetry={() => res.mutate()} />
        ) : !res.data ? (
          <SkRows rows={5} h={48} />
        ) : !res.data.items.length ? (
          <Empty>{res.data.error ? "POLYMARKET IS UNREACHABLE RIGHT NOW." : "NO OPEN MARKETS FOUND."}</Empty>
        ) : (
          res.data.items.map((o) => (
            <a key={o.question} href={o.url ?? undefined} target="_blank" rel="noopener noreferrer" className="st" style={{ display: "block", padding: 8, borderBottom: "1px solid var(--rule)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13 }}>
                <span>{o.question}</span>
                <span className="m" style={{ fontWeight: 600 }}>
                  {Math.round(o.probability)}%
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 64px", gap: 8, alignItems: "center", marginTop: 5 }}>
                <Bar value={o.probability} />
                <span className={`m ${cls(o.change_1d)}`} style={{ fontSize: 11, textAlign: "right" }}>
                  {pts(o.change_1d)}
                </span>
              </div>
            </a>
          ))
        )}
      </div>
    </Pane>
  );
}

// ── washington ────────────────────────────────────────────────────────────
function Washington({ now }: { now: number | null }) {
  const since = now !== null ? hoursAgo(now, 24 * 7) : null;
  const latest = useApi<NewsPage>(`/api/statuses${qs({ source: WASH, limit: 8 })}`);
  const eos = useApi<NewsPage>(since ? `/api/statuses${qs({ source: WASH, kind: "Executive Order", since, limit: 1, with_total: "true" })}` : null);
  const fr = useApi<NewsPage>(since ? `/api/statuses${qs({ source: "federal_register", since, limit: 1, with_total: "true" })}` : null);
  const peak = useApi<NewsPage>(since ? `/api/statuses${qs({ source: WASH, sort: "impact", since, limit: 1 })}` : null);
  const peakItem = peak.data?.items[0];
  return (
    <Pane title="Washington · latest" right={<Link href="/washington">2 WASH ›</Link>} style={{ gridColumn: 2, gridRow: 2 }}>
      <div className="body">
        <div className="m" style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", padding: 8, borderBottom: "1px solid var(--rule)" }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 600 }}>{eos.data?.total ?? "—"}</div>
            <div className="dim" style={{ fontSize: 10 }}>
              EXEC ORDERS · 7D
            </div>
          </div>
          <div>
            <div style={{ fontSize: 20, fontWeight: 600 }}>{fr.data?.total ?? "—"}</div>
            <div className="dim" style={{ fontSize: 10 }}>
              FED REGISTER · 7D
            </div>
          </div>
          <Link href={peakItem ? `/news${qs({ id: peakItem.id })}` : "/washington"}>
            <div className="amb" style={{ fontSize: 20, fontWeight: 600 }}>
              {peakItem ? impact100(peakItem) : "—"}
            </div>
            <div className="dim" style={{ fontSize: 10 }}>
              PEAK IMPACT · 7D
            </div>
          </Link>
        </div>
        {latest.error && !latest.data ? (
          <PaneError error={latest.error} onRetry={() => latest.mutate()} />
        ) : !latest.data ? (
          <SkRows rows={4} />
        ) : !latest.data.items.length ? (
          <Empty>NOTHING FROM WASHINGTON ARCHIVED YET.</Empty>
        ) : (
          latest.data.items.map((w) => (
            <Link key={w.id} href={`/news${qs({ id: w.id })}`} className="r" style={{ alignItems: "flex-start" }}>
              <span style={{ fontSize: 13, lineHeight: 1.35 }}>
                <span className="m amb" style={{ fontSize: 11 }}>
                  {kindShort(w.kind)}{" "}
                </span>
                {w.title}
              </span>
              <span className="m dim" style={{ fontSize: 11, whiteSpace: "nowrap" }}>
                {storyTime(w.created_at, now)}
              </span>
            </Link>
          ))
        )}
      </div>
    </Pane>
  );
}

// ── watchlist ─────────────────────────────────────────────────────────────
function Watchlist() {
  const list = useApi<{ items: WatchItem[] }>("/api/hub/watchlist");
  // Positions need the hub token; without it the backend says 401 and the row hides.
  const port = useApi<Portfolio>("/api/hub/portfolio", { shouldRetryOnError: false });
  const [error, setError] = useState<string | null>(null);
  const t = port.data?.positions.length ? port.data.totals : null;

  const remove = async (ticker: string) => {
    setError(null);
    try {
      await send("DELETE", `/api/hub/watchlist/${encodeURIComponent(ticker)}`);
    } catch (e) {
      setError(writeErrorMessage(e));
    }
  };

  return (
    <Pane title="Watchlist" right={<Link href="/ticker">5 STOCK ›</Link>} style={{ gridColumn: 3, gridRow: 2 }}>
      {t ? (
        <Link href="/portfolio" className="r m" style={{ fontSize: 12, background: "var(--sel)" }}>
          <span className="amb">PORT</span>
          <span>{fixed(t.market_value)}</span>
          <span className={cls(t.day_change)}>
            {signed(t.day_change)} {pct(t.day_change_pct)}
          </span>
        </Link>
      ) : null}
      {error ? (
        <div role="alert" className="m dn" style={{ fontSize: 11, padding: "4px 8px" }}>
          {error}
        </div>
      ) : null}
      <div className="body">
        {list.error && !list.data ? (
          <PaneError error={list.error} onRetry={() => list.mutate()} />
        ) : !list.data ? (
          <SkRows rows={6} />
        ) : !list.data.items.length ? (
          <Empty>WATCHLIST IS EMPTY. OPEN A STOCK AND PRESS W TO WATCH IT.</Empty>
        ) : (
          list.data.items.map((w) => (
            <div key={w.ticker} className="r m hov" style={{ fontSize: 13, padding: 0 }}>
              <Link href={`/ticker/${encodeURIComponent(w.ticker)}`} style={{ display: "flex", flex: 1, gap: 10, padding: "6px 0 6px 8px", minWidth: 0 }}>
                <span style={{ fontWeight: 600, width: 56 }}>{w.ticker}</span>
                <span style={{ flex: 1, textAlign: "right" }}>{fixed(w.quote?.price)}</span>
                <span className={cls(w.quote?.pct_change)} style={{ width: 72, textAlign: "right" }}>
                  {pct(w.quote?.pct_change)}
                </span>
              </Link>
              <button type="button" onClick={() => remove(w.ticker)} aria-label={`Remove ${w.ticker} from watchlist`} className="dim" style={{ background: "none", border: 0, cursor: "pointer", padding: "6px 8px", font: "inherit" }}>
                ×
              </button>
            </div>
          ))
        )}
      </div>
    </Pane>
  );
}

// ── tape ──────────────────────────────────────────────────────────────────
function Tape() {
  const quotes = useQuotes(TAPE);
  return (
    <footer className="m" aria-label="Market tape" style={{ display: "flex", overflowX: "auto", whiteSpace: "nowrap", borderTop: "1px solid var(--rule)", fontSize: 12, minHeight: 27 }}>
      {TAPE.map((t) => {
        const q = quotes.map.get(t);
        if (!q || q.price === null) return null;
        return (
          <Link key={t} href={`/ticker/${t}`} style={{ padding: "5px 14px", borderRight: "1px solid var(--rule)" }}>
            <span className="amb">{t}</span> {fixed(q.price)} <span className={cls(q.pct_change)}>{pct(q.pct_change)}</span>
          </Link>
        );
      })}
    </footer>
  );
}
