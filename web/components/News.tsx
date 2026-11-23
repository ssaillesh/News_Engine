"use client";

import Link from "next/link";
import useSWRInfinite from "swr/infinite";
import { fetcher, type NewsItem, type NewsPage } from "@/lib/api";
import { dateTime, num, sentimentTone, timeAgo, toneBg } from "@/lib/format";
import { buttonCls, Empty, ErrorBox, Skeleton } from "./ui";

const TIER_STYLE: Record<string, string> = {
  critical: "bg-down text-white",
  high: "bg-down-soft text-down",
  notable: "bg-warn-soft text-warn",
  routine: "bg-surface-2 text-muted",
};

function SentimentPill({ item }: { item: NewsItem }) {
  const s = item.sentiment;
  if (!s) return null;
  return (
    <span
      title={`FinBERT ${s.label} · compound ${num(s.compound, 3)}`}
      className={`rounded px-1.5 py-0.5 text-[11px] font-medium capitalize ${toneBg[sentimentTone(s.compound)]}`}
    >
      {s.label}
    </span>
  );
}

function ImpactPill({ item }: { item: NewsItem }) {
  const i = item.impact;
  if (!i) return null;
  const why = i.reasons.length ? ` · ${i.reasons.join(", ")}` : "";
  return (
    <span
      title={`Impact score ${num(i.score, 3)}${why}`}
      className={`num rounded px-1.5 py-0.5 text-[11px] font-medium capitalize ${TIER_STYLE[i.tier] ?? TIER_STYLE.routine}`}
    >
      {i.tier} {Math.round(i.score * 100)}
    </span>
  );
}

export function NewsCard({ item, highlight }: { item: NewsItem; highlight?: string }) {
  const source = item.publisher || item.kind || item.source;
  return (
    <article className="group px-4 py-3.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
        <span className="font-medium text-text/80">{source}</span>
        <span aria-hidden>·</span>
        <time dateTime={item.created_at ?? undefined} title={dateTime(item.created_at)}>
          {timeAgo(item.created_at)}
        </time>
        <span className="ml-auto flex items-center gap-1.5">
          <SentimentPill item={item} />
          <ImpactPill item={item} />
        </span>
      </div>
      <h3 className="mt-1.5 text-[15px] font-semibold leading-snug tracking-tight">
        {item.url ? (
          <a href={item.url} target="_blank" rel="noopener noreferrer" className="hover:text-accent">
            {item.title}
          </a>
        ) : (
          item.title
        )}
      </h3>
      {item.summary ? <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-muted">{item.summary}</p> : null}
      {item.generated_summary ? (
        <p className="mt-1.5 line-clamp-3 border-l-2 border-accent/40 pl-2.5 text-sm leading-relaxed text-muted">
          <span className="mr-1 text-[11px] font-semibold uppercase tracking-wide text-accent">Machine summary</span>
          {item.generated_summary.text}
        </p>
      ) : null}
      {item.stocks.length || item.sectors.length || item.topics.length ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {item.stocks.map((s) => (
            <Link
              key={s.ticker}
              href={`/ticker/${s.ticker}`}
              title={`${s.name} — matched “${s.alias}”`}
              className={`num rounded border px-1.5 py-0.5 text-[11px] font-semibold hover:border-accent hover:text-accent ${
                s.ticker === highlight ? "border-accent text-accent" : "border-border text-text/80"
              }`}
            >
              {s.ticker}
            </Link>
          ))}
          {item.sectors.map((s) => (
            <span
              key={s.key}
              title={`matched “${s.matched_term}”`}
              className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-muted"
            >
              {s.label}
              {s.etf ? <span className="num ml-1 font-semibold">{s.etf}</span> : null}
            </span>
          ))}
          {item.topics.slice(0, 2).map((t) => (
            <span key={t.key} className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-muted">
              {t.label}
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
}

export function NewsSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="divide-y divide-border">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="space-y-2 px-4 py-4">
          <Skeleton className="h-3 w-32" />
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="h-3 w-full" />
        </div>
      ))}
    </div>
  );
}

export function NewsItems({ items, highlight }: { items: NewsItem[]; highlight?: string }) {
  return (
    <div className="divide-y divide-border">
      {items.map((item) => (
        <NewsCard key={item.id} item={item} highlight={highlight} />
      ))}
    </div>
  );
}

/**
 * Paged news list. `base` is any endpoint returning `{items}` that accepts
 * `limit`/`offset`; the backend reports no total, so a short page ends it.
 */
export function InfiniteNews({
  base,
  pageSize = 25,
  highlight,
  emptyTitle = "No news yet",
  emptyBody,
}: {
  base: string | null;
  pageSize?: number;
  highlight?: string;
  emptyTitle?: string;
  emptyBody?: React.ReactNode;
}) {
  const sep = base?.includes("?") ? "&" : "?";
  const { data, error, size, setSize, isLoading, isValidating, mutate } = useSWRInfinite<NewsPage>(
    (index, prev) => {
      if (!base) return null;
      if (prev && prev.items.length < pageSize) return null;
      return `${base}${sep}limit=${pageSize}&offset=${index * pageSize}`;
    },
    fetcher,
    { revalidateOnFocus: false, revalidateFirstPage: false },
  );

  if (error && !data) return <ErrorBox error={error} onRetry={() => mutate()} />;
  if (isLoading || !data) return <NewsSkeleton />;

  const items = data.flatMap((p) => p.items);
  const done = data[data.length - 1].items.length < pageSize;
  const loadingMore = isValidating && size > data.length;

  if (!items.length) return <Empty title={emptyTitle}>{emptyBody}</Empty>;
  return (
    <>
      <NewsItems items={items} highlight={highlight} />
      <div className="border-t border-border px-4 py-3 text-center">
        {done ? (
          <span className="text-xs text-faint">
            {items.length} {items.length === 1 ? "story" : "stories"} · end of list
          </span>
        ) : (
          <button className={buttonCls.secondary} disabled={loadingMore} onClick={() => setSize(size + 1)}>
            {loadingMore ? "Loading…" : "Load more"}
          </button>
        )}
      </div>
    </>
  );
}
