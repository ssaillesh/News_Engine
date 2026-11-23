import { useSyncExternalStore } from "react";
import { parseUtc } from "./format";

const TZ = "America/New_York";

// One shared clock, ticking each minute. Rendered only in the browser: Cache
// Components prerenders client components, and reading the time there fails.
let now = typeof window === "undefined" ? 0 : Date.now();
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;

function subscribe(cb: () => void) {
  listeners.add(cb);
  if (!timer) {
    now = Date.now();
    timer = setInterval(() => {
      now = Date.now();
      listeners.forEach((l) => l());
    }, 30_000);
  }
  return () => {
    listeners.delete(cb);
    if (!listeners.size && timer) {
      clearInterval(timer);
      timer = null;
    }
  };
}

/** Epoch ms, refreshed every 30s; null while prerendering and on first hydration. */
export function useNow(): number | null {
  return useSyncExternalStore(
    subscribe,
    () => now,
    () => null,
  );
}

function parts(d: Date) {
  const f = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const o: Record<string, string> = {};
  for (const p of f.formatToParts(d)) o[p.type] = p.value;
  return o;
}

/** "FRI 20-NOV-26 16:12 ET" */
export function etClock(ms: number) {
  const p = parts(new Date(ms));
  return `${p.weekday} ${p.day}-${p.month}-${p.year} ${p.hour}:${p.minute} ET`.toUpperCase();
}

/** "20-NOV-26" for an ISO date or timestamp. */
export function etDateShort(iso: string | null | undefined) {
  const d = iso && iso.length === 10 ? new Date(`${iso}T12:00:00Z`) : parseUtc(iso);
  if (!d) return "—";
  const p = parts(d);
  return `${p.day}-${p.month}-${p.year}`.toUpperCase();
}

/** Regular session 09:30–16:00 ET on weekdays; holidays are not modelled. */
export function marketStatus(ms: number): { label: string; open: boolean } {
  const p = parts(new Date(ms));
  if (p.weekday === "Sat" || p.weekday === "Sun") return { label: "CLOSED", open: false };
  const mins = Number(p.hour) * 60 + Number(p.minute);
  if (mins >= 570 && mins < 960) return { label: "OPEN", open: true };
  if (mins >= 240 && mins < 570) return { label: "PRE-MKT", open: false };
  if (mins >= 960 && mins < 1200) return { label: "AFTER HRS", open: false };
  return { label: "CLOSED", open: false };
}

/** "14:05" in ET. */
export function etTime(iso: string | null | undefined) {
  const d = parseUtc(iso);
  if (!d) return "";
  const p = parts(d);
  return `${p.hour}:${p.minute}`;
}

/** "2026-11-20" calendar day in ET. */
export function etDay(iso: string | null | undefined) {
  const d = parseUtc(iso);
  if (!d) return "";
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

/** "FRI 20 NOV" heading for an ET calendar day ("2026-11-20"). */
export function dayHeading(ymd: string) {
  const d = new Date(`${ymd}T12:00:00Z`);
  const p = parts(d);
  return `${p.weekday} ${p.day} ${p.month}`.toUpperCase();
}

/** "20 NOV" */
export function dayMonth(iso: string | null | undefined) {
  const d = parseUtc(iso);
  if (!d) return "";
  const p = parts(d);
  return `${p.day} ${p.month}`.toUpperCase();
}

/** Story time: "14:05" when it is from today (ET), "YDAY", else "18 NOV". */
export function storyTime(iso: string | null | undefined, nowMs: number | null) {
  if (!iso) return "";
  const day = etDay(iso);
  if (nowMs !== null) {
    const today = etDay(new Date(nowMs).toISOString());
    if (day === today) return etTime(iso);
    const yday = etDay(new Date(nowMs - 86_400_000).toISOString());
    if (day === yday) return "YDAY";
  }
  return dayMonth(iso);
}

/** ISO timestamp `hours` before `nowMs`, rounded down to 15 minutes so fetch keys stay stable. */
export function hoursAgo(nowMs: number, hours: number) {
  const step = 15 * 60_000;
  const t = Math.floor((nowMs - hours * 3_600_000) / step) * step;
  return new Date(t).toISOString().replace(/\.\d{3}Z$/, "Z");
}
