"use client";

import { useState } from "react";
import Link from "next/link";
import { movesLookup, qs, reactionsKey, useApi, type NewsItem, type NewsPage, type ReactionsResponse } from "@/lib/api";
import { cls, pct, sentimentTone } from "@/lib/format";
import { ACTION_TYPES, impact100, kindShort, summaryOf, topicShort, WASHINGTON_SOURCES } from "@/lib/news";
import { dayHeading, dayMonth, etDay, etTime, hoursAgo, useNow } from "@/lib/time";
import { Bar, Empty, Pane, PaneError, SkRows, Tabs, Toolbar } from "@/components/term";

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

// ── direction: tailwind / headwind ────────────────────────────────────────
type Dir = 1 | -1 | 0;

/** FinBERT scores news, not government documents, so this usually reads the
 *  impact model's stance: is the action a tailwind or a headwind for the
 *  sectors it names? When items do carry sentiment, that is used instead. */
function direction(items: NewsItem[]) {
  const useSentiment = items.some((i) => i.sentiment);
  const dir = (i: NewsItem): Dir | null => {
    if (useSentiment) {
      if (!i.sentiment) return null;
      const t = sentimentTone(i.sentiment.compound);
      return t === "up" ? 1 : t === "down" ? -1 : 0;
    }
    const st = i.impact?.stance;
    return st === "supportive" ? 1 : st === "restrictive" ? -1 : st ? 0 : null;
  };
  return { useSentiment, up: useSentiment ? "POSITIVE" : "TAILWIND", down: useSentiment ? "NEGATIVE" : "HEADWIND", dir };
}

const KEY_TEXT =
  "Tailwind: exemptions, deregulation, awards, incentives. Headwind: tariffs, bans, probes, sanctions. Judged for the sectors each action names.";

// ── tone ──────────────────────────────────────────────────────────────────
function Tone({ items, loading, now }: { items: NewsItem[]; loading: boolean; now: number | null }) {
  const { useSentiment, up, down, dir } = direction(items);

  const days: string[] = [];
  if (now !== null) for (let k = 6; k >= 0; k--) days.push(etDay(new Date(now - k * 86_400_000).toISOString()));
  const byDay = days.map((d) => {
    const mine = items.filter((i) => etDay(i.created_at) === d);
    const dirs = mine.map(dir).filter((v): v is Dir => v !== null);
    const topics = new Map<string, number>();
    for (const i of mine) for (const t of i.topics) topics.set(t.label, (topics.get(t.label) ?? 0) + 1);
    return {
      d,
      up: dirs.filter((v) => v === 1).length,
      down: dirs.filter((v) => v === -1).length,
      flat: dirs.filter((v) => v === 0).length,
      topic: [...topics.entries()].sort((a, b) => b[1] - a[1])[0]?.[0],
    };
  });
  const totUp = byDay.reduce((a, x) => a + x.up, 0);
  const totDown = byDay.reduce((a, x) => a + x.down, 0);
  const totFlat = byDay.reduce((a, x) => a + x.flat, 0);
  const total = totUp + totDown + totFlat;
  const max = Math.max(1, ...byDay.map((x) => Math.max(x.up, x.down)));
  const verdict =
    totUp + totDown === 0
      ? { text: "NO CLEAR DIRECTION", cls: "dim" }
      : totDown > totUp * 1.25
        ? { text: `LEANING ${down}`, cls: "dn" }
        : totUp > totDown * 1.25
          ? { text: `LEANING ${up}`, cls: "up" }
          : { text: "BALANCED", cls: "dim" };
  const worst = [...byDay].sort((a, b) => b.down - a.down)[0];
  const best = [...byDay].sort((a, b) => b.up - a.up)[0];
  const dayName = (d: string) => dayHeading(d).slice(0, 3);
  const short = (t?: string) => (t ?? "").split(/[ &]/)[0].toUpperCase();

  return (
    <Pane title="Market tone · 7D" right={useSentiment ? "SENTIMENT" : "TAILWIND VS HEADWIND"}>
      <div className="body" style={{ padding: "8px", display: "flex", flexDirection: "column", gap: 8 }}>
        {loading ? (
          <SkRows rows={4} />
        ) : !total ? (
          <Empty>NOTHING SCORED THIS WEEK.</Empty>
        ) : (
          <>
            <div>
              <div className={`m ${verdict.cls}`} style={{ fontSize: 16, fontWeight: 600 }}>
                {verdict.text}
              </div>
              <div className="m" style={{ fontSize: 11, marginTop: 2 }}>
                <span className="up">{totUp} {up.toLowerCase()}</span>
                <span className="dim"> · </span>
                <span className="dn">{totDown} {down.toLowerCase()}</span>
                <span className="dim">
                  {" "}
                  · {totFlat} no clear direction, of {total} actions
                </span>
              </div>
              <div className="dim" style={{ fontSize: 11, lineHeight: 1.4, marginTop: 4 }}>
                {useSentiment
                  ? "Tone of the President's actions as scored by FinBERT: positive or negative wording."
                  : KEY_TEXT}
              </div>
            </div>

            <div
              role="img"
              aria-label={byDay.map((x) => `${dayName(x.d)}: ${x.up} ${up.toLowerCase()}, ${x.down} ${down.toLowerCase()}`).join("; ")}
              style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", gap: 4 }}
            >
              {byDay.map((x) => (
                <div key={x.d} className="m" style={{ display: "flex", flexDirection: "column", alignItems: "center", fontSize: 10 }} title={`${dayName(x.d)}: ${x.up} ${up.toLowerCase()}, ${x.down} ${down.toLowerCase()}, ${x.flat} neutral`}>
                  {/* Each count rides on the end of its own bar. */}
                  <div style={{ height: 54, width: "60%", display: "flex", flexDirection: "column", justifyContent: "flex-end", alignItems: "center" }}>
                    <span className="up">{x.up || ""}</span>
                    <div style={{ width: "100%", height: `${(x.up / max) * 40}px`, background: "var(--up)" }} />
                  </div>
                  <div style={{ height: 1, width: "100%", background: "var(--dim)" }} />
                  <div style={{ height: 54, width: "60%", display: "flex", flexDirection: "column", alignItems: "center" }}>
                    <div style={{ width: "100%", height: `${(x.down / max) * 40}px`, background: "var(--dn)" }} />
                    <span className="dn">{x.down || ""}</span>
                  </div>
                  <span className="dim">{dayName(x.d)}</span>
                </div>
              ))}
            </div>
            <div className="m dim" style={{ display: "flex", justifyContent: "space-between", fontSize: 10 }}>
              <span>
                <span className="up">▲</span> {up.toLowerCase()} actions above the line
              </span>
              <span>
                <span className="dn">▼</span> {down.toLowerCase()} below
              </span>
            </div>

            <div className="r m" style={{ borderTop: "1px solid var(--rule)", fontSize: 12 }}>
              <span className="dim">MOST {down}</span>
              <span>{worst && worst.down ? `${dayName(worst.d)} · ${worst.down} · ${short(worst.topic)}` : "—"}</span>
            </div>
            <div className="r m" style={{ fontSize: 12 }}>
              <span className="dim">MOST {up}</span>
              <span>{best && best.up ? `${dayName(best.d)} · ${best.up} · ${short(best.topic)}` : "—"}</span>
            </div>
          </>
        )}
      </div>
    </Pane>
  );
}

// ── sectors most affected ────────────────────────────────────────────────
type SectorRow = { key: string; n: string; etf: string | null; k: number; up: number; down: number; flat: number; sum: number; m: number };

function SectorHits({ items, loading }: { items: NewsItem[]; loading: boolean }) {
  const reactions = useApi<ReactionsResponse>(reactionsKey(items.map((i) => i.created_at), etfsOf(items).slice(0, 30)));
  const move = movesLookup(reactions.data);
  const { up, down, dir } = direction(items);

  const agg = new Map<string, SectorRow>();
  for (const i of items) {
    const d = dir(i);
    const spy = move(i.created_at, "SPY")?.d1;
    for (const s of i.sectors) {
      const row = agg.get(s.key) ?? { key: s.key, n: s.label, etf: s.etf, k: 0, up: 0, down: 0, flat: 0, sum: 0, m: 0 };
      row.k += 1;
      if (d === 1) row.up += 1;
      else if (d === -1) row.down += 1;
      else row.flat += 1;
      // Excess over the S&P 500 that session, so a market-wide day doesn't
      // read as the action's doing.
      const own = s.etf ? move(i.created_at, s.etf)?.d1 : null;
      if (own != null && spy != null) {
        row.sum += own - spy;
        row.m += 1;
      }
      agg.set(s.key, row);
    }
  }
  const rows = [...agg.values()].sort((a, b) => b.k - a.k).slice(0, 8);
  const max = Math.max(1, ...rows.map((r) => r.k));
  // Rank by the balance, not the raw count, so the most-named sector doesn't
  // top both lists just for being named most.
  const all = [...agg.values()];
  const helped = all.filter((r) => r.up > r.down).sort((a, b) => b.up - b.down - (a.up - a.down) || b.k - a.k)[0];
  const hurt = all
    .filter((r) => r.down > 0 && r.key !== helped?.key)
    .sort((a, b) => b.down - b.up - (a.down - a.up) || b.down / b.k - a.down / a.k || b.down - a.down)[0];
  const name = (r: SectorRow) => r.n.split(/ & | and /)[0];

  return (
    <Pane title="Sectors most affected · 30D" right="GAIN / LOSE">
      <div className="body" style={{ display: "flex", flexDirection: "column" }}>
        {loading ? (
          <SkRows rows={6} />
        ) : !rows.length ? (
          <Empty>NO SECTORS TAGGED IN THE LAST 30 DAYS.</Empty>
        ) : (
          <>
            <div style={{ padding: "8px 8px 6px" }}>
              <div className="m" style={{ fontSize: 12, lineHeight: 1.5 }}>
                <span className="dim">MOST HELPED </span>
                {helped && helped.up ? (
                  <span className="up">
                    {name(helped).toUpperCase()} · {helped.up} {up.toLowerCase()}
                    {helped.up === 1 ? "" : "s"}
                  </span>
                ) : (
                  <span className="dim">—</span>
                )}
                <br />
                <span className="dim">MOST HURT&nbsp;&nbsp; </span>
                {hurt && hurt.down ? (
                  <span className="dn">
                    {name(hurt).toUpperCase()} · {hurt.down} {down.toLowerCase()}
                    {hurt.down === 1 ? "" : "s"}
                  </span>
                ) : (
                  <span className="dim">—</span>
                )}
              </div>
              <div className="dim" style={{ fontSize: 11, lineHeight: 1.4, marginTop: 4 }}>
                Industries the President&apos;s actions named most in the last 30 days, split by whether each action helps or hurts them.
              </div>
            </div>

            <div className="r m dim" style={{ fontSize: 10, padding: "4px 8px" }}>
              <span>SECTOR · ETF</span>
              <span style={{ display: "flex", gap: 10 }}>
                <span>ACTIONS</span>
                <span style={{ width: 58, textAlign: "right" }}>VS S&amp;P</span>
              </span>
            </div>
            {rows.map((h) => {
              const avg = h.m ? h.sum / h.m : null;
              const tip = `${h.n}: ${h.k} actions, ${h.up} ${up.toLowerCase()}, ${h.down} ${down.toLowerCase()}, ${h.flat} no clear direction${
                avg == null
                  ? h.etf
                    ? `. No price data for ${h.etf} on those days.`
                    : ". No sector ETF to measure."
                  : `. On those days ${h.etf} did ${pct(avg, 1)} vs the S&P 500 on average (${h.m} measured).`
              }`;
              return (
                <Link key={h.key} href={`/news${qs({ sector: h.key })}`} className="hov" title={tip} style={{ display: "block", padding: "6px 8px", borderBottom: "1px solid var(--rule)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13 }}>
                    <span className="trunc">
                      {h.n}
                      {h.etf ? <span className="m dim" style={{ fontSize: 11 }}> · {h.etf}</span> : null}
                    </span>
                    <span className="m" style={{ display: "flex", gap: 10, whiteSpace: "nowrap", fontSize: 12 }}>
                      <span>
                        {h.k}
                        {h.up ? <span className="up"> ▲{h.up}</span> : null}
                        {h.down ? <span className="dn"> ▼{h.down}</span> : null}
                      </span>
                      <span className={reactions.data ? cls(avg) : "dim"} style={{ width: 58, textAlign: "right" }}>
                        {reactions.data ? (avg == null ? "—" : pct(avg, 1)) : ""}
                      </span>
                    </span>
                  </div>
                  {/* Bar length = how often the sector was named; colours = the split. */}
                  <div style={{ display: "flex", height: 6, marginTop: 4, width: `${(h.k / max) * 100}%`, background: "var(--rule)" }} aria-hidden>
                    <span style={{ flex: h.up, background: "var(--up)" }} />
                    <span style={{ flex: h.flat, background: "var(--dim)", opacity: 0.45 }} />
                    <span style={{ flex: h.down, background: "var(--dn)" }} />
                  </div>
                </Link>
              );
            })}
            <div className="m dim" style={{ fontSize: 10, lineHeight: 1.5, padding: "6px 8px" }}>
              <span className="up">■</span> {up.toLowerCase()} <span style={{ opacity: 0.6 }}>■</span> no clear direction <span className="dn">■</span> {down.toLowerCase()}
              <br />
              VS S&amp;P: how the sector&apos;s ETF did against the S&amp;P 500 on the days those actions landed, on average. Click a sector for its actions.
            </div>
          </>
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
