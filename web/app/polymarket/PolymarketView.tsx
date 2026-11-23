"use client";

import { useState } from "react";
import Link from "next/link";
import { qs, useApi, type PmDetail, type PmEvent, type PmHeadline, type PmKey, type PmListResponse, type PmStat } from "@/lib/api";
import { big, cls, fixed, pct, sentimentTone, shortDate, signed, timeAgo } from "@/lib/format";
import { Bar, Empty, LineChart, Pane, PaneError, SkRows, Tabs, Toolbar } from "@/components/term";

const SORTS = [
  { value: "volume", label: "VOLUME" },
  { value: "news", label: "MOST COVERED" },
  { value: "movers", label: "MOVERS" },
] as const;
type Sort = (typeof SORTS)[number]["value"];
const REFRESH = { refreshInterval: 300_000 };

/** Polymarket shows whole percents and clamps the tails; so do we. */
function prob(p: number | null | undefined) {
  if (p === null || p === undefined || !Number.isFinite(p)) return "—";
  if (p < 1) return "<1%";
  if (p > 99) return ">99%";
  return `${p < 10 ? p.toFixed(1) : Math.round(p)}%`;
}
/** Probability-point change with one decimal: "+3.5 PTS". */
const ptsFine = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${signed(v, 1)} PTS`);
const toneCls = (v: number | null | undefined) => ({ up: "up", down: "dn", flat: "dim" })[sentimentTone(v)];

function WhyChips({ keys, max = 4 }: { keys: PmKey[]; max?: number }) {
  if (!keys.length) return null;
  return (
    <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 4 }}>
      {keys.slice(0, max).map((k) => (
        <span
          key={`${k.kind}:${k.key}`}
          className={`m ${k.kind === "topic" ? "dim" : "amb"}`}
          title={`Linked on ${k.kind}: ${k.label}`}
          style={{ fontSize: 10, border: "1px solid var(--rule)", padding: "0 4px", whiteSpace: "nowrap" }}
        >
          {k.label.toUpperCase()}
        </span>
      ))}
    </span>
  );
}

// ── page ──────────────────────────────────────────────────────────────────
export function PolymarketView() {
  const [theme, setTheme] = useState("all");
  const [sort, setSort] = useState<Sort>("volume");
  const [sel, setSel] = useState<{ event: string; market?: string } | null>(null);

  const list = useApi<PmListResponse>(`/api/hub/polymarket${qs({ theme, sort, limit: 150 })}`, REFRESH);
  const items = list.data?.items ?? [];
  const eventId = sel?.event ?? items[0]?.id ?? null;
  const detail = useApi<PmDetail>(eventId ? `/api/hub/polymarket/${eventId}${qs({ market: sel?.market })}` : null, REFRESH);
  const d = detail.data && detail.data.event.id === eventId ? detail.data : undefined;

  const themeOptions = [
    { value: "all", label: `ALL ${list.data?.total ?? ""}`.trim() },
    ...(list.data?.themes ?? []).map((t) => ({ value: t.key, label: `${t.label} ${t.count ?? ""}`.trim() })),
  ];

  return (
    <div className="grid-term g-poly">
      <Pane
        title="Prediction markets"
        right={list.data?.fetched_at ? `POLYMARKET · ${timeAgo(list.data.fetched_at).toUpperCase()}` : "POLYMARKET"}
        style={{ gridRow: "span 2" }}
      >
        <Toolbar>
          <Tabs
            label="Theme"
            value={theme}
            options={themeOptions}
            onChange={(v) => {
              setTheme(v);
              setSel(null);
            }}
          />
        </Toolbar>
        <Toolbar>
          <span className="m dim" style={{ fontSize: 11 }}>
            SORT
          </span>
          <Tabs label="Sort" value={sort} options={SORTS} onChange={setSort} />
        </Toolbar>
        <div className="body">
          {list.error && !list.data ? (
            <PaneError error={list.error} onRetry={() => list.mutate()} />
          ) : !list.data ? (
            <SkRows rows={9} h={74} />
          ) : !items.length ? (
            <Empty>{list.data.error ? "POLYMARKET IS UNREACHABLE RIGHT NOW. TRY AGAIN IN A FEW MINUTES." : "NO OPEN MARKETS IN THIS THEME."}</Empty>
          ) : (
            items.map((ev) => <MarketRow key={ev.id} ev={ev} on={ev.id === eventId} onPick={() => setSel({ event: ev.id })} />)
          )}
        </div>
      </Pane>

      <OddsPane
        d={d}
        loading={!!eventId && !d && !detail.error}
        error={detail.error}
        retry={() => detail.mutate()}
        onOutcome={(market) => eventId && setSel({ event: eventId, market })}
      />
      <MovesPane d={d} loading={!!eventId && !d && !detail.error} />
      <CoveragePane d={d} loading={!!eventId && !d && !detail.error} />
    </div>
  );
}

// ── list ──────────────────────────────────────────────────────────────────
function MarketRow({ ev, on, onPick }: { ev: PmEvent; on: boolean; onPick: () => void }) {
  const lead = ev.lead;
  const c = ev.coverage;
  return (
    <button type="button" className={on ? "item on" : "item"} onClick={onPick} aria-pressed={on} style={{ gridTemplateColumns: "minmax(0, 1fr) 76px", gap: 8 }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 14, lineHeight: 1.3 }}>{ev.title}</div>
        <div className="m dim" style={{ fontSize: 11, marginTop: 3 }}>
          {ev.outcome_count > 1 ? <span className="amb">{lead.label.toUpperCase()} · </span> : null}
          VOL 24H ${big(ev.volume_24h)}
        </div>
        <div className="m" style={{ fontSize: 11, marginTop: 4, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {c && c.count_30d ? (
            <>
              <span>
                {c.count_7d} {c.count_7d === 1 ? "STORY" : "STORIES"} 7D
                <span className="dim"> · {c.count_30d} 30D</span>
              </span>
              {c.avg_sentiment_7d !== null ? <span className={toneCls(c.avg_sentiment_7d)}>TONE {signed(c.avg_sentiment_7d)}</span> : null}
              <WhyChips keys={ev.keys} max={3} />
            </>
          ) : (
            <span className="dim">NO LINKED COVERAGE</span>
          )}
        </div>
      </div>
      <div className="m" style={{ textAlign: "right" }}>
        <div style={{ fontSize: 18, fontWeight: 600 }}>{prob(lead.probability)}</div>
        <div className={cls(lead.change_1d)} style={{ fontSize: 11 }}>
          {ptsFine(lead.change_1d)}
        </div>
        <Bar value={lead.probability} style={{ marginTop: 4 }} />
      </div>
    </button>
  );
}

// ── odds vs coverage ──────────────────────────────────────────────────────
function OddsPane({ d, loading, error, retry, onOutcome }: { d?: PmDetail; loading: boolean; error: unknown; retry: () => void; onOutcome: (id: string) => void }) {
  const title = d ? d.event.title : "Odds vs coverage";
  return (
    <Pane
      title={title}
      right={
        d?.event.url ? (
          <a href={d.event.url} target="_blank" rel="noopener noreferrer">
            POLYMARKET ↗
          </a>
        ) : (
          "30D"
        )
      }
      style={{ gridColumn: "2 / 4" }}
    >
      {error && !d ? (
        <PaneError error={error} onRetry={retry} />
      ) : !d ? (
        loading ? <SkRows rows={6} h={40} /> : <Empty>PICK A MARKET ON THE LEFT.</Empty>
      ) : (
        <div className="body" style={{ padding: 8, display: "flex", flexDirection: "column", gap: 8 }}>
          {d.event.outcomes.length > 1 ? (
            <Toolbar>
              <label htmlFor="pm-outcome" className="m dim" style={{ fontSize: 11 }}>
                OUTCOME
              </label>
              <select id="pm-outcome" className="sel" value={d.outcome.id} onChange={(e) => onOutcome(e.target.value)}>
                {d.event.outcomes.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label} · {prob(o.probability)}
                  </option>
                ))}
              </select>
            </Toolbar>
          ) : null}
          <div className="m" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(96px, 1fr))", gap: 8 }}>
            <Kpi label="YES" value={prob(d.outcome.probability)} big />
            <Kpi label="1D" value={ptsFine(d.outcome.change_1d)} cls={cls(d.outcome.change_1d)} />
            <Kpi label="1W" value={ptsFine(d.outcome.change_1w)} cls={cls(d.outcome.change_1w)} />
            <Kpi label="VOL 24H" value={`$${big(d.outcome.volume_24h)}`} />
            <Kpi label="RESOLVES" value={d.outcome.end_date ? shortDate(d.outcome.end_date.slice(0, 10)).toUpperCase() : "—"} />
          </div>
          {d.outcome.question && d.outcome.question !== d.event.title ? (
            <div className="dim" style={{ fontSize: 12 }}>
              {d.outcome.question}
            </div>
          ) : null}
          <Chart d={d} />
          <Stats d={d} />
          <div className="dim" style={{ fontSize: 11, lineHeight: 1.45 }}>
            Odds are Polymarket&apos;s YES price, read live. Coverage is every archived headline that names the same people, companies, countries, agencies or
            places as this market (the chips show which); tone is FinBERT on news headlines only, as government documents are not scored. These are descriptive
            co-movements over {d.window_days} days: they do not show that coverage moved the odds, or the reverse.
          </div>
        </div>
      )}
    </Pane>
  );
}

function Kpi({ label, value, cls: c = "", big: isBig = false }: { label: string; value: string; cls?: string; big?: boolean }) {
  return (
    <div>
      <div className="dim" style={{ fontSize: 10 }}>
        {label}
      </div>
      <div className={c} style={{ fontSize: isBig ? 22 : 14, fontWeight: 600, whiteSpace: "nowrap" }}>
        {value}
      </div>
    </div>
  );
}

function Chart({ d }: { d: PmDetail }) {
  const days = d.days;
  const hasPrice = days.some((x) => x.probability !== null);
  const maxNews = Math.max(1, ...days.map((x) => x.news_count));
  const toneColor = (s: number | null) => (s === null ? "var(--dim)" : { up: "var(--up)", down: "var(--dn)", flat: "var(--amb)" }[sentimentTone(s)]);
  // Carry the last close across days with no trade so the line stays honest
  // about what the market last said, rather than dropping to a gap.
  const line = days.reduce<(number | null)[]>((acc, x) => [...acc, x.probability ?? acc[acc.length - 1] ?? null], []);
  const priced = line.filter((v): v is number => v !== null);
  return (
    <div>
      {d.history_error ? <div className="m dn" style={{ fontSize: 11 }}>{d.history_error.toUpperCase()}</div> : null}
      {priced.length ? (
        <div className="m dim" style={{ fontSize: 10, display: "flex", gap: 12 }}>
          <span>
            {d.window_days}D HIGH <span className="up">{prob(Math.max(...priced))}</span>
          </span>
          <span>
            LOW <span className="dn">{prob(Math.min(...priced))}</span>
          </span>
          <span>
            START <span style={{ color: "var(--ink)" }}>{prob(priced[0])}</span>
          </span>
          <span className="amb">— DAILY CLOSE, ET</span>
        </div>
      ) : null}
      <div style={{ height: 150 }}>
        {hasPrice ? (
          <LineChart
            label={`Daily closing probability of ${d.outcome.label} over ${d.window_days} days, with days of linked coverage marked`}
            height={150}
            series={[{ values: line, color: "var(--amb)" }]}
            markers={days
              .map((x, i) => ({ x, i }))
              .filter(({ x, i }) => x.news_count > 0 && line[i] !== null)
              .map(({ x, i }) => ({
                index: i,
                color: toneColor(x.sentiment),
                r: 2.5 + (x.news_count / maxNews) * 3.5,
                title: `${x.date}: ${x.news_count} linked ${x.news_count === 1 ? "story" : "stories"}${x.sentiment !== null ? `, tone ${signed(x.sentiment)}` : ""}${x.change !== null ? `, odds ${ptsFine(x.change)}` : ""}`,
              }))}
          />
        ) : (
          <Empty>NO PRICE HISTORY FOR THIS OUTCOME YET.</Empty>
        )}
      </div>
      {/* Linked stories per day, coloured by their average tone. */}
      <div
        role="img"
        aria-label={`Linked stories per day: ${days.map((x) => `${x.date} ${x.news_count}`).join(", ")}`}
        style={{ display: "grid", gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))`, gap: 1, height: 34, alignItems: "end", marginTop: 4 }}
      >
        {days.map((x) => (
          <div
            key={x.date}
            title={`${x.date}: ${x.news_count} linked stories${x.sentiment !== null ? `, tone ${signed(x.sentiment)}` : ""}`}
            style={{ height: `${x.news_count ? Math.max(8, (x.news_count / maxNews) * 100) : 0}%`, background: toneColor(x.sentiment), opacity: 0.85 }}
          />
        ))}
      </div>
      <div className="m dim" style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginTop: 2 }}>
        <span>{shortDate(days[0].date).toUpperCase()}</span>
        <span>
          ● STORIES / DAY · <span className="up">POS</span> <span className="amb">NEU</span> <span className="dn">NEG</span> TONE
        </span>
        <span>TODAY</span>
      </div>
    </div>
  );
}

const STRENGTH: Record<PmStat["strength"], string> = {
  none: "NO RELATIONSHIP",
  weak: "WEAK",
  moderate: "MODERATE",
  strong: "STRONG",
  insufficient: "NOT ENOUGH DATA",
};

function StatCell({ title, s, minDays, explain }: { title: string; s: PmStat; minDays: number; explain: (r: number) => string }) {
  return (
    <div style={{ borderTop: "1px solid var(--rule)", paddingTop: 6 }}>
      <div className="m dim" style={{ fontSize: 10 }}>
        {title}
      </div>
      <div className="m" style={{ fontSize: 15, fontWeight: 600 }}>
        {s.r === null ? "—" : `r = ${signed(s.r)}`} <span className={s.strength === "insufficient" || s.strength === "none" ? "dim" : "amb"} style={{ fontSize: 11 }}>{STRENGTH[s.strength]}</span>
      </div>
      <div className="dim" style={{ fontSize: 11, lineHeight: 1.4 }}>
        {s.r === null ? `Needs at least ${minDays} days with data; has ${s.n}.` : `${explain(s.r)} Over ${s.n} days.`}
      </div>
    </div>
  );
}

function Stats({ d }: { d: PmDetail }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
      <StatCell
        title="ODDS CHANGE vs COVERAGE TONE"
        s={d.stats.co_movement}
        minDays={d.stats.min_days}
        explain={(r) => (Math.abs(r) < 0.2 ? "Daily odds moves and the tone of that day's coverage show no consistent relationship." : r > 0 ? "Odds of YES tended to rise on days coverage read more positive." : "Odds of YES tended to rise on days coverage read more negative.")}
      />
      <StatCell
        title="SIZE OF MOVE vs NUMBER OF STORIES"
        s={d.stats.attention}
        minDays={d.stats.min_days}
        explain={(r) => (Math.abs(r) < 0.2 ? "Big odds moves did not coincide with heavier coverage." : r > 0 ? "The odds moved most on the days with the most linked coverage." : "The odds moved most on quieter news days.")}
      />
    </div>
  );
}

// ── what moved it ─────────────────────────────────────────────────────────
function MovesPane({ d, loading }: { d?: PmDetail; loading: boolean }) {
  return (
    <Pane title="Big moves · what ran that day" right={d ? `≥3 PTS · ${d.window_days}D` : ""} style={{ gridColumn: 2, gridRow: 2 }}>
      <div className="body">
        {!d ? (
          loading ? <SkRows rows={5} h={60} /> : <Empty>—</Empty>
        ) : !d.big_moves.length ? (
          <Empty>THE ODDS HAVE NOT MOVED 3 POINTS OR MORE IN A DAY OVER THE LAST {d.window_days} DAYS.</Empty>
        ) : (
          d.big_moves.map((m) => (
            <div key={m.date} style={{ borderBottom: "1px solid var(--rule)" }}>
              <div className="m" style={{ display: "flex", justifyContent: "space-between", padding: "6px 8px", background: "var(--sel)", fontSize: 12 }}>
                <span className="amb">{shortDate(m.date).toUpperCase()}</span>
                <span>
                  <span className={cls(m.change)} style={{ fontWeight: 600 }}>
                    {ptsFine(m.change)}
                  </span>
                  <span className="dim"> → {prob(m.probability)}</span>
                </span>
              </div>
              {m.headlines.length ? (
                <>
                  {m.headlines.map((h) => (
                    <HeadlineRow key={h.id} h={h} compact />
                  ))}
                  {m.news_count > m.headlines.length ? (
                    <div className="m dim" style={{ fontSize: 11, padding: "4px 8px" }}>
                      +{m.news_count - m.headlines.length} MORE LINKED THAT DAY
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="m dim" style={{ fontSize: 11, padding: "6px 8px" }}>
                  NO LINKED COVERAGE IN THE ARCHIVE THAT DAY.
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </Pane>
  );
}

// ── linked coverage ───────────────────────────────────────────────────────
function CoveragePane({ d, loading }: { d?: PmDetail; loading: boolean }) {
  return (
    <Pane title="Linked coverage" right={d ? `${d.headline_total} IN ${d.window_days}D` : ""} style={{ gridColumn: 3, gridRow: 2 }}>
      <div className="body">
        {!d ? (
          loading ? <SkRows rows={6} h={56} /> : <Empty>—</Empty>
        ) : (
          <>
            {d.stocks.length ? (
              <div style={{ borderBottom: "1px solid var(--rule)" }}>
                <div className="m dim" style={{ fontSize: 10, padding: "6px 8px 2px" }}>
                  STOCKS NAMED · TODAY
                </div>
                {d.stocks.map((s) => (
                  <Link key={s.ticker} href={`/ticker/${encodeURIComponent(s.ticker)}`} className="r m" style={{ fontSize: 12 }}>
                    <span>
                      <span className="amb">{s.ticker}</span> <span className="dim">{s.mentions ? `· ${s.mentions} ${s.mentions === 1 ? "STORY" : "STORIES"}` : "· IN MARKET"}</span>
                    </span>
                    <span className={cls(s.pct_change)}>{pct(s.pct_change)}</span>
                  </Link>
                ))}
              </div>
            ) : null}
            {d.headlines.length ? (
              d.headlines.map((h) => <HeadlineRow key={h.id} h={h} />)
            ) : (
              <Empty>
                NOTHING IN THE ARCHIVE NAMES {d.event.keys.length ? d.event.keys.map((k) => k.label.toUpperCase()).join(", ") : "WHAT THIS MARKET IS ABOUT"} IN THE LAST {d.window_days} DAYS.
              </Empty>
            )}
            {d.headline_total > d.headlines.length ? (
              <div className="m dim" style={{ fontSize: 11, padding: 8 }}>
                SHOWING THE NEWEST {d.headlines.length} OF {d.headline_total}.
              </div>
            ) : null}
          </>
        )}
      </div>
    </Pane>
  );
}

const SRC: Record<string, string> = { whitehouse: "WHITE HOUSE", presidential_documents: "PRES. DOCS", federal_register: "FED. REGISTER", market_news: "COMPANY NEWS" };

function HeadlineRow({ h, compact: dense = false }: { h: PmHeadline; compact?: boolean }) {
  return (
    <Link href={`/news${qs({ id: h.id })}`} className="st" style={{ display: "block", padding: dense ? "6px 8px" : "8px", borderBottom: "1px solid var(--rule)" }}>
      <div className="m dim" style={{ fontSize: 10, display: "flex", justifyContent: "space-between", gap: 8 }}>
        <span className="trunc">
          {(h.publisher || SRC[h.source] || h.source).toUpperCase()} · {timeAgo(h.created_at).toUpperCase()}
        </span>
        <span className={h.sentiment === null ? "dim" : toneCls(h.sentiment)} title={h.sentiment === null ? "Not scored (government documents are not run through FinBERT)" : "FinBERT tone of the headline, −1 to +1"}>
          {h.sentiment === null ? "—" : fixed(h.sentiment)}
        </span>
      </div>
      <div
        title={h.title}
        style={{ fontSize: dense ? 13 : 14, lineHeight: 1.3, margin: "3px 0", display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}
      >
        {h.title}
      </div>
      <WhyChips keys={h.why} />
    </Link>
  );
}

export function PolymarketSkeleton() {
  return (
    <div className="grid-term g-poly">
      <Pane title="Prediction markets" style={{ gridRow: "span 2" }}>
        <SkRows rows={9} h={74} />
      </Pane>
      <Pane title="Odds vs coverage" style={{ gridColumn: "2 / 4" }}>
        <SkRows rows={6} h={40} />
      </Pane>
      <Pane title="Big moves · what ran that day" style={{ gridColumn: 2, gridRow: 2 }}>
        <SkRows rows={5} h={60} />
      </Pane>
      <Pane title="Linked coverage" style={{ gridColumn: 3, gridRow: 2 }}>
        <SkRows rows={6} h={56} />
      </Pane>
    </div>
  );
}
