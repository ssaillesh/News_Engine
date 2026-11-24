"use client";

import { useNow, marketStatus } from "@/lib/time";

const OPEN = 570; // 09:30 ET
const CLOSE = 960; // 16:00 ET

function etParts(ms: number) {
  const f = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const o: Record<string, string> = {};
  for (const p of f.formatToParts(new Date(ms))) o[p.type] = p.value;
  return { day: o.weekday, mins: Number(o.hour) * 60 + Number(o.minute), clock: `${o.hour}:${o.minute}` };
}

const span = (m: number) => {
  const d = Math.floor(m / 1440);
  const h = Math.floor((m % 1440) / 60);
  const mm = m % 60;
  return d ? `${d}D ${h}H` : h ? `${h}H ${String(mm).padStart(2, "0")}M` : `${mm}M`;
};

/** Minutes to the next bell. Regular hours only; holidays are not modelled. */
function nextBell(ms: number): { open: boolean; label: string } {
  const { day, mins } = etParts(ms);
  const weekday = !["Sat", "Sun"].includes(day);
  if (weekday && mins >= OPEN && mins < CLOSE) return { open: true, label: `CLOSES IN ${span(CLOSE - mins)}` };
  if (weekday && mins < OPEN) return { open: false, label: `OPENS IN ${span(OPEN - mins)}` };
  const ahead = { Fri: 3, Sat: 2, Sun: 1 }[day] ?? 1;
  return { open: false, label: `OPENS IN ${span(ahead * 1440 - mins + OPEN)}` };
}

export function Countdown() {
  const now = useNow();
  if (now === null) return <div className="lg-bell">&nbsp;</div>;
  const bell = nextBell(now);
  const st = marketStatus(now);
  return (
    <div className="lg-bell">
      <span>
        <i className={bell.open ? "lg-dotUp" : "lg-dotDn"} aria-hidden />
        NYSE · TSX <b>{st.label}</b>
      </span>
      <span>{bell.label}</span>
      <span className="dim">{etParts(now).clock} ET</span>
    </div>
  );
}
