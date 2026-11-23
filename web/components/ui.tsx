"use client";

import { useState, type ReactNode } from "react";
import { pct, tone, toneBg, toneText } from "@/lib/format";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-border bg-surface ${className}`}>{children}</section>;
}

export function CardHeader({ title, sub, right }: { title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        {sub ? <p className="mt-0.5 text-xs text-muted">{sub}</p> : null}
      </div>
      {right}
    </div>
  );
}

export function Change({ value, className = "" }: { value: number | null | undefined; className?: string }) {
  return <span className={`num ${toneText[tone(value)]} ${className}`}>{pct(value)}</span>;
}

export function ChangePill({ value }: { value: number | null | undefined }) {
  return (
    <span className={`num inline-flex min-w-[4.5rem] justify-end rounded-md px-1.5 py-0.5 text-xs font-medium ${toneBg[tone(value)]}`}>
      {pct(value)}
    </span>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  size = "sm",
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  size?: "sm" | "xs";
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={`rounded-md font-medium transition-colors ${size === "xs" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-xs"} ${
              active ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function Logo({ ticker, url, size = 32 }: { ticker: string; url?: string | null; size?: number }) {
  const [failed, setFailed] = useState(false);
  const style = { width: size, height: size };
  if (url && !failed) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- remote logos from many hosts
      <img
        src={url}
        alt=""
        style={style}
        onError={() => setFailed(true)}
        className="shrink-0 rounded-md border border-border bg-white object-contain p-0.5"
      />
    );
  }
  return (
    <span
      style={style}
      aria-hidden
      className="num grid shrink-0 place-items-center rounded-md border border-border bg-surface-2 text-[10px] font-semibold text-muted"
    >
      {ticker.slice(0, 4)}
    </span>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-surface-2 ${className}`} />;
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="m-4 rounded-lg border border-down/30 bg-down-soft px-4 py-3 text-sm text-down">
      <p className="font-medium">Couldn’t load this.</p>
      <p className="mt-1 opacity-90">{msg}</p>
      {onRetry ? (
        <button onClick={onRetry} className="mt-2 text-xs font-semibold underline underline-offset-2">
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-4 py-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      {children ? <div className="mx-auto mt-1 max-w-sm text-sm text-muted">{children}</div> : null}
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-muted">{label}</div>
      <div className="num mt-1 truncate text-xl font-semibold tracking-tight">{value}</div>
      {sub ? <div className="mt-0.5 text-xs">{sub}</div> : null}
    </div>
  );
}

export const buttonCls = {
  primary:
    "inline-flex items-center justify-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50",
  secondary:
    "inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-2 disabled:opacity-50",
  ghost: "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-muted hover:bg-surface-2 hover:text-text disabled:opacity-50",
};

export const inputCls =
  "w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-sm placeholder:text-faint focus:border-accent focus:outline-none";
