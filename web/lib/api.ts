import useSWR, { mutate as globalMutate, type SWRConfiguration } from "swr";

// ── types (mirror src/archiver/web/hub.py and app.py serializers) ───────────
export type Quote = {
  price: number | null;
  change: number | null;
  pct_change: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  prev_close: number | null;
  at: string | null;
};

export type Recommendation = {
  period: string;
  strongBuy: number;
  buy: number;
  hold: number;
  sell: number;
  strongSell: number;
};

export type Security = {
  ticker: string;
  tracked_data: boolean;
  name?: string | null;
  exchange?: string | null;
  currency?: string | null;
  country?: string | null;
  industry?: string | null;
  logo_url?: string | null;
  web_url?: string | null;
  ipo_date?: string | null;
  market_cap?: number | null;
  quote?: Quote;
  metrics?: Record<string, number>;
  recommendation?: Recommendation | null;
  last_error?: string | null;
  refreshed_at?: string | null;
};

export type SecurityDetail = Security & { watched: boolean; shares_held: number };
export type WatchItem = Security & { note: string | null; added_at: string };

export type Bar = {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  adj_close: number | null;
  volume: number | null;
};

export type NewsMarker = {
  date: string;
  count: number;
  avg_sentiment: number | null;
  max_impact: number | null;
};

export type PricesResponse = {
  ticker: string;
  range: string;
  bars: Bar[];
  stats: { start: number; end: number; return_pct: number | null; high: number; low: number } | null;
  news_markers: NewsMarker[];
};

export type Sentiment = {
  label: "positive" | "negative" | "neutral" | string;
  score: number;
  compound: number;
  model: string;
};

export type Impact = {
  score: number;
  tier: string;
  stance: string | null;
  authority_label: string | null;
  reasons: string[];
};

export type NewsItem = {
  id: string;
  created_at: string | null;
  source: string;
  kind: string | null;
  publisher: string | null;
  title: string;
  url: string | null;
  text: string;
  summary: string;
  generated_summary: { text: string; model: string; generated_at: string | null } | null;
  sentiment: Sentiment | null;
  impact: Impact | null;
  topics: { key: string; label: string; weight: number; matched_term: string }[];
  entities: { key: string; type: string; alias: string }[];
  stocks: { ticker: string; name: string; alias: string }[];
  sectors: { key: string; label: string; etf: string | null; tickers: string[]; matched_term: string }[];
};

export type NewsPage = { items: NewsItem[] };

export type Position = {
  ticker: string;
  name: string | null;
  lots: number;
  shares: number;
  avg_cost: number | null;
  cost_basis: number | null;
  price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  day_change: number | null;
  day_change_pct: number | null;
  weight_pct: number | null;
};

export type PortfolioTotals = {
  market_value: number | null;
  cost_basis: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  day_change: number | null;
  day_change_pct: number | null;
};

export type Portfolio = { positions: Position[]; totals: PortfolioTotals; unpriced: string[] };

export type Holding = {
  id: number;
  ticker: string;
  shares: number;
  avg_cost: number;
  opened_at: string | null;
  note: string | null;
};

export type Dashboard = {
  tickers: string[];
  movers: Security[];
  portfolio: PortfolioTotals | null;
  top_news: NewsItem[];
};

export type Facet = { key: string; label?: string; count: number; etf?: string };
export type Facets = {
  total: number;
  sources: Facet[];
  sectors: Facet[];
  stances: Facet[];
  companies: Facet[];
  topics: Facet[];
  tiers: Facet[];
  kinds: Facet[];
  sentiments: Facet[];
};

// ── fetching ────────────────────────────────────────────────────────────────
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function parse<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg).join("; ")
          : `Request failed (${res.status})`;
    throw new ApiError(res.status, message);
  }
  return body as T;
}

export const fetcher = <T,>(url: string): Promise<T> => fetch(url).then((r) => parse<T>(r));

export function useApi<T>(url: string | null, config?: SWRConfiguration<T>) {
  return useSWR<T>(url, fetcher, { revalidateOnFocus: false, keepPreviousData: true, ...config });
}

/** Write to the hub, then revalidate every cached hub read. */
export async function send<T>(method: "POST" | "PATCH" | "DELETE", url: string, body?: unknown) {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const out = await parse<T>(res);
  await globalMutate((key) => typeof key === "string" && key.startsWith("/api/hub/"));
  return out;
}

export function writeErrorMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 401) {
    return "The backend requires a write token. Set HUB_WRITE_TOKEN in web/.env.local to match the API's .env and restart the dev server.";
  }
  return err instanceof Error ? err.message : String(err);
}

export const qs = (params: Record<string, string | number | null | undefined>) => {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : "";
};
