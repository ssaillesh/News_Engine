"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { fetcher, LIVE_MS, qs, send, useApi, writeErrorMessage, type Holding, type NewsPage, type Portfolio, type PricesResponse, type SecuritiesPage } from "@/lib/api";
import { cls, fixed, num, pct, shortDate, signed } from "@/lib/format";
import { impact100, srcShort, toneOf } from "@/lib/news";
import { shortSector } from "@/lib/sectors";
import { hoursAgo, storyTime, useNow } from "@/lib/time";
import { Bar, Empty, LineChart, Pane, PaneError, SkRows, Tabs, Toolbar } from "@/components/term";

const RANGES = [
  { value: "1m", label: "1M" },
  { value: "3m", label: "3M" },
  { value: "6m", label: "6M" },
  { value: "1y", label: "1Y" },
] as const;
type Range = (typeof RANGES)[number]["value"];

export function PortfolioSkeleton() {
  return (
    <>
      <div className="m" style={{ display: "flex", borderBottom: "1px solid var(--rule)", minHeight: 62 }} />
      <div className="grid-term g-port">
        <Pane title="Holdings">
          <SkRows rows={6} />
        </Pane>
        <Pane title="Allocation">
          <SkRows rows={5} />
        </Pane>
        <Pane title="Value vs S&P 500">
          <SkRows rows={6} />
        </Pane>
        <Pane title="News on your holdings">
          <SkRows rows={6} />
        </Pane>
      </div>
    </>
  );
}

/** Today's holdings valued over the range: Σ shares × close, with SPY alongside, both indexed to 100. */
function useHistory(positions: { ticker: string; shares: number }[], range: Range) {
  const tickers = positions.map((p) => p.ticker);
  const key = positions.length ? ["pf-history", range, ...tickers] : null;
  const res = useSWR(
    key,
    async () => {
      const all = await Promise.all([...tickers, "SPY"].map((t) => fetcher<PricesResponse>(`/api/hub/securities/${encodeURIComponent(t)}/prices?range=${range}`)));
      return all;
    },
    { refreshInterval: LIVE_MS, revalidateOnFocus: true, keepPreviousData: true },
  );
  if (!res.data) return { ...res, series: null };
  const spy = res.data[res.data.length - 1];
  const calendar = spy.bars.length ? spy.bars.map((b) => b.date) : [...new Set(res.data.flatMap((r) => r.bars.map((b) => b.date)))].sort();
  const closes = res.data.map((r) => new Map(r.bars.filter((b) => b.close !== null).map((b) => [b.date, b.close as number])));
  // Forward-fill gaps; before a ticker's first bar, hold its first close (no jump on listing).
  const filled = closes.map((m) => {
    const first = calendar.map((d) => m.get(d)).find((v) => v !== undefined) ?? null;
    let last: number | null = first;
    return calendar.map((d) => {
      const v = m.get(d);
      if (v !== undefined) last = v;
      return last;
    });
  });
  const value = calendar.map((_, i) => positions.reduce((sum, p, k) => sum + p.shares * (filled[k][i] ?? 0), 0));
  const spyVals = filled[filled.length - 1];
  const index = (vals: (number | null)[]) => {
    const base = vals.find((v) => v !== null && v > 0);
    return vals.map((v) => (v === null || !base ? null : (v / base) * 100));
  };
  const port = index(value);
  const bench = index(spyVals);
  const ret = (vals: (number | null)[]) => {
    const xs = vals.filter((v): v is number => v !== null);
    return xs.length > 1 ? xs[xs.length - 1] - 100 : null;
  };
  return { ...res, series: { calendar, port, bench, portRet: ret(port), benchRet: ret(bench) } };
}

export function PortfolioView() {
  const params = useSearchParams();
  const addTicker = params.get("add")?.toUpperCase() ?? "";
  const pf = useApi<Portfolio>("/api/hub/portfolio", { shouldRetryOnError: false });
  const [range, setRange] = useState<Range>("6m");
  const p = pf.data;
  const t = p?.totals;
  const priced = (p?.positions ?? []).filter((x) => x.price !== null);
  const hist = useHistory(
    priced.map((x) => ({ ticker: x.ticker, shares: x.shares })),
    range,
  );
  const s = hist.series;
  const vs = s && s.portRet !== null && s.benchRet !== null ? s.portRet - s.benchRet : null;

  const kpis: { l: string; v: string; s?: string; c?: string }[] = t
    ? [
        { l: "MARKET VALUE", v: fixed(t.market_value) },
        { l: "DAY", v: signed(t.day_change), s: pct(t.day_change_pct), c: cls(t.day_change) },
        { l: "UNREALIZED P&L", v: signed(t.unrealized_pnl), s: pct(t.unrealized_pnl_pct), c: cls(t.unrealized_pnl) },
        { l: "COST BASIS", v: fixed(t.cost_basis) },
        {
          l: `VS S&P 500 · ${range.toUpperCase()}`,
          v: vs === null ? "—" : `${signed(vs, 1)} PTS`,
          s: vs === null ? "" : vs >= 0 ? "AHEAD" : "BEHIND",
          c: cls(vs),
        },
      ]
    : [];

  if (pf.error && !p) {
    return (
      <div className="grid-term">
        <Pane title="Portfolio">
          <PaneError error={pf.error} onRetry={() => pf.mutate()} />
        </Pane>
      </div>
    );
  }
  if (!p) return <PortfolioSkeleton />;

  return (
    <>
      <div className="m" style={{ display: "flex", flexWrap: "wrap", borderBottom: "1px solid var(--rule)" }}>
        {kpis.map((k) => (
          <div key={k.l} className="kpi">
            <div className="dim" style={{ fontSize: 10 }}>
              {k.l}
            </div>
            <div className={k.c} style={{ fontSize: 20, fontWeight: 600 }}>
              {k.v}
            </div>
            <div className={k.c} style={{ fontSize: 11, minHeight: 14 }}>
              {k.s}
            </div>
          </div>
        ))}
        {p.unpriced.length ? (
          <div className="kpi" style={{ alignSelf: "center", color: "var(--hot)", fontSize: 11, borderRight: 0 }}>
            NO QUOTE YET FOR {p.unpriced.join(", ")}: LISTED BUT LEFT OUT OF TOTALS.
          </div>
        ) : null}
      </div>

      <div className="grid-term g-port">
        <Holdings portfolio={p} initialTab={addTicker ? "lots" : "holdings"} addTicker={addTicker} />

        <Pane title="Value vs S&P 500" right={`INDEXED · ${range.toUpperCase()}`} style={{ gridColumn: 1, gridRow: 2 }}>
          <Toolbar>
            <Tabs label="Range" value={range} onChange={setRange} options={RANGES} />
            <span className="m" style={{ marginLeft: "auto", fontSize: 11 }}>
              <span className="amb">━ PORTFOLIO {s ? pct(s.portRet, 1) : ""}</span>
              {"   "}
              <span className="dim">┅ SPY {s ? pct(s.benchRet, 1) : ""}</span>
            </span>
          </Toolbar>
          <div style={{ flex: 1, minHeight: 200, padding: 8, display: "flex", flexDirection: "column", opacity: hist.isValidating && s ? 0.6 : 1 }}>
            {!priced.length ? (
              <Empty>ADD A PRICED HOLDING TO CHART IT AGAINST THE S&amp;P 500.</Empty>
            ) : hist.error && !s ? (
              <PaneError error={hist.error} onRetry={() => hist.mutate()} />
            ) : !s ? (
              <SkRows rows={6} />
            ) : (
              <>
                <div style={{ flex: 1, minHeight: 0 }}>
                  <LineChart
                    label={`Current holdings against SPY over ${range}, indexed to 100: portfolio ${pct(s.portRet, 1)}, SPY ${pct(s.benchRet, 1)}`}
                    baseline={100}
                    series={[
                      { values: s.bench, color: "var(--dim)", dash: "6 4" },
                      { values: s.port, color: "var(--amb)", width: 2.5 },
                    ]}
                  />
                </div>
                <div className="m dim" style={{ display: "flex", justifyContent: "space-between", fontSize: 11, paddingTop: 4 }}>
                  <span>{s.calendar[0] ? shortDate(s.calendar[0]).toUpperCase() : ""}</span>
                  <span>CURRENT HOLDINGS, HELD THROUGHOUT</span>
                  <span>{s.calendar.length ? shortDate(s.calendar[s.calendar.length - 1]).toUpperCase() : ""}</span>
                </div>
              </>
            )}
          </div>
        </Pane>

        <Allocation portfolio={p} />
        <HoldingsNews tickers={p.positions.map((x) => x.ticker)} />
      </div>
    </>
  );
}

// ── holdings / lots ───────────────────────────────────────────────────────
function Holdings({ portfolio, initialTab, addTicker }: { portfolio: Portfolio; initialTab: "holdings" | "lots"; addTicker: string }) {
  const [tab, setTab] = useState<"holdings" | "lots">(initialTab);
  const lots = useApi<{ items: Holding[] }>("/api/hub/holdings");
  const n = portfolio.positions.length;
  const lotCount = portfolio.positions.reduce((a, x) => a + x.lots, 0);
  return (
    <Pane title="Holdings" right={`${n} ${n === 1 ? "POSITION" : "POSITIONS"} · ${lotCount} ${lotCount === 1 ? "LOT" : "LOTS"}`} style={{ gridColumn: 1, gridRow: 1 }}>
      <Toolbar>
        <Tabs
          label="View"
          value={tab}
          onChange={setTab}
          options={[
            { value: "holdings", label: "POSITIONS" },
            { value: "lots", label: "LOTS · EDIT" },
          ]}
        />
        <span className="m dim" style={{ marginLeft: "auto", fontSize: 11 }}>
          OR TYPE: BUY 10 AAPL @ 340
        </span>
      </Toolbar>
      <div className="body">
        {tab === "holdings" ? (
          !n ? (
            <Empty>NO POSITIONS YET. OPEN LOTS · EDIT TO ADD ONE, OR TYPE &quot;BUY 10 AAPL @ 340&quot; IN THE COMMAND LINE.</Empty>
          ) : (
            <table className="tbl" style={{ minWidth: 640 }}>
              <thead>
                <tr>
                  <th className="l">TICKER</th>
                  <th>SHARES</th>
                  <th>AVG COST</th>
                  <th>PRICE</th>
                  <th>VALUE</th>
                  <th>DAY</th>
                  <th>P&amp;L</th>
                  <th>P&amp;L %</th>
                  <th>WEIGHT</th>
                </tr>
              </thead>
              <tbody>
                {portfolio.positions.map((x) => (
                  <tr key={x.ticker} className="lk">
                    <td className="m l" style={{ fontWeight: 600 }}>
                      <Link href={`/ticker/${encodeURIComponent(x.ticker)}`} style={{ color: "var(--amb)" }} title={x.name ?? undefined}>
                        {x.ticker}
                      </Link>
                    </td>
                    <td className="m">{num(x.shares, 4)}</td>
                    <td className="m">{fixed(x.avg_cost)}</td>
                    <td className="m">{fixed(x.price)}</td>
                    <td className="m">{fixed(x.market_value)}</td>
                    <td className={`m ${cls(x.day_change_pct)}`}>{pct(x.day_change_pct)}</td>
                    <td className={`m ${cls(x.unrealized_pnl)}`}>{signed(x.unrealized_pnl)}</td>
                    <td className={`m ${cls(x.unrealized_pnl)}`}>{pct(x.unrealized_pnl_pct, 1)}</td>
                    <td className="m">{x.weight_pct != null ? `${num(x.weight_pct, 1)}%` : <span className="dim">UNPRICED</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        ) : lots.error && !lots.data ? (
          <PaneError error={lots.error} onRetry={() => lots.mutate()} />
        ) : (
          <>
            <AddLot initialTicker={addTicker} />
            {!lots.data ? (
              <SkRows rows={4} />
            ) : !lots.data.items.length ? (
              <Empty>NO LOTS RECORDED YET.</Empty>
            ) : (
              lots.data.items.map((h) => <LotRow key={h.id} lot={h} />)
            )}
          </>
        )}
      </div>
    </Pane>
  );
}

type Draft = { ticker: string; shares: string; avg_cost: string; opened_at: string; note: string };

function toBody(d: Draft) {
  const shares = Number(d.shares);
  const avg = Number(d.avg_cost);
  if (!(shares > 0)) throw new Error("Shares must be greater than zero.");
  if (d.avg_cost.trim() === "" || !(avg >= 0)) throw new Error("Average cost must be zero or more.");
  return { shares, avg_cost: avg, opened_at: d.opened_at || null, note: d.note.trim() || null };
}

function LotFields({ draft, setDraft, withTicker, idp }: { draft: Draft; setDraft: (d: Draft) => void; withTicker?: boolean; idp: string }) {
  const f = (k: keyof Draft) => ({ id: `${idp}-${k}`, value: draft[k], onChange: (e: { target: { value: string } }) => setDraft({ ...draft, [k]: e.target.value }) });
  const lab = (k: keyof Draft, text: string) => (
    <label htmlFor={`${idp}-${k}`} className="m dim" style={{ fontSize: 10, display: "block", marginBottom: 2 }}>
      {text}
    </label>
  );
  return (
    <>
      {withTicker ? (
        <div>
          {lab("ticker", "TICKER")}
          <input {...f("ticker")} className="fld" required placeholder="AAPL" autoCapitalize="characters" style={{ width: 84, textTransform: "uppercase" }} />
        </div>
      ) : null}
      <div>
        {lab("shares", "SHARES")}
        <input {...f("shares")} className="fld" required type="number" step="any" min="0" inputMode="decimal" style={{ width: 90 }} />
      </div>
      <div>
        {lab("avg_cost", "AVG COST")}
        <input {...f("avg_cost")} className="fld" required type="number" step="any" min="0" inputMode="decimal" style={{ width: 96 }} />
      </div>
      <div>
        {lab("opened_at", "OPENED")}
        <input {...f("opened_at")} className="fld" type="date" style={{ width: 140 }} />
      </div>
      <div style={{ flex: 1, minWidth: 120 }}>
        {lab("note", "NOTE")}
        <input {...f("note")} className="fld" maxLength={2000} placeholder="OPTIONAL" style={{ width: "100%" }} />
      </div>
    </>
  );
}

function AddLot({ initialTicker }: { initialTicker: string }) {
  const empty: Draft = { ticker: initialTicker, shares: "", avg_cost: "", opened_at: "", note: "" };
  const [draft, setDraft] = useState<Draft>(empty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await send("POST", "/api/hub/holdings", { ticker: draft.ticker.trim().toUpperCase(), ...toBody(draft) });
      setDraft({ ...empty, ticker: "" });
    } catch (err) {
      setError(writeErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} aria-label="Add a lot" style={{ padding: 8, borderBottom: "1px solid var(--rule)", background: "var(--sel)" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <LotFields draft={draft} setDraft={setDraft} withTicker idp="add" />
        <button type="submit" className="btn on" disabled={busy}>
          {busy ? "ADDING…" : "+ ADD LOT"}
        </button>
      </div>
      {error ? (
        <p role="alert" className="m dn" style={{ fontSize: 11, margin: "6px 0 0" }}>
          {error}
        </p>
      ) : null}
    </form>
  );
}

function LotRow({ lot }: { lot: Holding }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [draft, setDraft] = useState<Draft>({ ticker: lot.ticker, shares: "", avg_cost: "", opened_at: "", note: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      return true;
    } catch (err) {
      setError(writeErrorMessage(err));
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (editing) {
    return (
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (await run(() => send("PATCH", `/api/hub/holdings/${lot.id}`, toBody(draft)))) setEditing(false);
        }}
        aria-label={`Edit ${lot.ticker} lot`}
        style={{ padding: 8, borderBottom: "1px solid var(--rule)", background: "var(--sel)" }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
          <span className="m amb" style={{ fontWeight: 600, alignSelf: "center", width: 60 }}>
            {lot.ticker}
          </span>
          <LotFields draft={draft} setDraft={setDraft} idp={`lot${lot.id}`} />
          <button type="submit" className="btn on" disabled={busy}>
            {busy ? "SAVING…" : "SAVE"}
          </button>
          <button type="button" className="btn" onClick={() => setEditing(false)}>
            CANCEL
          </button>
        </div>
        {error ? (
          <p role="alert" className="m dn" style={{ fontSize: 11, margin: "6px 0 0" }}>
            {error}
          </p>
        ) : null}
      </form>
    );
  }

  return (
    <div className="r m" style={{ fontSize: 13, flexWrap: "wrap" }}>
      <Link href={`/ticker/${encodeURIComponent(lot.ticker)}`} className="amb" style={{ fontWeight: 600, width: 60 }}>
        {lot.ticker}
      </Link>
      <span>
        {num(lot.shares, 4)} @ {fixed(lot.avg_cost)}
      </span>
      <span className="dim">{fixed(lot.shares * lot.avg_cost)} COST</span>
      <span className="dim">{lot.opened_at ? `OPENED ${shortDate(lot.opened_at).toUpperCase()}` : ""}</span>
      {lot.note ? (
        <span className="dim trunc" style={{ flex: 1, fontFamily: "var(--font-archivo)", minWidth: 80 }}>
          {lot.note}
        </span>
      ) : (
        <span style={{ flex: 1 }} />
      )}
      <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
        {confirming ? (
          <>
            <span className="dim" style={{ fontSize: 11 }}>
              DELETE LOT?
            </span>
            <button type="button" className="btn danger" disabled={busy} onClick={() => run(() => send("DELETE", `/api/hub/holdings/${lot.id}`))}>
              {busy ? "DELETING…" : "DELETE"}
            </button>
            <button type="button" className="btn" onClick={() => setConfirming(false)}>
              KEEP
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setDraft({ ticker: lot.ticker, shares: String(lot.shares), avg_cost: String(lot.avg_cost), opened_at: lot.opened_at ?? "", note: lot.note ?? "" });
                setEditing(true);
                setConfirming(false);
              }}
            >
              EDIT
            </button>
            <button type="button" className="btn" onClick={() => setConfirming(true)}>
              DELETE
            </button>
          </>
        )}
      </span>
      {error ? (
        <span role="alert" className="dn" style={{ width: "100%", fontSize: 11 }}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

// ── allocation ────────────────────────────────────────────────────────────
function Allocation({ portfolio }: { portfolio: Portfolio }) {
  const tickers = portfolio.positions.map((x) => x.ticker);
  const secs = useApi<SecuritiesPage>(tickers.length ? `/api/hub/securities${qs({ scope: "all", tickers: tickers.join(","), limit: 100 })}` : null);
  const sectorOf = new Map((secs.data?.items ?? []).map((r) => [r.ticker, r.sector === "ETF" || r.type === "ETP" ? "ETFs" : shortSector(r.sector)]));
  const groups = new Map<string, { w: number; day: number; prev: number }>();
  for (const x of portfolio.positions) {
    if (x.weight_pct == null) continue;
    const k = sectorOf.get(x.ticker) ?? "Other";
    const g = groups.get(k) ?? { w: 0, day: 0, prev: 0 };
    g.w += x.weight_pct;
    g.day += x.day_change ?? 0;
    g.prev += (x.market_value ?? 0) - (x.day_change ?? 0);
    groups.set(k, g);
  }
  const rows = [...groups.entries()].map(([n, g]) => ({ n, w: g.w, d: g.prev ? (g.day / g.prev) * 100 : null })).sort((a, b) => b.w - a.w);
  const max = Math.max(1, ...rows.map((r) => r.w));
  const top3 = [...portfolio.positions].map((x) => x.weight_pct ?? 0).sort((a, b) => b - a).slice(0, 3).reduce((a, b) => a + b, 0);
  return (
    <Pane title="Allocation" right="BY SECTOR" style={{ gridColumn: 2, gridRow: 1 }}>
      <div className="body" style={{ padding: "6px 8px" }}>
        {!portfolio.positions.length ? (
          <Empty>NOTHING TO ALLOCATE YET.</Empty>
        ) : !secs.data ? (
          <SkRows rows={4} />
        ) : (
          <>
            {rows.map((a) => (
              <div key={a.n} style={{ display: "grid", gridTemplateColumns: "120px 1fr 56px 70px", gap: 10, alignItems: "center", padding: "7px 0", fontSize: 13 }}>
                <span className="trunc">{a.n}</span>
                <Bar value={(a.w / max) * 100} />
                <span className="m" style={{ textAlign: "right" }}>
                  {num(a.w, 1)}%
                </span>
                <span className={`m ${cls(a.d)}`} style={{ textAlign: "right" }}>
                  {pct(a.d, 1)}
                </span>
              </div>
            ))}
            <div className="m dim" style={{ fontSize: 11, paddingTop: 8, borderTop: "1px solid var(--rule)", marginTop: 4 }}>
              CONCENTRATION: TOP {Math.min(3, portfolio.positions.length)} POSITIONS = {Math.round(top3)}% OF VALUE
            </div>
          </>
        )}
      </div>
    </Pane>
  );
}

// ── news on holdings ──────────────────────────────────────────────────────
function HoldingsNews({ tickers }: { tickers: string[] }) {
  const now = useNow();
  const res = useApi<NewsPage>(tickers.length && now !== null ? `/api/statuses${qs({ ticker: tickers.join(","), sort: "impact", since: hoursAgo(now, 24 * 7), limit: 25 })}` : null);
  const held = new Set(tickers);
  return (
    <Pane title="News on your holdings · 7D" right={<Link href={`/news${qs({ ticker: tickers.join(","), w: "7D" })}`}>3 NEWS ›</Link>} style={{ gridColumn: 2, gridRow: 2 }}>
      <div className="body">
        {!tickers.length ? (
          <Empty>NO HOLDINGS, SO NO HOLDINGS NEWS.</Empty>
        ) : res.error && !res.data ? (
          <PaneError error={res.error} onRetry={() => res.mutate()} />
        ) : !res.data ? (
          <SkRows rows={6} h={48} />
        ) : !res.data.items.length ? (
          <Empty>NO STORIES ABOUT YOUR HOLDINGS THIS WEEK.</Empty>
        ) : (
          res.data.items.map((n) => {
            const t = toneOf(n);
            const tick = n.stocks.find((x) => held.has(x.ticker))?.ticker ?? n.stocks[0]?.ticker ?? "";
            return (
              <Link key={n.id} href={`/news${qs({ id: n.id })}`} className="st" style={{ display: "grid", gridTemplateColumns: "36px minmax(0, 1fr)", gap: 10, padding: 8, borderBottom: "1px solid var(--rule)" }}>
                <span className="m amb" style={{ fontWeight: 600, fontSize: 15 }}>
                  {impact100(n) ?? "—"}
                </span>
                <span style={{ minWidth: 0 }}>
                  <span className="m trunc" style={{ fontSize: 11, display: "block" }}>
                    <span className="amb">{tick}</span>
                    <span className="dim">
                      {" "}
                      · {srcShort(n)} · {storyTime(n.created_at, now)}
                      {t ? " · " : ""}
                    </span>
                    {t ? <span className={t.cls}>{t.tone}</span> : null}
                  </span>
                  <span style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.3 }}>{n.title}</span>
                </span>
              </Link>
            );
          })
        )}
      </div>
    </Pane>
  );
}
