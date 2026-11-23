"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { qs, useApi, type ReturnsResponse, type SecuritiesPage, type SecuritySort, type Sectors } from "@/lib/api";
import { big, cls, fixed, num, pct } from "@/lib/format";
import { CROSS_ASSET, SECTOR_ETFS, shortSector } from "@/lib/sectors";
import { Empty, heat, Pane, PaneError, SkRows, Tabs, Toolbar } from "@/components/term";

const PAGE_SIZE = 50;
const SORTS = ["ticker", "name", "price", "pct_change", "market_cap"] as const satisfies readonly SecuritySort[];
const DEFAULT_SORT: SecuritySort = "pct_change";
type Order = "asc" | "desc";
type Param = "scope" | "q" | "sector" | "sort" | "order" | "page";

const isSort = (v: string | null): v is SecuritySort => SORTS.includes(v as SecuritySort);
const firstOrder = (key: SecuritySort): Order => (key === "ticker" || key === "name" ? "asc" : "desc");

const PERIODS = [
  { value: "1D", label: "1D" },
  { value: "5D", label: "5D" },
  { value: "1M", label: "1M" },
  { value: "YTD", label: "YTD" },
] as const;
type Period = (typeof PERIODS)[number]["value"];

function useQuotes(tickers: readonly string[]) {
  const res = useApi<SecuritiesPage>(`/api/hub/securities${qs({ scope: "all", tickers: tickers.join(","), limit: 100 })}`);
  return { ...res, map: new Map((res.data?.items ?? []).map((r) => [r.ticker, r])) };
}

export function MarketsSkeleton() {
  return (
    <div className="grid-term g-mkts">
      <Pane title="Cross-asset">
        <SkRows rows={8} />
      </Pane>
      <Pane title="Sector map · S&P 500">
        <SkRows rows={6} h={50} />
      </Pane>
      <Pane title="Movers · core">
        <SkRows rows={8} />
      </Pane>
      <Pane title="Screener" style={{ gridColumn: "span 3" }}>
        <SkRows rows={10} />
      </Pane>
    </div>
  );
}

export function MarketsView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const sector = params.get("sector") ?? "";
  const update = (changes: Partial<Record<Param, string>>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (!("page" in changes)) next.delete("page");
    const s = next.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  };

  return (
    <div className="grid-term g-mkts">
      <CrossAsset />
      <SectorMap selected={sector} onPick={(g) => update({ sector: g === sector ? "" : g })} />
      <Movers />
      <Screener params={params} update={update} />
    </div>
  );
}

// ── cross-asset ───────────────────────────────────────────────────────────
function CrossAsset() {
  const quotes = useQuotes(CROSS_ASSET.map((c) => c.t));
  const rows = CROSS_ASSET.filter((c) => !quotes.data || quotes.map.get(c.t)?.price != null);
  return (
    <Pane title="Cross-asset" right="DAY">
      <div className="body">
        {quotes.error && !quotes.data ? (
          <PaneError error={quotes.error} onRetry={() => quotes.mutate()} />
        ) : !quotes.data ? (
          <SkRows rows={8} />
        ) : (
          rows.map((c) => {
            const q = quotes.map.get(c.t);
            return (
              <Link key={c.t} href={`/ticker/${c.t}`} className="r m" style={{ fontSize: 13 }}>
                <span style={{ width: 180, flexShrink: 0 }} className="trunc">
                  <span className="amb">{c.t}</span> <span className="dim" style={{ fontFamily: "var(--font-archivo)" }}>{c.n}</span>
                </span>
                <span style={{ flex: 1, textAlign: "right" }}>{fixed(q?.price)}</span>
                <span className={cls(q?.pct_change)} style={{ width: 68, textAlign: "right" }}>
                  {pct(q?.pct_change)}
                </span>
              </Link>
            );
          })
        )}
      </div>
    </Pane>
  );
}

// ── sector map ────────────────────────────────────────────────────────────
function SectorMap({ selected, onPick }: { selected: string; onPick: (gics: string) => void }) {
  const [period, setPeriod] = useState<Period>("1D");
  const etfs = SECTOR_ETFS.map((s) => s.etf);
  const quotes = useQuotes(etfs);
  const rets = useApi<ReturnsResponse>(period === "1D" ? null : `/api/hub/returns${qs({ tickers: etfs.join(",") })}`);
  const counts = useApi<Sectors>("/api/hub/sectors");
  const count = (g: string) => counts.data?.sectors.find((s) => s.sector === g)?.count;
  const val = (etf: string) => {
    if (period === "1D") return quotes.map.get(etf)?.pct_change;
    const r = rets.data?.items[etf];
    return period === "5D" ? r?.r5d : period === "1M" ? r?.r1m : r?.rytd;
  };
  const ready = period === "1D" ? Boolean(quotes.data) : Boolean(rets.data);
  const scale = period === "1D" ? 2 : period === "5D" ? 4 : 8;
  return (
    <Pane title="Sector map · S&P 500" right={period}>
      <Toolbar>
        <Tabs label="Period" value={period} onChange={setPeriod} options={PERIODS} />
        <span className="m dim" style={{ marginLeft: "auto", fontSize: 11 }}>
          CLICK TO FILTER SCREENER
        </span>
      </Toolbar>
      <div className="body" style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gridAutoRows: "minmax(60px, 1fr)", gap: 2, padding: 2, background: "var(--rule)" }}>
        {SECTOR_ETFS.map((s) => {
          const v = ready ? val(s.etf) : null;
          const on = selected === s.gics;
          return (
            <button
              key={s.etf}
              type="button"
              aria-pressed={on}
              onClick={() => onPick(s.gics)}
              style={{
                ...heat(v, scale),
                border: 0,
                outline: on ? "2px solid var(--amb)" : undefined,
                outlineOffset: -2,
                color: "var(--ink)",
                textAlign: "left",
                padding: 8,
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                cursor: "pointer",
                font: "inherit",
              }}
            >
              <span style={{ fontSize: 13, fontWeight: 500 }}>{s.name}</span>
              <span className="m" style={{ fontWeight: 600, fontSize: 15 }}>
                {ready ? pct(v) : ""}
              </span>
              <span className="m dim" style={{ fontSize: 10 }}>
                {s.etf} · {count(s.gics) ?? "—"} STOCKS
              </span>
            </button>
          );
        })}
      </div>
    </Pane>
  );
}

// ── movers ────────────────────────────────────────────────────────────────
function Movers() {
  const [mv, setMv] = useState<"GAINERS" | "LOSERS">("GAINERS");
  const res = useApi<SecuritiesPage>(`/api/hub/securities${qs({ kind: "stock", sort: "pct_change", order: mv === "GAINERS" ? "desc" : "asc", limit: 15 })}`);
  return (
    <Pane title="Movers · core" right="DAY">
      <Toolbar>
        <Tabs
          label="Movers"
          value={mv}
          onChange={setMv}
          options={[
            { value: "GAINERS", label: "GAINERS" },
            { value: "LOSERS", label: "LOSERS" },
          ]}
        />
      </Toolbar>
      <div className="body">
        {res.error && !res.data ? (
          <PaneError error={res.error} onRetry={() => res.mutate()} />
        ) : !res.data ? (
          <SkRows rows={8} />
        ) : (
          res.data.items.map((x) => (
            <Link key={x.ticker} href={`/ticker/${encodeURIComponent(x.ticker)}`} className="r m" style={{ fontSize: 13 }}>
              <span style={{ fontWeight: 600, width: 52, flexShrink: 0 }}>{x.ticker}</span>
              <span className="dim trunc" style={{ flex: 1, fontFamily: "var(--font-archivo)", fontSize: 12 }}>
                {x.name}
              </span>
              <span className={cls(x.pct_change)} style={{ width: 66, textAlign: "right" }}>
                {pct(x.pct_change)}
              </span>
            </Link>
          ))
        )}
      </div>
    </Pane>
  );
}

// ── screener ──────────────────────────────────────────────────────────────
type Col = { key: string; label: string; sort?: SecuritySort; left?: boolean };
const COLS: Col[] = [
  { key: "ticker", label: "TICKER", sort: "ticker", left: true },
  { key: "name", label: "NAME", sort: "name", left: true },
  { key: "sector", label: "SECTOR", left: true },
  { key: "price", label: "PRICE", sort: "price" },
  { key: "day", label: "DAY", sort: "pct_change" },
  { key: "r5d", label: "5D" },
  { key: "cap", label: "MKT CAP", sort: "market_cap" },
  { key: "pe", label: "P/E" },
  { key: "news", label: "NEWS 7D" },
];

function Screener({ params, update }: { params: URLSearchParams; update: (c: Partial<Record<Param, string>>) => void }) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const box = useRef<HTMLInputElement>(null);
  const scope = params.get("scope") === "all" ? "all" : "core";
  const q = params.get("q") ?? "";
  const sector = params.get("sector") ?? "";
  const rawSort = params.get("sort");
  const sort: SecuritySort = isSort(rawSort) ? rawSort : DEFAULT_SORT;
  const order: Order = params.get("order") === "asc" || params.get("order") === "desc" ? (params.get("order") as Order) : firstOrder(sort);
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);
  const offset = (page - 1) * PAGE_SIZE;

  const list = useApi<SecuritiesPage>(`/api/hub/securities${qs({ scope, q, sector, sort, order, limit: PAGE_SIZE, offset })}`);
  const sectors = useApi<Sectors>("/api/hub/sectors");
  const data = list.data;
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const sectorList = sectors.data?.sectors ?? [];
  const stale = list.isLoading && Boolean(data);

  const onSort = (key: SecuritySort) => {
    const nextOrder = key === sort ? (order === "asc" ? "desc" : "asc") : firstOrder(key);
    const isDefault = key === DEFAULT_SORT && nextOrder === firstOrder(DEFAULT_SORT);
    update({ sort: isDefault ? "" : key, order: nextOrder === firstOrder(key) ? "" : nextOrder });
  };

  return (
    <Pane title="Screener" right={data ? `${total.toLocaleString()} SYMBOLS` : ""} style={{ gridColumn: "span 3" }}>
      <Toolbar>
        <Tabs
          label="Universe"
          value={scope}
          onChange={(v) => update({ scope: v === "core" ? "" : v })}
          options={[
            { value: "core", label: "CORE" },
            { value: "all", label: "ALL LISTED" },
          ]}
        />
        <label htmlFor="scr-q" className="m dim" style={{ fontSize: 11, marginLeft: 8 }}>
          FIND
        </label>
        <input
          id="scr-q"
          ref={box}
          className="fld"
          type="search"
          defaultValue={q}
          maxLength={40}
          placeholder="TICKER OR NAME"
          style={{ width: 160 }}
          onChange={(e) => {
            const v = e.target.value.trim();
            if (timer.current) clearTimeout(timer.current);
            timer.current = setTimeout(() => update({ q: v }), 300);
          }}
        />
        <label htmlFor="scr-sector" className="m dim" style={{ fontSize: 11, marginLeft: 8 }}>
          SECTOR
        </label>
        <select id="scr-sector" className="sel" value={sector} onChange={(e) => update({ sector: e.target.value })}>
          <option value="">All sectors</option>
          {sector && !sectorList.some((s) => s.sector === sector) ? <option value={sector}>{sector}</option> : null}
          {sectorList.map((s) => (
            <option key={s.sector} value={s.sector}>
              {scope === "core" ? `${s.sector} (${s.count})` : s.sector}
            </option>
          ))}
        </select>
        {q || sector ? (
          <button
            type="button"
            className="btn"
            onClick={() => {
              if (timer.current) clearTimeout(timer.current);
              if (box.current) box.current.value = "";
              update({ q: "", sector: "" });
            }}
          >
            CLEAR
          </button>
        ) : null}
        <span className="m dim" style={{ marginLeft: "auto", fontSize: 11 }}>
          CLICK A COLUMN TO SORT
        </span>
      </Toolbar>
      <div className="body">
        {list.error && !data ? (
          <PaneError error={list.error} onRetry={() => list.mutate()} />
        ) : (
          <table className="tbl" style={{ minWidth: 820 }}>
            <caption className="sr-only">Securities sorted by {COLS.find((c) => c.sort === sort)?.label}, {order === "asc" ? "ascending" : "descending"}</caption>
            <thead>
              <tr>
                {COLS.map((c) => {
                  const on = c.sort === sort;
                  return (
                    <th key={c.key} scope="col" className={c.left ? "l" : ""} aria-sort={on ? (order === "asc" ? "ascending" : "descending") : undefined}>
                      {c.sort ? (
                        <button type="button" className={on ? "on" : ""} onClick={() => onSort(c.sort!)}>
                          {c.label}
                          {on ? (order === "asc" ? " ▲" : " ▼") : ""}
                        </button>
                      ) : (
                        c.label
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody style={{ opacity: stale ? 0.5 : 1 }} aria-busy={stale}>
              {!data
                ? Array.from({ length: 10 }, (_, i) => (
                    <tr key={i}>
                      <td colSpan={COLS.length} className="l">
                        <div className="sk" style={{ height: 14, width: `${50 + ((i * 29) % 45)}%` }} />
                      </td>
                    </tr>
                  ))
                : data.items.map((x) => (
                    <tr key={x.ticker} className="lk">
                      <td className="m l" style={{ fontWeight: 600 }}>
                        <Link href={`/ticker/${encodeURIComponent(x.ticker)}`} style={{ color: "var(--amb)" }}>
                          {x.ticker}
                        </Link>
                      </td>
                      <td className="l trunc" style={{ maxWidth: 260 }}>
                        {x.name ?? "—"}
                        {x.type && x.type !== "Common Stock" ? <span className="m dim" style={{ fontSize: 10, marginLeft: 6 }}>{x.type === "ETP" ? "ETF" : x.type.toUpperCase()}</span> : null}
                      </td>
                      <td className="l dim">{shortSector(x.sector)}</td>
                      <td className="m">{fixed(x.price)}</td>
                      <td className={`m ${cls(x.pct_change)}`}>{pct(x.pct_change)}</td>
                      <td className={`m ${cls(x.r5d)}`}>{pct(x.r5d, 1)}</td>
                      <td className="m">{big(x.market_cap)}</td>
                      <td className="m">{num(x.pe, 1)}</td>
                      <td className="m">{x.news_7d || <span className="dim">0</span>}</td>
                    </tr>
                  ))}
            </tbody>
          </table>
        )}
        {data && !data.items.length ? (
          <Empty>
            {total > 0 ? "THIS PAGE IS PAST THE END OF THE LIST." : q || sector ? "NO SECURITIES MATCH. TRY ALL LISTED OR CLEAR THE FILTERS." : "THE UNIVERSE IS EMPTY. RUN `archiver universe-sync`."}
          </Empty>
        ) : null}
      </div>
      {data && total > PAGE_SIZE ? (
        <nav aria-label="Pagination" className="r m" style={{ borderTop: "1px solid var(--rule)", borderBottom: 0, fontSize: 11 }}>
          <span className="dim">
            {Math.min(offset + 1, total).toLocaleString()}–{Math.min(offset + PAGE_SIZE, total).toLocaleString()} OF {total.toLocaleString()}
          </span>
          <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <button type="button" className="btn" disabled={page <= 1} onClick={() => update({ page: page - 1 > 1 ? String(page - 1) : "" })}>
              ‹ PREV
            </button>
            <span>
              PAGE {page} / {pages}
            </span>
            <button type="button" className="btn" disabled={page >= pages} onClick={() => update({ page: String(page + 1) })}>
              NEXT ›
            </button>
          </span>
        </nav>
      ) : null}
    </Pane>
  );
}
