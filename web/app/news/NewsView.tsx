"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import useSWRInfinite from "swr/infinite";
import { fetcher, LIVE_MS, movesLookup, qs, reactionsKey, useApi, type NewsItem, type NewsPage, type ReactionsResponse } from "@/lib/api";
import { cls, fixed, pct } from "@/lib/format";
import { useHotkeys } from "@/lib/hotkeys";
import { impact100, sectorWords, SOURCE_FILTERS, srcLong, srcShort, summaryOf, toneOf, topicShort, type SourceFilter } from "@/lib/news";
import { hoursAgo, storyTime, useNow } from "@/lib/time";
import { Bar, Empty, Pane, PaneError, SkRows, Tabs, Toolbar } from "@/components/term";

const PAGE = 50;
const WINDOWS = [
  { value: "1D", label: "1D", hours: 24 },
  { value: "7D", label: "7D", hours: 24 * 7 },
  { value: "30D", label: "30D", hours: 24 * 30 },
  { value: "ALL", label: "ALL", hours: 0 },
] as const;
type Win = (typeof WINDOWS)[number]["value"];

export function NewsSkeleton() {
  return (
    <div className="grid-term g-news">
      <Pane title="All stories · by impact" style={{ gridRow: "span 2" }}>
        <SkRows rows={10} h={56} />
      </Pane>
      <Pane title="Story" style={{ gridColumn: "span 2" }}>
        <SkRows rows={4} />
      </Pane>
      <Pane title="Why this score">
        <SkRows rows={5} />
      </Pane>
      <Pane title="Market reaction">
        <SkRows rows={4} />
      </Pane>
    </div>
  );
}

export function NewsView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const now = useNow();
  const listRef = useRef<HTMLDivElement>(null);

  const src = (SOURCE_FILTERS.some((f) => f.key === params.get("src")) ? params.get("src") : "all") as SourceFilter;
  const win = (WINDOWS.some((w) => w.value === params.get("w")) ? params.get("w") : "1D") as Win;
  const q = params.get("q") ?? "";
  const ticker = params.get("ticker") ?? "";
  const sector = params.get("sector") ?? "";
  const id = params.get("id");
  const sort: "recent" | "impact" = params.get("sort") === "impact" ? "impact" : "recent";

  const set = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    const s = next.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  };

  const hours = WINDOWS.find((w) => w.value === win)!.hours;
  // Searching or filtering by ticker/sector looks across all time unless a window was picked.
  const since = now === null ? null : hours && !(params.get("w") === null && (q || ticker || sector)) ? hoursAgo(now, hours) : "";
  const sources = SOURCE_FILTERS.find((f) => f.key === src)!.sources.join(",");
  const base = since === null ? null : `/api/statuses${qs({ sort, since, source: sources, q, ticker, sector, with_total: "true" })}`;

  const { data, error, size, setSize, isValidating, mutate } = useSWRInfinite<NewsPage>(
    (i, prev) => (!base || (prev && prev.items.length < PAGE) ? null : `${base}&limit=${PAGE}&offset=${i * PAGE}`),
    fetcher,
    { refreshInterval: LIVE_MS, revalidateOnFocus: true, revalidateFirstPage: true },
  );
  const items = data?.flatMap((p) => p.items) ?? [];
  const total = data?.[0]?.total;
  const done = data ? data[data.length - 1].items.length < PAGE : false;

  // The selected story may come from another page and sit outside this list.
  const inList = id ? items.find((i) => i.id === id) : items[0];
  const single = useApi<NewsPage>(id && data && !inList ? `/api/statuses${qs({ id })}` : null);
  const cur: NewsItem | undefined = inList ?? single.data?.items[0];
  const idx = cur ? items.findIndex((i) => i.id === cur.id) : -1;

  const pick = (i: number) => {
    const it = items[i];
    if (!it) return;
    set({ id: it.id });
    listRef.current?.querySelector<HTMLElement>(`[data-id="${CSS.escape(it.id)}"]`)?.scrollIntoView({ block: "nearest" });
  };

  useHotkeys({
    j: () => pick(Math.min(idx + 1, items.length - 1)),
    k: () => pick(Math.max(idx - 1, 0)),
    Enter: () => {
      if (cur?.url) window.open(cur.url, "_blank", "noopener,noreferrer");
    },
  });

  useEffect(() => {
    if (!id || !items.length) return;
    listRef.current?.querySelector<HTMLElement>(`[data-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: "nearest" });
    // Only on first arrival with an id: later picks scroll themselves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Boolean(data)]);

  const chips = [
    q && { k: "q", label: `"${q.toUpperCase()}"` },
    ticker && { k: "ticker", label: ticker.toUpperCase() },
    sector && { k: "sector", label: sector.replace(/_/g, " ").toUpperCase() },
  ].filter(Boolean) as { k: string; label: string }[];

  return (
    <div className="grid-term g-news">
      <Pane
        title={sort === "impact" ? "All stories · by impact" : "All stories · latest first"}
        right={total !== undefined ? `${total.toLocaleString()} · ${win === "ALL" || since === "" ? "ALL TIME" : win}` : ""}
        style={{ gridRow: "span 2" }}
      >
        <Toolbar>
          <Tabs label="Source" value={src} onChange={(v) => set({ src: v === "all" ? null : v, id: null })} options={SOURCE_FILTERS.map((f) => ({ value: f.key, label: f.label }))} />
          <span style={{ marginLeft: "auto" }} />
          <Tabs
            label="Sort"
            value={sort}
            onChange={(v) => set({ sort: v === "impact" ? "impact" : null, id: null })}
            options={[
              { value: "recent", label: "LATEST" },
              { value: "impact", label: "IMPACT" },
            ]}
          />
        </Toolbar>
        <Toolbar>
          <Tabs label="Window" value={win} onChange={(v) => set({ w: v === "1D" ? null : v, id: null })} options={WINDOWS} />
          {chips.map((c) => (
            <button key={c.k} type="button" className="btn on" onClick={() => set({ [c.k]: null, id: null })} aria-label={`Clear filter ${c.label}`}>
              {c.label} ×
            </button>
          ))}
        </Toolbar>
        <div className="body" ref={listRef}>
          {error && !data ? (
            <PaneError error={error} onRetry={() => mutate()} />
          ) : !data ? (
            <SkRows rows={10} h={56} />
          ) : !items.length ? (
            <Empty>NO STORIES MATCH. TRY A LONGER WINDOW OR CLEAR A FILTER.</Empty>
          ) : (
            <>
              {items.map((s) => {
                const t = toneOf(s);
                return (
                  <button key={s.id} data-id={s.id} type="button" className={s.id === cur?.id ? "item on" : "item"} onClick={() => set({ id: s.id })}>
                    <span className="m amb" style={{ fontSize: 17, fontWeight: 600, textAlign: "center" }}>
                      {impact100(s) ?? "—"}
                    </span>
                    <span style={{ minWidth: 0, display: "block" }}>
                      <span className="m trunc" style={{ fontSize: 11, display: "block" }}>
                        <span className="amb">{srcShort(s)}</span>
                        <span className="dim">
                          {" "}
                          {storyTime(s.created_at, now)} · {topicShort(s)}
                          {t ? " · " : ""}
                        </span>
                        {t ? <span className={t.cls}>{t.tone}</span> : null}
                      </span>
                      <span style={{ display: "block", fontWeight: 600, fontSize: 14, lineHeight: 1.3, marginTop: 2 }}>{s.title}</span>
                    </span>
                  </button>
                );
              })}
              <div style={{ padding: 8, textAlign: "center" }}>
                {done ? (
                  <span className="m dim" style={{ fontSize: 11 }}>
                    END OF LIST · {items.length} STORIES
                  </span>
                ) : (
                  <button type="button" className="btn" disabled={isValidating && size > data.length} onClick={() => setSize(size + 1)}>
                    {isValidating && size > data.length ? "LOADING…" : "LOAD MORE"}
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </Pane>

      <Story item={cur} loading={!data || (Boolean(id) && !cur && !single.error)} empty={Boolean(data) && !items.length && !id} now={now} />
      <WhyScore item={cur} />
      <Reaction item={cur} />
    </div>
  );
}

// ── story ─────────────────────────────────────────────────────────────────
function Story({ item, loading, empty, now }: { item: NewsItem | undefined; loading: boolean; empty: boolean; now: number | null }) {
  const t = item ? toneOf(item) : null;
  const imp = item ? impact100(item) : null;
  return (
    <Pane title="Story" right={item ? `${srcShort(item)} · ${storyTime(item.created_at, now)}` : ""} style={{ gridColumn: "span 2" }}>
      <div className="body" style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 12 }}>
        {!item ? (
          loading ? <SkRows rows={4} /> : <Empty>{empty ? "NOTHING TO SHOW." : "STORY NOT FOUND."}</Empty>
        ) : (
          <>
            <div className="m" style={{ fontSize: 12 }}>
              <span className="amb">{srcLong(item)}</span>
              <span className="dim"> · {topicShort(item)}</span>
              {t ? (
                <>
                  <span className="dim"> · </span>
                  <span className={t.cls}>TONE {t.tone}</span>
                </>
              ) : null}
            </div>
            <h1 style={{ margin: 0, fontSize: 26, lineHeight: 1.2, fontWeight: 700 }}>{item.title}</h1>
            <p style={{ margin: 0, fontSize: 15, lineHeight: 1.55, maxWidth: 760, whiteSpace: "pre-line" }}>
              {summaryOf(item).slice(0, 1400)}
              {summaryOf(item).length > 1400 ? "…" : ""}
            </p>
            {item.stocks.length ? (
              <div className="m" style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {item.stocks.map((s) => (
                  <Link key={s.ticker} href={`/ticker/${encodeURIComponent(s.ticker)}`} className="btn" title={s.name}>
                    {s.ticker}
                  </Link>
                ))}
              </div>
            ) : null}
            <div className="m" style={{ display: "flex", flexWrap: "wrap", gap: "6px 24px", fontSize: 12, paddingTop: 10, borderTop: "1px solid var(--rule)" }}>
              <span>
                <span className="dim">IMPACT </span>
                <span className="amb" style={{ fontWeight: 600 }}>
                  {imp !== null ? `${imp}/100` : "—"}
                </span>
                {item.impact ? <span className="dim"> {item.impact.tier.toUpperCase()}</span> : null}
              </span>
              <span>
                <span className="dim">SENTIMENT </span>
                <span className={t?.cls ?? "dim"}>{item.sentiment ? fixed(item.sentiment.compound) : "—"}</span>
              </span>
              {item.impact?.stance ? (
                <span>
                  <span className="dim">STANCE </span>
                  {item.impact.stance.toUpperCase()}
                </span>
              ) : null}
              <span>
                <span className="dim">SECTORS </span>
                {item.sectors.length ? item.sectors.map((s) => s.label.split(/[ &]/)[0].toUpperCase()).join(" · ") : "—"}
              </span>
              {item.url ? (
                <a href={item.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--amb)", marginLeft: "auto" }}>
                  OPEN SOURCE ↗
                </a>
              ) : null}
            </div>
          </>
        )}
      </div>
    </Pane>
  );
}

// ── why this score ────────────────────────────────────────────────────────
function WhyScore({ item }: { item: NewsItem | undefined }) {
  const i = item?.impact;
  const parts = i
    ? [
        { n: "Authority", v: i.authority, why: i.authority_label ?? "How official the source is" },
        {
          n: "Corroboration",
          v: i.corroboration,
          why: i.corroboration === null ? "Not yet reported by other outlets" : "How widely other outlets report it",
        },
        { n: "Topic weight", v: i.topic, why: item!.topics.map((t) => t.label).join(", ") || "No market-moving topic matched" },
        { n: "Actionability", v: i.actionability, why: i.reasons.length ? i.reasons.join(", ") : "Concrete action rather than talk" },
        {
          n: "Market sensitivity",
          v: i.market_sensitivity,
          why: item!.stocks.length || item!.sectors.length ? `Names ${[item!.stocks.length && `${item!.stocks.length} stock(s)`, item!.sectors.length && `${item!.sectors.length} sector(s)`].filter(Boolean).join(" and ")}` : "Names no priced company or sector",
        },
      ]
    : [];
  return (
    <Pane title="Why this score" right="IMPACT PARTS">
      <div className="body" style={{ padding: "6px 8px" }}>
        {!item ? (
          <SkRows rows={5} />
        ) : !i ? (
          <Empty>THIS STORY HAS NOT BEEN SCORED YET.</Empty>
        ) : (
          parts.map((p) => (
            <div key={p.n} style={{ padding: "6px 0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                <span>{p.n}</span>
                <span className="m">{p.v === null ? "—" : fixed(p.v)}</span>
              </div>
              <Bar value={p.v === null ? 0 : p.v * 100} style={{ marginTop: 4 }} />
              <div className="dim" style={{ fontSize: 11, marginTop: 3 }}>
                {p.why}
              </div>
            </div>
          ))
        )}
      </div>
    </Pane>
  );
}

// ── market reaction ───────────────────────────────────────────────────────
function Reaction({ item }: { item: NewsItem | undefined }) {
  const tickers = item
    ? item.stocks.length
      ? item.stocks.slice(0, 8).map((s) => s.ticker)
      : item.sectors.map((s) => s.etf).filter((e): e is string => Boolean(e)).slice(0, 6)
    : [];
  const res = useApi<ReactionsResponse>(item && tickers.length ? reactionsKey([item.created_at], tickers) : null);
  const move = movesLookup(res.data);
  const spy = move(item?.created_at, "SPY");
  const session = res.data?.events[0]?.session;
  return (
    <Pane title="Market reaction" right="VS SPY">
      <div className="r m dim" style={{ fontSize: 11 }}>
        <span style={{ width: 52 }}>TICKER</span>
        <span style={{ flex: 1, textAlign: "right" }}>{session && session === res.data?.live ? "TODAY · LIVE" : "DAY OF"}</span>
        <span style={{ width: 64, textAlign: "right" }}>+5D</span>
        <span style={{ width: 64, textAlign: "right" }}>VS SPY</span>
      </div>
      <div className="body">
        {!item ? (
          <SkRows rows={4} />
        ) : !tickers.length ? (
          <Empty>NO COMPANY OR SECTOR NAMED, SO NOTHING TO MEASURE.</Empty>
        ) : res.error && !res.data ? (
          <PaneError error={res.error} onRetry={() => res.mutate()} />
        ) : !res.data ? (
          <SkRows rows={tickers.length} />
        ) : (
          <>
            {tickers.map((t) => {
              const m = move(item.created_at, t);
              const own = m?.d5 ?? m?.d1;
              const bench = m?.d5 != null ? spy?.d5 : spy?.d1;
              const x = own != null && bench != null ? own - bench : null;
              return (
                <Link key={t} href={`/ticker/${encodeURIComponent(t)}`} className="r m" style={{ fontSize: 13 }}>
                  <span style={{ width: 52, fontWeight: 600 }}>{t}</span>
                  <span className={cls(m?.d1)} style={{ flex: 1, textAlign: "right" }}>
                    {pct(m?.d1)}
                  </span>
                  <span className={cls(m?.d5)} style={{ width: 64, textAlign: "right" }}>
                    {pct(m?.d5)}
                  </span>
                  <span className={cls(x)} style={{ width: 64, textAlign: "right" }}>
                    {pct(x)}
                  </span>
                </Link>
              );
            })}
            <div className="dim" style={{ fontSize: 11, padding: 8, lineHeight: 1.5 }}>
              {session
                ? session === res.data?.live
                  ? `Session ${session}, still trading: day-of is the move so far, live. `
                  : `Session ${session}. `
                : "No trading session since this story yet. "}Excess move = ticker minus SPY over the same window (5 days when
              available).{item.stocks.length ? "" : ` Sector ETFs shown: ${sectorWords(item, 6)}.`}
            </div>
          </>
        )}
      </div>
    </Pane>
  );
}
