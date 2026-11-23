"use client";

import type { CSSProperties, ReactNode } from "react";
import { cls, pct } from "@/lib/format";

/** A titled terminal pane: amber title bar over a scrolling body. */
export function Pane({
  title,
  right,
  children,
  className = "",
  style,
  label,
}: {
  title: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  label?: string;
}) {
  return (
    <section className={`pane ${className}`} style={style} aria-label={label}>
      <div className="tb">
        <h2 style={{ margin: 0, font: "inherit" }}>{title}</h2>
        {right ? <span>{right}</span> : null}
      </div>
      {children}
    </section>
  );
}

export function Tabs<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} style={{ display: "contents" }}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          className={o.value === value ? "btn on" : "btn"}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** A filter/toolbar row under a title bar. */
export function Toolbar({ children }: { children: ReactNode }) {
  return (
    <div className="r" style={{ justifyContent: "flex-start", flexWrap: "wrap", gap: 6 }}>
      {children}
    </div>
  );
}

/** Horizontal amber bar; `value` is 0–100. */
export function Bar({ value, style }: { value: number | null | undefined; style?: CSSProperties }) {
  const w = Math.max(0, Math.min(100, value ?? 0));
  return (
    <div className="blk" style={style}>
      <span style={{ width: `${w}%` }} />
    </div>
  );
}

/** Signed percent in up/down colour. */
export function Chg({ v, digits = 2, className = "", style }: { v: number | null | undefined; digits?: number; className?: string; style?: CSSProperties }) {
  return (
    <span className={`m ${cls(v)} ${className}`} style={style}>
      {pct(v, digits)}
    </span>
  );
}

export function SkRows({ rows = 6, h = 30 }: { rows?: number; h?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="r">
          <div className="sk" style={{ height: h - 16, width: `${60 + ((i * 37) % 35)}%` }} />
        </div>
      ))}
    </div>
  );
}

export function PaneError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="m" style={{ padding: 10, fontSize: 12 }}>
      <div className="dn">ERROR · {msg}</div>
      {onRetry ? (
        <button type="button" className="btn" style={{ marginTop: 8 }} onClick={onRetry}>
          RETRY
        </button>
      ) : null}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="m dim" style={{ padding: "14px 10px", fontSize: 12, lineHeight: 1.5 }}>
      {children}
    </div>
  );
}

/** Background for a heat-map tile: green or red mixed into the pane by size of move. */
export function heat(v: number | null | undefined, scale = 2): CSSProperties {
  if (v === null || v === undefined || !Number.isFinite(v)) return { background: "var(--pane)" };
  const a = Math.min(Math.abs(v) / scale, 1);
  const p = Math.round(16 + a * 46);
  return { background: `color-mix(in srgb, ${v >= 0 ? "var(--up)" : "var(--dn)"} ${p}%, var(--pane))` };
}

/** Simple line chart in a 800×H box; each series is an array of y values (nulls skipped). */
export function LineChart({
  series,
  height = 240,
  label,
  markers = [],
  baseline,
}: {
  series: { values: (number | null)[]; color: string; width?: number; dash?: string }[];
  height?: number;
  label: string;
  markers?: { index: number; color: string; r?: number; title?: string }[];
  baseline?: number;
}) {
  const all = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  if (baseline !== undefined) all.push(baseline);
  if (!all.length) return null;
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (hi === lo) {
    hi += 1;
    lo -= 1;
  }
  const pad = (hi - lo) * 0.08;
  lo -= pad;
  hi += pad;
  const n = Math.max(...series.map((s) => s.values.length));
  const x = (i: number) => (n <= 1 ? 0 : (i / (n - 1)) * 800);
  const y = (v: number) => height - ((v - lo) / (hi - lo)) * height;
  const path = (vals: (number | null)[]) =>
    vals
      .map((v, i) => (v === null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`))
      .filter(Boolean)
      .join(" ");
  const first = series[0]?.values ?? [];
  return (
    <svg viewBox={`0 0 800 ${height}`} preserveAspectRatio="none" role="img" aria-label={label} style={{ width: "100%", height: "100%", display: "block" }}>
      {[0.25, 0.5, 0.75].map((f) => (
        <line key={f} x1="0" x2="800" y1={height * f} y2={height * f} stroke="var(--rule)" vectorEffect="non-scaling-stroke" />
      ))}
      {baseline !== undefined ? (
        <line x1="0" x2="800" y1={y(baseline)} y2={y(baseline)} stroke="var(--dim)" strokeDasharray="3 4" vectorEffect="non-scaling-stroke" />
      ) : null}
      {series.map((s, i) => (
        <polyline
          key={i}
          points={path(s.values)}
          fill="none"
          stroke={s.color}
          strokeWidth={s.width ?? 2}
          strokeDasharray={s.dash}
          vectorEffect="non-scaling-stroke"
          strokeLinejoin="round"
        />
      ))}
      {markers.map((m, i) => {
        const v = first[m.index];
        if (v === null || v === undefined) return null;
        // A zero-length round-capped stroke stays a dot when the box is stretched.
        const cx = x(m.index);
        const cy = y(v);
        return (
          <line key={i} x1={cx} y1={cy} x2={cx} y2={cy} stroke={m.color} strokeWidth={(m.r ?? 4) * 2} strokeLinecap="round" vectorEffect="non-scaling-stroke">
            {m.title ? <title>{m.title}</title> : null}
          </line>
        );
      })}
    </svg>
  );
}
