"use client";

import { useState } from "react";
import Link from "next/link";
import { send, useApi, writeErrorMessage, type Dashboard as DashboardData, type WatchItem } from "@/lib/api";
import { money, signedMoney, tone, toneText } from "@/lib/format";
import { useToday } from "@/lib/useToday";
import { NewsItems, NewsSkeleton } from "@/components/News";
import { TickerSearch } from "@/components/TickerSearch";
import { Card, CardHeader, ChangePill, Empty, ErrorBox, Logo, Segmented, Skeleton, Stat } from "@/components/ui";

type Window = "1" | "7" | "30";

export function Dashboard() {
  const [days, setDays] = useState<Window>("7");
  const dash = useApi<DashboardData>(`/api/hub/dashboard?days=${days}`);
  const d = dash.data;
  const today = useToday();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="mt-1 text-sm text-muted">
          {today ?? "\u00a0"}
          {d ? ` · tracking ${d.tickers.length} ${d.tickers.length === 1 ? "ticker" : "tickers"}` : ""}
        </p>
      </div>

      {dash.error && !d ? <ErrorBox error={dash.error} onRetry={() => dash.mutate()} /> : null}

      <PortfolioStrip data={d} />
      <Movers data={d} />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Top news for your tickers"
            sub="Ranked by impact score across your watchlist and holdings."
            right={
              <Segmented
                label="News window"
                size="xs"
                value={days}
                onChange={setDays}
                options={[
                  { value: "1", label: "24h" },
                  { value: "7", label: "7d" },
                  { value: "30", label: "30d" },
                ]}
              />
            }
          />
          {!d ? (
            <NewsSkeleton />
          ) : d.top_news.length ? (
            <div className={dash.isValidating ? "opacity-60 transition-opacity" : ""}>
              <NewsItems items={d.top_news} />
              <div className="border-t border-border px-4 py-3 text-center">
                <Link href="/news?sort=impact" className="text-sm font-medium text-accent hover:underline">
                  Open the full news feed →
                </Link>
              </div>
            </div>
          ) : (
            <Empty title={d.tickers.length ? "No stories in this window" : "Nothing tracked yet"}>
              {d.tickers.length ? "Try a longer window, or run an ingest." : "Add tickers to your watchlist to see news about them here."}
            </Empty>
          )}
        </Card>
        <Watchlist />
      </div>
    </div>
  );
}

function PortfolioStrip({ data }: { data: DashboardData | undefined }) {
  if (!data) {
    return (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-[84px] rounded-xl" />
        ))}
      </div>
    );
  }
  const p = data.portfolio;
  if (!p) {
    return (
      <Card className="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
        <div>
          <p className="text-sm font-medium">No holdings yet</p>
          <p className="text-sm text-muted">Record your positions to see value, day change and P&amp;L here.</p>
        </div>
        <Link href="/portfolio" className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90">
          Add holdings
        </Link>
      </Card>
    );
  }
  return (
    <Link href="/portfolio" className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Card className="px-4 py-3 hover:border-border-strong">
        <Stat label="Portfolio value" value={money(p.market_value)} />
      </Card>
      <Card className="px-4 py-3 hover:border-border-strong">
        <Stat
          label="Today"
          value={<span className={toneText[tone(p.day_change)]}>{signedMoney(p.day_change)}</span>}
          sub={<ChangePill value={p.day_change_pct} />}
        />
      </Card>
      <Card className="px-4 py-3 hover:border-border-strong">
        <Stat
          label="Unrealized P&L"
          value={<span className={toneText[tone(p.unrealized_pnl)]}>{signedMoney(p.unrealized_pnl)}</span>}
          sub={<ChangePill value={p.unrealized_pnl_pct} />}
        />
      </Card>
      <Card className="px-4 py-3 hover:border-border-strong">
        <Stat label="Cost basis" value={money(p.cost_basis)} />
      </Card>
    </Link>
  );
}

function Movers({ data }: { data: DashboardData | undefined }) {
  if (!data || !data.movers.length) return null;
  return (
    <section aria-labelledby="movers">
      <h2 id="movers" className="mb-2 text-sm font-semibold tracking-tight">
        Biggest moves today
      </h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {data.movers.slice(0, 5).map((m) => (
          <Link
            key={m.ticker}
            href={`/ticker/${m.ticker}`}
            className="rounded-xl border border-border bg-surface px-3 py-3 hover:border-border-strong"
          >
            <div className="flex items-center gap-2">
              <Logo ticker={m.ticker} url={m.logo_url} size={24} />
              <span className="num text-sm font-semibold">{m.ticker}</span>
              <span className="ml-auto">
                <ChangePill value={m.quote?.pct_change} />
              </span>
            </div>
            <div className="num mt-2 text-lg font-semibold tracking-tight">{money(m.quote?.price, m.currency || "USD")}</div>
            <div className="truncate text-xs text-muted">{m.name}</div>
          </Link>
        ))}
      </div>
    </section>
  );
}

function Watchlist() {
  const list = useApi<{ items: WatchItem[] }>("/api/hub/watchlist");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (ticker: string, fn: () => Promise<unknown>) => {
    setPending(ticker);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(writeErrorMessage(e));
    } finally {
      setPending(null);
    }
  };

  const add = (ticker: string) => run(ticker, () => send("POST", "/api/hub/watchlist", { ticker }));
  const remove = (ticker: string) => run(ticker, () => send("DELETE", `/api/hub/watchlist/${encodeURIComponent(ticker)}`));

  return (
    <Card className="self-start">
      <CardHeader title="Watchlist" sub={list.data ? `${list.data.items.length} tickers` : undefined} />
      <div className="border-b border-border px-4 py-3">
        <TickerSearch onPick={add} placeholder="Add a ticker…" />
        {pending && !list.data?.items.some((i) => i.ticker === pending) ? (
          <p className="mt-2 text-xs text-muted">Adding {pending} and fetching its data…</p>
        ) : null}
        {error ? (
          <p role="alert" className="mt-2 text-xs text-down">
            {error}
          </p>
        ) : null}
      </div>
      {list.error && !list.data ? (
        <ErrorBox error={list.error} onRetry={() => list.mutate()} />
      ) : !list.data ? (
        <div className="space-y-2 p-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-9" />
          ))}
        </div>
      ) : !list.data.items.length ? (
        <Empty title="Your watchlist is empty">Search above to start tracking a ticker.</Empty>
      ) : (
        <ul className="divide-y divide-border">
          {list.data.items.map((w) => (
            <li key={w.ticker} className="group flex items-center gap-3 px-4 py-2.5">
              <Link href={`/ticker/${w.ticker}`} className="flex min-w-0 flex-1 items-center gap-3">
                <Logo ticker={w.ticker} url={w.logo_url} size={28} />
                <span className="min-w-0">
                  <span className="num block text-sm font-semibold">{w.ticker}</span>
                  <span className="block truncate text-xs text-muted">{w.name ?? "—"}</span>
                </span>
              </Link>
              <span className="text-right">
                <span className="num block text-sm">{money(w.quote?.price, w.currency || "USD")}</span>
                <ChangePill value={w.quote?.pct_change} />
              </span>
              <button
                onClick={() => remove(w.ticker)}
                disabled={pending === w.ticker}
                aria-label={`Remove ${w.ticker} from watchlist`}
                className="rounded p-1 text-faint opacity-0 hover:bg-surface-2 hover:text-down focus:opacity-100 group-hover:opacity-100 disabled:opacity-50"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
