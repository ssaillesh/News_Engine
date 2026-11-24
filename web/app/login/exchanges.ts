import { useEffect, useState } from "react";

/** Regular sessions in each exchange's local time, as [open, close] minute pairs.
 *  Lunch breaks are the gaps between pairs. Holidays are not modelled. */
export type Exchange = { code: string; city: string; tz: string; sessions: [number, number][] };

const t = (h: number, m = 0) => h * 60 + m;

export const EXCHANGES: Exchange[] = [
  { code: "NYSE", city: "NEW YORK", tz: "America/New_York", sessions: [[t(9, 30), t(16)]] },
  { code: "TSX", city: "TORONTO", tz: "America/Toronto", sessions: [[t(9, 30), t(16)]] },
  { code: "B3", city: "SÃO PAULO", tz: "America/Sao_Paulo", sessions: [[t(10), t(17)]] },
  { code: "LSE", city: "LONDON", tz: "Europe/London", sessions: [[t(8), t(16, 30)]] },
  { code: "XETRA", city: "FRANKFURT", tz: "Europe/Berlin", sessions: [[t(9), t(17, 30)]] },
  { code: "EURONEXT", city: "PARIS", tz: "Europe/Paris", sessions: [[t(9), t(17, 30)]] },
  { code: "SIX", city: "ZURICH", tz: "Europe/Zurich", sessions: [[t(9), t(17, 20)]] },
  { code: "NSE", city: "MUMBAI", tz: "Asia/Kolkata", sessions: [[t(9, 15), t(15, 30)]] },
  { code: "SSE", city: "SHANGHAI", tz: "Asia/Shanghai", sessions: [[t(9, 30), t(11, 30)], [t(13), t(15)]] },
  { code: "HKEX", city: "HONG KONG", tz: "Asia/Hong_Kong", sessions: [[t(9, 30), t(12)], [t(13), t(16)]] },
  { code: "TSE", city: "TOKYO", tz: "Asia/Tokyo", sessions: [[t(9), t(11, 30)], [t(12, 30), t(15, 30)]] },
  { code: "ASX", city: "SYDNEY", tz: "Australia/Sydney", sessions: [[t(10), t(16)]] },
];

export type Status = "OPEN" | "LUNCH" | "CLOSED";

const fmt = new Map<string, Intl.DateTimeFormat>();

export function local(ms: number, tz: string) {
  let f = fmt.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    });
    fmt.set(tz, f);
  }
  const o: Record<string, string> = {};
  for (const p of f.formatToParts(new Date(ms))) o[p.type] = p.value;
  return { day: o.weekday, mins: Number(o.hour) * 60 + Number(o.minute), clock: `${o.hour}:${o.minute}:${o.second}` };
}

export function status(ex: Exchange, ms: number): { clock: string; status: Status } {
  const { day, mins, clock } = local(ms, ex.tz);
  if (day === "Sat" || day === "Sun") return { clock, status: "CLOSED" };
  const first = ex.sessions[0][0];
  const last = ex.sessions[ex.sessions.length - 1][1];
  if (ex.sessions.some(([a, b]) => mins >= a && mins < b)) return { clock, status: "OPEN" };
  if (mins >= first && mins < last) return { clock, status: "LUNCH" };
  return { clock, status: "CLOSED" };
}

const span = (m: number) => {
  const d = Math.floor(m / 1440);
  const h = Math.floor((m % 1440) / 60);
  const mm = m % 60;
  return d ? `${d}d ${h}h` : h ? `${h}h ${String(mm).padStart(2, "0")}m` : `${mm}m`;
};

/** "Closes in 2h 05m", "Opens in 13h 58m": time to the next bell in local hours. */
export function nextBell(ex: Exchange, ms: number): string {
  const { day, mins } = local(ms, ex.tz);
  const weekday = day !== "Sat" && day !== "Sun";
  if (weekday) {
    const now = ex.sessions.find(([a, b]) => mins >= a && mins < b);
    if (now) return `Closes in ${span(now[1] - mins)}`;
    const later = ex.sessions.find(([a]) => mins < a);
    if (later) return `${mins < ex.sessions[0][0] ? "Opens" : "Reopens"} in ${span(later[0] - mins)}`;
  }
  const ahead = ({ Fri: 3, Sat: 2 } as Record<string, number>)[day] ?? 1;
  return `Opens in ${span(ahead * 1440 - mins + ex.sessions[0][0])}`;
}

/** Epoch ms, refreshed every ``ms``; null until mounted (nothing time-based prerenders). */
export function useTick(ms = 15_000): number | null {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, ms);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [ms]);
  return now;
}
