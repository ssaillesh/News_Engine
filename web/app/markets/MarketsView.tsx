"use client";

import { useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { qs, useApi, type SecuritiesPage, type SecuritySort, type Sectors } from "@/lib/api";
import { compact, dateTime, money } from "@/lib/format";
import { buttonCls, Card, Change, Empty, ErrorBox, inputCls, Segmented, Skeleton } from "@/components/ui";

const PAGE_SIZE = 50;
const SORTS = ["ticker", "name", "price", "pct_change", "market_cap"] as const satisfies readonly SecuritySort[];
const DEFAULT_SORT: SecuritySort = "market_cap";
type Order = "asc" | "desc";
type Param = "scope" | "q" | "sector" | "sort" | "order" | "page";

type Column = {
  key: SecuritySort | "sector";
  label: string;
  numeric?: boolean;
  sortable: boolean;
  className?: string;
};

// The API sorts by every column except sector (it filters by it instead).
const COLUMNS: Column[] = [
  { key: "ticker", label: "Ticker", sortable: true, className: "w-28" },
  { key: "name", label: "Name", sortable: true },
  { key: "sector", label: "Sector", sortable: false, className: "hidden md:table-cell" },
  { key: "price", label: "Price", numeric: true, sortable: true },
  { key: "pct_change", label: "% Change", numeric: true, sortable: true },
  { key: "market_cap", label: "Market cap", numeric: true, sortable: true },
];

const isSort = (v: string | null): v is SecuritySort => SORTS.includes(v as SecuritySort);
// First click on a text column sorts A→Z; on a number column, largest first.
const firstOrder = (key: SecuritySort): Order => (key === "ticker" || key === "name" ? "asc" : "desc");

const selectCls = `${inputCls} w-auto min-w-0 pr-7`;

function SortIcon({ dir }: { dir: Order | null }) {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden className={dir ? "text-accent" : "text-faint"}>
      <path d="M2 4 L5 1 L8 4" fill="none" stroke="currentColor" strokeWidth="1.4" opacity={dir === "desc" ? 0.3 : 1} />
      <path d="M2 6 L5 9 L8 6" fill="none" stroke="currentColor" strokeWidth="1.4" opacity={dir === "asc" ? 0.3 : 1} />
    </svg>
  );
}

function Header({
  sort,
  order,
  onSort,
}: {
  sort: SecuritySort;
  order: Order;
  onSort: (key: SecuritySort) => void;
}) {
  return (
    <thead className="border-b border-border text-xs text-muted">
      <tr>
        {COLUMNS.map((c) => {
          const active = c.sortable && c.key === sort;
          return (
            <th
              key={c.key}
              scope="col"
              aria-sort={active ? (order === "asc" ? "ascending" : "descending") : undefined}
              className={`px-4 py-2.5 font-medium ${c.numeric ? "text-right" : "text-left"} ${c.className ?? ""}`}
            >
              {c.sortable ? (
                <button
                  type="button"
                  onClick={() => onSort(c.key as SecuritySort)}
                  className={`inline-flex items-center gap-1.5 hover:text-text ${c.numeric ? "flex-row-reverse" : ""} ${active ? "text-text" : ""}`}
                >
                  {c.label}
                  <SortIcon dir={active ? order : null} />
                </button>
              ) : (
                c.label
              )}
            </th>
          );
        })}
      </tr>
    </thead>
  );
}

function SkeletonRows({ rows = 10 }: { rows?: number }) {
  return (
    <tbody>
      {Array.from({ length: rows }, (_, i) => (
        <tr key={i} className="border-b border-border last:border-0">
          {COLUMNS.map((c) => (
            <td key={c.key} className={`px-4 py-3 ${c.className ?? ""}`}>
              <Skeleton className={`h-4 ${c.numeric ? "ml-auto w-16" : c.key === "name" ? "w-40" : "w-20"}`} />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

export function MarketsSkeleton() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Markets</h1>
        <Skeleton className="mt-2 h-4 w-56" />
      </div>
      <Card className="overflow-hidden">
        <div className="h-[60px] border-b border-border" />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <SkeletonRows />
          </table>
        </div>
      </Card>
    </div>
  );
}

export function MarketsView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchBox = useRef<HTMLInputElement>(null);

  const scope = params.get("scope") === "all" ? "all" : "core";
  const q = params.get("q") ?? "";
  const sector = params.get("sector") ?? "";
  const rawSort = params.get("sort");
  const sort: SecuritySort = isSort(rawSort) ? rawSort : DEFAULT_SORT;
  const order: Order = params.get("order") === "asc" || params.get("order") === "desc" ? (params.get("order") as Order) : firstOrder(sort);
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);

  /** Write params to the URL; any change other than paging returns to page 1. */
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

  const onSort = (key: SecuritySort) => {
    const nextOrder = key === sort ? (order === "asc" ? "desc" : "asc") : firstOrder(key);
    // Keep the URL clean when it matches the default (market cap, largest first).
    const isDefault = key === DEFAULT_SORT && nextOrder === firstOrder(DEFAULT_SORT);
    update({
      sort: isDefault ? "" : key,
      order: nextOrder === firstOrder(key) ? "" : nextOrder,
    });
  };

  const clearFilters = () => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (searchBox.current) searchBox.current.value = "";
    update({ q: "", sector: "" });
  };

  const offset = (page - 1) * PAGE_SIZE;
  const list = useApi<SecuritiesPage>(
    `/api/hub/securities${qs({ scope, q, sector, sort, order, limit: PAGE_SIZE, offset })}`,
  );
  const sectors = useApi<Sectors>("/api/hub/sectors");

  const data = list.data;
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const filtered = Boolean(q || sector);
  const sectorList = sectors.data?.sectors ?? [];
  // Keep a sector from the URL selectable even before (or without) the list.
  const knownSector = !sector || sectorList.some((s) => s.sector === sector);
  // With keepPreviousData the old page stays on screen while the next loads.
  const stale = list.isLoading && Boolean(data);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Markets</h1>
          <p className="mt-1 text-sm text-muted">
            {data
              ? `${total.toLocaleString()} ${scope === "core" ? "core" : "listed"} ${total === 1 ? "security" : "securities"}${filtered ? " match" : ""}`
              : " "}
          </p>
        </div>
        <Segmented
          label="Universe"
          value={scope}
          onChange={(v) => update({ scope: v === "core" ? "" : v })}
          options={[
            { value: "core", label: "Core" },
            { value: "all", label: "All listed" },
          ]}
        />
      </div>

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-end gap-3 border-b border-border px-4 py-3">
          <label className="flex min-w-[12rem] flex-1 flex-col gap-1 text-xs text-muted sm:max-w-xs">
            Search
            <input
              ref={searchBox}
              type="search"
              defaultValue={q}
              placeholder="Ticker or company…"
              maxLength={40}
              className={inputCls}
              onChange={(e) => {
                const v = e.target.value.trim();
                if (searchTimer.current) clearTimeout(searchTimer.current);
                searchTimer.current = setTimeout(() => update({ q: v }), 300);
              }}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            Sector
            <select aria-label="Sector" value={sector} onChange={(e) => update({ sector: e.target.value })} className={selectCls}>
              <option value="">All sectors</option>
              {!knownSector ? <option value={sector}>{sector}</option> : null}
              {sectorList.map((s) => (
                <option key={s.sector} value={s.sector}>
                  {/* Counts are of core symbols, so they only describe the core view. */}
                  {scope === "core" ? `${s.sector} (${s.count})` : s.sector}
                </option>
              ))}
            </select>
          </label>
          {filtered ? (
            <button type="button" onClick={clearFilters} className="pb-2 text-xs font-medium text-accent hover:underline">
              Clear filters
            </button>
          ) : null}
        </div>

        {list.error && !data ? (
          <ErrorBox error={list.error} onRetry={() => list.mutate()} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <caption className="sr-only">
                Securities sorted by {COLUMNS.find((c) => c.key === sort)?.label}, {order === "asc" ? "ascending" : "descending"}
              </caption>
              <Header sort={sort} order={order} onSort={onSort} />
              {!data ? (
                <SkeletonRows />
              ) : (
                <tbody className={`transition-opacity ${stale ? "opacity-50" : ""}`} aria-busy={stale}>
                  {data.items.map((s) => (
                    <tr key={s.ticker} className="relative border-b border-border last:border-0 hover:bg-surface-2">
                      <td className="px-4 py-2.5">
                        {/* Stretched link: the whole row opens the ticker page. */}
                        <Link
                          href={`/ticker/${encodeURIComponent(s.ticker)}`}
                          className="num font-semibold after:absolute after:inset-0 after:content-[''] hover:text-accent focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-accent"
                        >
                          {s.ticker}
                        </Link>
                      </td>
                      <td className="max-w-[22rem] px-4 py-2.5">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="truncate">{s.name ?? "—"}</span>
                          {s.type && s.type !== "Common Stock" ? (
                            <span className="shrink-0 rounded border border-border px-1 py-px text-[10px] font-medium text-muted">{s.type}</span>
                          ) : null}
                        </div>
                      </td>
                      <td className="hidden px-4 py-2.5 text-muted md:table-cell">{s.sector ?? "—"}</td>
                      <td className="num px-4 py-2.5 text-right" title={s.quote_at ? `Quote as of ${dateTime(s.quote_at)}` : "No quote yet"}>
                        {money(s.price)}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <Change value={s.pct_change} />
                      </td>
                      <td className="num px-4 py-2.5 text-right">{compact(s.market_cap, "USD")}</td>
                    </tr>
                  ))}
                </tbody>
              )}
            </table>

            {data && data.items.length === 0 ? (
              total > 0 ? (
                <Empty title="This page is past the end of the list.">
                  <button type="button" onClick={() => update({ page: pages > 1 ? String(pages) : "" })} className="font-medium text-accent hover:underline">
                    Go to page {pages}
                  </button>
                </Empty>
              ) : filtered ? (
                <Empty title="No securities match.">
                  {scope === "core" ? (
                    <>
                      Try{" "}
                      <button type="button" onClick={() => update({ scope: "all" })} className="font-medium text-accent hover:underline">
                        all listed securities
                      </button>{" "}
                      or clear the filters.
                    </>
                  ) : (
                    "Try a different search or sector."
                  )}
                </Empty>
              ) : (
                <Empty title="The universe is empty.">
                  Run <code className="num">archiver universe-sync</code> to load listed securities.
                </Empty>
              )
            ) : null}
          </div>
        )}

        {data && total > PAGE_SIZE ? (
          <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3 text-xs text-muted">
            <span className="num">
              {Math.min(offset + 1, total).toLocaleString()}–{Math.min(offset + PAGE_SIZE, total).toLocaleString()} of {total.toLocaleString()}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => update({ page: page - 1 > 1 ? String(page - 1) : "" })}
                className={buttonCls.secondary}
              >
                Previous
              </button>
              <span className="num px-1">
                Page {page} of {pages}
              </span>
              <button type="button" disabled={page >= pages} onClick={() => update({ page: String(page + 1) })} className={buttonCls.secondary}>
                Next
              </button>
            </div>
          </nav>
        ) : null}
      </Card>
    </div>
  );
}
