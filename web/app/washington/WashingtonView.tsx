"use client";

import { useState } from "react";
import Link from "next/link";
import { movesLookup, qs, reactionsKey, useApi, type NewsItem, type NewsPage, type ReactionsResponse } from "@/lib/api";
import { cls, pct } from "@/lib/format";
import { ACTION_TYPES, impact100, kindShort, summaryOf, topicShort, WASHINGTON_SOURCES } from "@/lib/news";
import { dayHeading, dayMonth, etDay, etTime, hoursAgo, useNow } from "@/lib/time";
import { Bar, Empty, LineChart, Pane, PaneError, SkRows, Tabs, Toolbar } from "@/components/term";

const WASH = WASHINGTON_SOURCES.join(",");
const RANGES = [
  { value: "1D", label: "1D", hours: 24 },
  { value: "7D", label: "7D", hours: 24 * 7 },
  { value: "30D", label: "30D", hours: 24 * 30 },
] as const;
type Range = (typeof RANGES)[number]["value"];
type TypeKey = (typeof ACTION_TYPES)[number]["key"];

const etfsOf = (items: NewsItem[]) => [...new Set(items.flatMap((i) => i.sectors.map((s) => s.etf).filter((e): e is string => Boolean(e))))];

export function WashingtonView() {
  const now = useNow();
  const [type, setType] = useState<TypeKey>("all");
  const [range, setRange] = useState<Range>("7D");
  const hours = RANGES.find((r) => r.value === range)!.hours;
  const kinds = ACTION_TYPES.find((t) => t.key === type)!.kinds;

  const list = useApi<NewsPage>(
    now !== null ? `/api/statuses${qs({ source: WASH, kind: kinds.join(","), since: hoursAgo(now, hours), limit: 100, with_total: "true" })}` : null,
  );
  const items = list.data?.items ?? [];
  const reactions = useApi<ReactionsResponse>(reactionsKey(items.map((i) => i.created_at), etfsOf(items).slice(0, 30)));
  const move = movesLookup(reactions.data);

  // 30 days of everything, for the side panes.
  const month = useApi<NewsPage>(now !== null ? `/api/statuses${qs({ source: WASH, since: hoursAgo(now, 24 * 30), limit: 200 })}` : null);
  const monthItems = month.data?.items ?? [];
  const weekCut = now !== null ? now - 7 * 86_400_000 : 0;
  const week = monthItems.filter((i) => i.created_at && Date.parse(i.created_at) >= weekCut);

  // Group the list by ET calendar day.
  const days: { day: string; items: NewsItem[] }[] = [];
  for (const it of items) {
    const d = etDay(it.created_at);
    const last = days[days.length - 1];
    if (last && last.day === d) last.items.push(it);
    else days.push({ day: d, items: [it] });
  }

  return (
    <div className="grid-term g-wash">
      <Pane
        title="President Trump · actions & statements"
        right={list.data ? `${list.data.total ?? items.length} ITEMS` : ""}
        style={{ gridRow: "span 2" }}
      >
        <Toolbar>
          <Tabs label="Document type" value={type} onChange={setType} options={ACTION_TYPES.map((t) => ({ value: t.key, label: t.label }))} />
          <span className="m dim" style={{ marginLeft: "auto", fontSize: 11 }}>
            RANGE
          </span>
          <Tabs label="Range" value={range} onChange={setRange} options={RANGES} />
        </Toolbar>
        <div className="body">
          {list.error && !list.data ? (
            <PaneError error={list.error} onRetry={() => list.mutate()} />
          ) : !list.data ? (
            <SkRows rows={8} h={70} />
          ) : !items.length ? (
            <Empty>NOTHING OF THIS TYPE IN THE LAST {range}. TRY A LONGER RANGE.</Empty>
          ) : (
            days.map((d) => (
              <div key={d.day}>
                <div className="m amb" style={{ padding: "5px 8px", fontSize: 11, background: "var(--sel)", borderBottom: "1px solid var(--rule)" }}>
                  {dayHeading(d.day)}
                </div>
                {d.items.map((i) => {
                  const spx = move(i.created_at, "SPY");
                  const imp = impact100(i);
                  return (
                    <Link
                      key={i.id}
                      href={`/news${qs({ id: i.id })}`}
                      className="st"
                      style={{ display: "grid", gridTemplateColumns: "52px minmax(0, 1fr) 150px", gap: 12, padding: "10px 8px", borderBottom: "1px solid var(--rule)" }}
                    >
                      <div className="m dim" style={{ fontSize: 12 }}>
                        {i.source === "whitehouse" ? etTime(i.created_at) : "—"}
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div className="m" style={{ fontSize: 11 }}>
                          <span className="amb">{kindShort(i.kind)}</span>
                          <span className="dim"> · {topicShort(i)}</span>
                        </div>
                        <div style={{ fontWeight: 600, fontSize: 15, lineHeight: 1.3, margin: "3px 0" }}>{i.title}</div>
                        <div className="dim" style={{ fontSize: 13, lineHeight: 1.4, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                          {summaryOf(i)}
                        </div>
                      </div>
                      <div className="m" style={{ fontSize: 12, display: "flex", flexDirection: "column", gap: 3 }}>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="dim">IMPACT</span>
                          <span className="amb" style={{ fontWeight: 600 }}>
                            {imp ?? "—"}
                          </span>
                        </div>
                        <Bar value={imp} />
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="dim">SPY +1D</span>
                          <span className={cls(spx?.d1)}>{pct(spx?.d1)}</span>
                        </div>
                        <div style={{ fontSize: 11, lineHeight: 1.4, display: "flex", flexWrap: "wrap", columnGap: 6 }}>
                          {i.sectors.slice(0, 3).map((s) => {
                            const m = s.etf ? move(i.created_at, s.etf)?.d1 : null;
                            return (
                              <span key={s.key} className={m == null ? "dim" : cls(m)} title={s.etf ? `${s.etf} ${pct(m)}` : undefined}>
                                {m == null ? "" : m >= 0 ? "▲ " : "▼ "}
                                {s.label.split(/[ &]/)[0].toUpperCase()}
                              </span>
                            );
                          })}
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </Pane>

      <Focus items={week} loading={!month.data} />
      <Tone items={week} loading={!month.data} now={now} />
      <SectorHits items={monthItems} loading={!month.data} />
      <FedRegister />
    </div>
  );
}

// ── policy focus ──────────────────────────────────────────────────────────
function Focus({ items, loading }: { items: NewsItem[]; loading: boolean }) {
  const counts = new Map<string, { n: string; c: number }>();
  for (const i of items) for (const t of i.topics) counts.set(t.key, { n: t.label, c: (counts.get(t.key)?.c ?? 0) + 1 });
  const total = [...counts.values()].reduce((a, b) => a + b.c, 0);
  const rows = [...counts.values()].sort((a, b) => b.c - a.c);
  const top = rows.slice(0, 5);
  const other = rows.slice(5).reduce((a, b) => a + b.c, 0);
  if (other) top.push({ n: "Other", c: other });
  const max = Math.max(1, ...top.map((r) => r.c));
  return (
    <Pane title="Policy focus · 7D" right="SHARE">
      <div className="body" style={{ padding: "6px 8px" }}>
        {loading ? (
          <SkRows rows={6} />
        ) : !top.length ? (
          <Empty>NO TOPICS TAGGED THIS WEEK.</Empty>
        ) : (
          top.map((f) => (
            <div key={f.n} style={{ display: "grid", gridTemplateColumns: "120px 1fr 38px", gap: 8, alignItems: "center", padding: "6px 0", fontSize: 13 }}>
              <span className="trunc">{f.n}</span>
              <Bar value={(f.c / max) * 100} />
              <span className="m dim" style={{ textAlign: "right" }}>
                {Math.round((f.c / total) * 100)}%
              </span>
            </div>
          ))
        )}
      </div>
    </Pane>
  );
}

// ── tone ──────────────────────────────────────────────────────────────────
const STANCE: Record<string, number> = { supportive: 1, restrictive: -1, mentioned: 0 };

function Tone({ items, loading, now }: { items: NewsItem[]; loading: boolean; now: number | null }) {
  // FinBERT scores news, not every government document; fall back to the
  // impact model's policy stance when nothing here has a sentiment score.
  const useSentiment = items.some((i) => i.sentiment);
  const value = (i: NewsItem) => (useSentiment ? (i.sentiment?.compound ?? null) : i.impact?.stance ? (STANCE[i.impact.stance] ?? 0) : null);
  const days: string[] = [];
  if (now !== null) for (let k = 6; k >= 0; k--) days.push(etDay(new Date(now - k * 86_400_000).toISOString()));
  const byDay = days.map((d) => {
    const vals = items.filter((i) => etDay(i.created_at) === d).map(value).filter((v): v is number => v !== null);
    const topics = new Map<string, number>();
    for (const i of items) if (etDay(i.created_at) === d) for (const t of i.topics) topics.set(t.label, (topics.get(t.label) ?? 0) + 1);
    const topic = [...topics.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    return { d, avg: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null, topic };
  });
  const scored = byDay.filter((x) => x.avg !== null) as { d: string; avg: number; topic?: string }[];
  const lo = scored.length ? scored.reduce((a, b) => (b.avg < a.avg ? b : a)) : null;
  const hi = scored.length ? scored.reduce((a, b) => (b.avg > a.avg ? b : a)) : null;
  const label = (x: { d: string; topic?: string } | null) => (x ? `${dayHeading(x.d).slice(0, 3)} · ${(x.topic ?? "—").split(/[ &]/)[0].toUpperCase()}` : "—");

  return (
    <Pane title="Market tone · 7D" right={useSentiment ? "AVG SENTIMENT" : "NET STANCE"}>
      <div className="body" style={{ padding: "10px 8px", display: "flex", flexDirection: "column", gap: 8 }}>
        {loading ? (
          <SkRows rows={4} />
        ) : !scored.length ? (
          <Empty>NOTHING SCORED THIS WEEK.</Empty>
        ) : (
          <>
            <div style={{ height: 120 }}>
              <LineChart
                label={`Average ${useSentiment ? "sentiment" : "policy stance"} of the President's actions over seven days`}
                height={120}
                baseline={0}
                series={[{ values: byDay.map((x) => x.avg), color: "var(--amb)" }]}
                markers={lo && lo.avg < 0 ? [{ index: byDay.findIndex((x) => x.d === lo.d), color: "var(--dn)", r: 3.5 }] : []}
              />
            </div>
            <div className="m dim" style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
              <span>{days[0] ? dayHeading(days[0]).slice(0, 3) : ""}</span>
              <span>{useSentiment ? "— NEUTRAL —" : "— BALANCED —"}</span>
              <span>{days[6] ? dayHeading(days[6]).slice(0, 3) : ""}</span>
            </div>
            <div className="r m" style={{ borderTop: "1px solid var(--rule)", fontSize: 12 }}>
              <span className="dim">{useSentiment ? "MOST NEGATIVE" : "MOST RESTRICTIVE"}</span>
              <span>{label(lo)}</span>
            </div>
            <div className="r m" style={{ fontSize: 12 }}>
              <span className="dim">{useSentiment ? "MOST POSITIVE" : "MOST SUPPORTIVE"}</span>
              <span>{label(hi)}</span>
            </div>
          </>
        )}
      </div>
    </Pane>
  );
}

// ── sectors most affected ────────────────────────────────────────────────
function SectorHits({ items, loading }: { items: NewsItem[]; loading: boolean }) {
  const reactions = useApi<ReactionsResponse>(reactionsKey(items.map((i) => i.created_at), etfsOf(items).slice(0, 30)));
  const move = movesLookup(reactions.data);
  const agg = new Map<string, { key: string; n: string; k: number; sum: number; m: number }>();
  for (const i of items) {
    for (const s of i.sectors) {
      const row = agg.get(s.key) ?? { key: s.key, n: s.label, k: 0, sum: 0, m: 0 };
      row.k += 1;
      const d1 = s.etf ? move(i.created_at, s.etf)?.d1 : null;
      if (d1 !== null && d1 !== undefined) {
        row.sum += d1;
        row.m += 1;
      }
      agg.set(s.key, row);
    }
  }
  const rows = [...agg.values()].sort((a, b) => b.k - a.k).slice(0, 8);
  return (
    <Pane title="Sectors most affected · 30D" right="AVG MOVE +1D">
      <div className="body">
        {loading ? (
          <SkRows rows={6} />
        ) : !rows.length ? (
          <Empty>NO SECTORS TAGGED IN THE LAST 30 DAYS.</Empty>
        ) : (
          rows.map((h) => {
            const avg = h.m ? h.sum / h.m : null;
            return (
              <Link key={h.key} href={`/news${qs({ sector: h.key })}`} className="r" style={{ fontSize: 13 }}>
                <span className="trunc">{h.n}</span>
                <span className="m" style={{ whiteSpace: "nowrap" }}>
                  <span className="dim">{h.k} ACT</span>&nbsp;&nbsp;
                  <span className={cls(avg)} style={{ display: "inline-block", width: 60, textAlign: "right" }}>
                    {reactions.data ? pct(avg, 1) : ""}
                  </span>
                </span>
              </Link>
            );
          })
        )}
      </div>
    </Pane>
  );
}

// ── federal register ──────────────────────────────────────────────────────
function FedRegister() {
  const res = useApi<NewsPage>(`/api/statuses${qs({ source: "federal_register", limit: 10 })}`);
  return (
    <Pane title="Federal Register · latest" right={<Link href={`/news${qs({ src: "fr" })}`}>ALL ›</Link>}>
      <div className="body">
        {res.error && !res.data ? (
          <PaneError error={res.error} onRetry={() => res.mutate()} />
        ) : !res.data ? (
          <SkRows rows={5} />
        ) : !res.data.items.length ? (
          <Empty>NO FEDERAL REGISTER DOCUMENTS ARCHIVED YET.</Empty>
        ) : (
          res.data.items.map((f) => (
            <Link key={f.id} href={`/news${qs({ id: f.id })}`} className="r" style={{ alignItems: "flex-start" }}>
              <span style={{ fontSize: 13, lineHeight: 1.35 }}>
                <span className="m amb" style={{ fontSize: 11 }}>
                  {kindShort(f.kind)}{" "}
                </span>
                {f.title}
              </span>
              <span className="m dim" style={{ fontSize: 11, whiteSpace: "nowrap" }}>
                {dayMonth(f.created_at)}
              </span>
            </Link>
          ))
        )}
      </div>
    </Pane>
  );
}
