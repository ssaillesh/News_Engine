"use client";

import { useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { qs, useApi, type Facet, type Facets } from "@/lib/api";
import { InfiniteNews } from "@/components/News";
import { Card, CardHeader, inputCls, Segmented } from "@/components/ui";

const FILTERS = ["q", "sort", "sentiment", "tier", "ticker", "sector", "source", "stance", "since", "until"] as const;
type Filter = (typeof FILTERS)[number];

const selectCls = `${inputCls} w-auto min-w-0 pr-7`;

function FacetSelect({
  label,
  name,
  value,
  facets,
  onChange,
  format = (f) => f.label ?? f.key,
}: {
  label: string;
  name: Filter;
  value: string;
  facets: Facet[] | undefined;
  onChange: (name: Filter, value: string) => void;
  format?: (f: Facet) => string;
}) {
  const options = facets ?? [];
  // Keep a value from the URL selectable even before facets load.
  const known = !value || options.some((f) => f.key === value);
  return (
    <label className="flex flex-col gap-1 text-xs text-muted">
      {label}
      <select aria-label={label} value={value} onChange={(e) => onChange(name, e.target.value)} className={selectCls}>
        <option value="">All</option>
        {!known ? <option value={value}>{value}</option> : null}
        {options.map((f) => (
          <option key={f.key} value={f.key}>
            {format(f)} ({f.count})
          </option>
        ))}
      </select>
    </label>
  );
}

export function NewsFeed() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const facets = useApi<Facets>("/api/facets");
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchBox = useRef<HTMLInputElement>(null);

  const get = (k: Filter) => params.get(k) ?? "";
  const set = (name: Filter, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(name, value);
    else next.delete(name);
    const s = next.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  };

  const sort = (get("sort") || "recent") as "recent" | "impact";
  const filters = Object.fromEntries(FILTERS.map((k) => [k, get(k)]));
  const base = `/api/statuses${qs({ ...filters, sort })}`;
  const active = FILTERS.filter((k) => k !== "sort" && get(k)).length;
  const f = facets.data;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">News</h1>
          <p className="mt-1 text-sm text-muted">
            {f ? `${f.total.toLocaleString()} stories archived, scored for sentiment and market impact.` : " "}
          </p>
        </div>
        <Segmented
          label="Sort"
          value={sort}
          onChange={(v) => set("sort", v === "recent" ? "" : v)}
          options={[
            { value: "recent", label: "Latest" },
            { value: "impact", label: "Highest impact" },
          ]}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
        <Card className="self-start lg:sticky lg:top-20">
          <CardHeader
            title="Filters"
            right={
              active ? (
                <button
                  onClick={() => {
                    if (searchTimer.current) clearTimeout(searchTimer.current);
                    if (searchBox.current) searchBox.current.value = "";
                    router.replace(sort === "recent" ? pathname : `${pathname}?sort=${sort}`, { scroll: false });
                  }}
                  className="text-xs font-medium text-accent hover:underline">
                  Clear {active}
                </button>
              ) : null
            }
          />
          <div className="space-y-3 p-4">
            <label className="flex flex-col gap-1 text-xs text-muted">
              Search
              <input
                ref={searchBox}
                type="search"
                defaultValue={get("q")}
                placeholder="Headline or text…"
                className={inputCls}
                onChange={(e) => {
                  const v = e.target.value.trim();
                  if (searchTimer.current) clearTimeout(searchTimer.current);
                  searchTimer.current = setTimeout(() => set("q", v), 350);
                }}
              />
            </label>
            <FacetSelect label="Company" name="ticker" value={get("ticker")} facets={f?.companies} onChange={set} format={(x) => `${x.key} · ${x.label ?? ""}`} />
            <FacetSelect label="Sentiment" name="sentiment" value={get("sentiment")} facets={f?.sentiments} onChange={set} format={(x) => x.key[0].toUpperCase() + x.key.slice(1)} />
            <FacetSelect label="Impact tier" name="tier" value={get("tier")} facets={f?.tiers} onChange={set} format={(x) => x.key[0].toUpperCase() + x.key.slice(1)} />
            <FacetSelect label="Sector" name="sector" value={get("sector")} facets={f?.sectors} onChange={set} format={(x) => `${x.label ?? x.key}${x.etf ? ` · ${x.etf}` : ""}`} />
            <FacetSelect label="Policy stance" name="stance" value={get("stance")} facets={f?.stances} onChange={set} format={(x) => x.key[0].toUpperCase() + x.key.slice(1)} />
            <FacetSelect label="Source" name="source" value={get("source")} facets={f?.sources} onChange={set} format={(x) => x.key.replace(/_/g, " ")} />
            <div className="grid grid-cols-2 gap-2">
              <label className="flex flex-col gap-1 text-xs text-muted">
                From
                <input type="date" value={get("since")} onChange={(e) => set("since", e.target.value)} className={inputCls} />
              </label>
              <label className="flex flex-col gap-1 text-xs text-muted">
                To
                <input type="date" value={get("until")} onChange={(e) => set("until", e.target.value)} className={inputCls} />
              </label>
            </div>
          </div>
        </Card>

        <Card>
          <InfiniteNews
            key={base}
            base={base}
            highlight={get("ticker") || undefined}
            emptyTitle="No stories match these filters"
            emptyBody="Loosen a filter or clear them all."
          />
        </Card>
      </div>
    </div>
  );
}
