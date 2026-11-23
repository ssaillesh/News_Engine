const cache = new Map<string, Intl.NumberFormat>();
function nf(key: string, opts: Intl.NumberFormatOptions) {
  let f = cache.get(key);
  if (!f) {
    f = new Intl.NumberFormat("en-US", opts);
    cache.set(key, f);
  }
  return f;
}

const DASH = "—";
const ok = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

export function money(v: number | null | undefined, currency = "USD", digits = 2) {
  if (!ok(v)) return DASH;
  return nf(`m${currency}${digits}`, {
    style: "currency",
    currency: currency || "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(v);
}

export function signedMoney(v: number | null | undefined, currency = "USD") {
  if (!ok(v)) return DASH;
  return (v > 0 ? "+" : v < 0 ? "−" : "") + money(Math.abs(v), currency);
}

export function pct(v: number | null | undefined, digits = 2, signed = true) {
  if (!ok(v)) return DASH;
  const s = Math.abs(v).toFixed(digits) + "%";
  if (!signed) return (v < 0 ? "−" : "") + s;
  return (v > 0 ? "+" : v < 0 ? "−" : "") + s;
}

export function num(v: number | null | undefined, digits = 2) {
  if (!ok(v)) return DASH;
  return nf(`n${digits}`, { maximumFractionDigits: digits, minimumFractionDigits: 0 }).format(v);
}

export function compact(v: number | null | undefined, currency?: string) {
  if (!ok(v)) return DASH;
  return nf(`c${currency ?? ""}`, {
    notation: "compact",
    maximumFractionDigits: 2,
    ...(currency ? { style: "currency", currency } : {}),
  }).format(v);
}

/** The backend stores naive UTC timestamps; treat a bare ISO string as UTC. */
export function parseUtc(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const hasTz = /([zZ]|[+-]\d\d:?\d\d)$/.test(iso);
  const d = new Date(hasTz || iso.length <= 10 ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function timeAgo(iso: string | null | undefined, now = Date.now()) {
  const d = parseUtc(iso);
  if (!d) return "";
  const s = Math.round((now - d.getTime()) / 1000);
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.round(h / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: days > 300 ? "numeric" : undefined });
}

export function dateTime(iso: string | null | undefined) {
  const d = parseUtc(iso);
  if (!d) return DASH;
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function shortDate(ymd: string) {
  const [y, m, d] = ymd.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

export type Tone = "up" | "down" | "flat";
export const tone = (v: number | null | undefined): Tone => (!ok(v) || v === 0 ? "flat" : v > 0 ? "up" : "down");
/** Terminal colour class for a signed value: "up", "dn" or "dim". */
export const cls = (v: number | null | undefined) => ({ up: "up", down: "dn", flat: "dim" })[tone(v)];

/** FinBERT compound → tone, with a dead zone so faint signals read as neutral. */
export const sentimentTone = (compound: number | null | undefined): Tone =>
  !ok(compound) ? "flat" : compound > 0.15 ? "up" : compound < -0.15 ? "down" : "flat";

/** Plain grouped number with fixed decimals: 48,920.40 */
export function fixed(v: number | null | undefined, digits = 2) {
  if (!ok(v)) return DASH;
  return nf(`f${digits}`, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);
}

/** Signed grouped number with a true minus: +1,987.80 / −612.18 */
export function signed(v: number | null | undefined, digits = 2) {
  if (!ok(v)) return DASH;
  return (v > 0 ? "+" : v < 0 ? "−" : "") + fixed(Math.abs(v), digits);
}

/** Probability-point change: "+4 PTS", "−1 PT" */
export function pts(v: number | null | undefined) {
  if (!ok(v)) return DASH;
  const r = Math.round(v);
  const s = (r > 0 ? "+" : r < 0 ? "−" : "") + Math.abs(r);
  return `${s} ${Math.abs(r) === 1 ? "PT" : "PTS"}`;
}

/** Compact without currency, upper-case suffix: 3.06T, 240B, 61.2M */
export function big(v: number | null | undefined) {
  if (!ok(v)) return DASH;
  return nf("big", { notation: "compact", maximumFractionDigits: 2 }).format(v).toUpperCase();
}
