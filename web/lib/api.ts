import useSWR, { mutate as globalMutate, type SWRConfiguration } from "swr";
import { parseUtc } from "./format";

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
  sector?: string | null;
  security_type?: string | null;
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
  stance_confidence?: number | null;
  authority: number;
  authority_label: string | null;
  topic: number;
  actionability: number;
  corroboration: number | null;
  market_sensitivity: number | null;
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

export type NewsPage = { items: NewsItem[]; total?: number };

export type Position = {
  ticker: string;
  name: string | null;
  /** The currency this position is quoted (and its average cost entered) in. */
  currency: string;
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
  /** The same figures in the portfolio's base currency (null if unconverted). */
  market_value_base: number | null;
  unrealized_pnl_base: number | null;
  day_change_base: number | null;
  weight_pct: number | null;
};

export type PortfolioTotals = {
  /** Base currency of every total (e.g. "CAD"). */
  currency?: string | null;
  market_value: number | null;
  cost_basis: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  day_change: number | null;
  day_change_pct: number | null;
};

export type Portfolio = {
  positions: Position[];
  totals: PortfolioTotals;
  /** Units of the base currency per one unit of each other currency held. */
  fx: Record<string, number>;
  unpriced: string[];
  /** Positions in a currency with no rate: listed, kept out of the totals. */
  unconverted: string[];
};

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

/** One row of GET /api/hub/securities (the universe browser). */
export type SecurityRow = {
  ticker: string;
  name: string | null;
  sector: string | null;
  type: string | null;
  tags: string[];
  price: number | null;
  change: number | null;
  pct_change: number | null;
  market_cap: number | null;
  quote_at: string | null;
  pe: number | null;
  r5d: number | null;
  news_7d: number;
};
export type SecuritiesPage = { total: number; items: SecurityRow[] };
export type SecuritySort = "ticker" | "name" | "price" | "pct_change" | "market_cap";
export type Sectors = { sectors: { sector: string; count: number }[] };

/** GET /api/hub/returns: percent returns from stored daily bars. */
export type PeriodReturns = {
  date: string | null;
  close: number | null;
  r1d: number | null;
  r5d: number | null;
  r1m: number | null;
  rytd: number | null;
};
/** ``live``: the session still trading, whose figures are moves so far (null when closed). */
export type ReturnsResponse = { items: Record<string, PeriodReturns>; live?: string | null };

/** GET /api/hub/reactions: moves after each timestamp, percent from the prior close. */
export type Move = { d1: number | null; d5: number | null };
export type ReactionsResponse = {
  benchmark: string;
  events: { at: string; session: string | null; moves: Record<string, Move> }[];
  live?: string | null;
};

export type Odds = {
  question: string;
  probability: number;
  change_1d: number | null;
  volume_24h: number;
  url: string | null;
};
export type OddsResponse = { source: string; items: Odds[]; error?: string };

// ── polymarket × coverage (mirror src/archiver/hub/polymarket.py) ──────────
export type PmKey = { kind: "person" | "company" | "country" | "bloc" | "agency" | "named" | "topic" | string; key: string; label: string };
export type PmOutcome = {
  id: string;
  label: string;
  question: string;
  probability: number;
  change_1d: number | null;
  change_1w: number | null;
  volume_24h: number;
  end_date: string | null;
};
export type PmHeadline = {
  id: string;
  created_at: string;
  source: string;
  title: string;
  publisher: string | null;
  url: string | null;
  /** FinBERT compound, −1…1; null when the source is not scored. */
  sentiment: number | null;
  impact: number | null;
  /** The keys this headline shares with the market: why it is linked. */
  why: PmKey[];
};
export type PmCoverage = {
  count_7d: number;
  count_30d: number;
  scored_7d: number;
  avg_sentiment_7d: number | null;
  latest: PmHeadline | null;
};
export type PmEvent = {
  id: string;
  slug: string;
  title: string;
  url: string | null;
  end_date: string | null;
  volume_24h: number;
  liquidity: number;
  themes: string[];
  keys: PmKey[];
  topics: PmKey[];
  lead: PmOutcome;
  outcome_count: number;
  outcomes: PmOutcome[];
  coverage: PmCoverage | null;
};
export type PmTheme = { key: string; label: string; count?: number };
export type PmListResponse = {
  source: string;
  fetched_at?: string | null;
  window_days?: number;
  total?: number;
  themes: PmTheme[];
  items: PmEvent[];
  error?: string;
};
export type PmDay = {
  date: string;
  probability: number | null;
  change: number | null;
  news_count: number;
  scored: number;
  sentiment: number | null;
};
export type PmStat = { r: number | null; n: number; strength: "none" | "weak" | "moderate" | "strong" | "insufficient" };
export type PmDetail = {
  event: PmEvent;
  outcome: PmOutcome;
  window_days: number;
  today: string;
  days: PmDay[];
  stats: { co_movement: PmStat; attention: PmStat; min_days: number };
  big_moves: { date: string; change: number; probability: number | null; news_count: number; headlines: PmHeadline[] }[];
  headlines: PmHeadline[];
  headline_total: number;
  stocks: { ticker: string; name: string | null; price: number | null; pct_change: number | null; quote_at: string | null; mentions: number }[];
  history_error: string | null;
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
  // The site session expired (see proxy.ts): send the visitor to sign in again.
  if (res.status === 401 && body?.detail === "Sign in required." && typeof window !== "undefined") {
    const here = window.location.pathname + window.location.search;
    // A full load on purpose: it drops every cached response along with the session.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign(`/login?next=${encodeURIComponent(here)}`);
  }
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

/** How often open pages re-read the API. The backend keeps quotes live during
 *  market hours and ingest adds stories every few minutes, so a minute is the
 *  slowest anything on screen can lag. Polling pauses while the tab is hidden. */
export const LIVE_MS = 60_000;

export function useApi<T>(url: string | null, config?: SWRConfiguration<T>) {
  return useSWR<T>(url, fetcher, { refreshInterval: LIVE_MS, revalidateOnFocus: true, keepPreviousData: true, ...config });
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
    return "The backend rejected the hub token. Set HUB_WRITE_TOKEN for the web app to the same value as the API's and restart or redeploy it.";
  }
  return err instanceof Error ? err.message : String(err);
}

export const qs = (params: Record<string, string | number | null | undefined>) => {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : "";
};

/** Key for /api/hub/reactions, or null when there is nothing to ask about. */
export function reactionsKey(at: (string | null | undefined)[], tickers: string[], benchmark = "SPY") {
  const stamps = [...new Set(at.filter((a): a is string => Boolean(a)))];
  if (!stamps.length) return null;
  const sp = new URLSearchParams();
  for (const a of stamps) sp.append("at", a);
  sp.set("tickers", tickers.join(",") || benchmark);
  sp.set("benchmark", benchmark);
  return `/api/hub/reactions?${sp.toString()}`;
}

/** `(at, ticker) => Move` over a reactions response, matching timestamps by instant. */
export function movesLookup(data: ReactionsResponse | undefined) {
  const m = new Map<number, Record<string, Move>>();
  for (const e of data?.events ?? []) {
    const t = parseUtc(e.at)?.getTime();
    if (t !== undefined) m.set(t, e.moves);
  }
  return (at: string | null | undefined, ticker: string): Move | undefined => {
    const t = parseUtc(at)?.getTime();
    return t === undefined ? undefined : m.get(t)?.[ticker];
  };
}
