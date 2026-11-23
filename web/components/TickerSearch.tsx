"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useApi, qs } from "@/lib/api";
import { inputCls } from "./ui";

type Result = { ticker: string; name: string };

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/**
 * Ticker lookup against /api/hub/search. Enter on free text goes straight to
 * that symbol, so a known ticker never waits on the search round-trip.
 */
export function TickerSearch({
  onPick,
  placeholder = "Search ticker or company…",
  className = "",
  autoFocus,
}: {
  onPick?: (ticker: string) => void;
  placeholder?: string;
  className?: string;
  autoFocus?: boolean;
}) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const debounced = useDebounced(q.trim(), 200);
  const { data, isLoading } = useApi<{ results: Result[] }>(
    debounced ? `/api/hub/search${qs({ q: debounced })}` : null,
  );
  const results = debounced ? (data?.results ?? []) : [];
  const listId = useId();
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const pick = (ticker: string) => {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setQ("");
    setOpen(false);
    if (onPick) onPick(t);
    else router.push(`/ticker/${encodeURIComponent(t)}`);
  };

  return (
    <div ref={box} className={`relative ${className}`}>
      <input
        type="search"
        role="combobox"
        aria-expanded={open && results.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-label="Search securities"
        autoFocus={autoFocus}
        value={q}
        placeholder={placeholder}
        className={inputCls}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, results.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            const exact = results.find((r) => r.ticker === q.trim().toUpperCase());
            pick(exact?.ticker ?? results[active]?.ticker ?? q);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {open && debounced ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute left-0 right-0 top-full z-30 mt-1 max-h-80 overflow-auto rounded-lg border border-border bg-surface py-1 shadow-lg"
        >
          {results.length === 0 ? (
            <li className="px-3 py-2 text-sm text-muted">
              {isLoading ? "Searching…" : `No matches. Press Enter to open ${debounced.toUpperCase()}.`}
            </li>
          ) : (
            results.map((r, i) => (
              <li
                key={`${r.ticker}-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(r.ticker);
                }}
                className={`flex cursor-pointer items-baseline gap-3 px-3 py-1.5 text-sm ${i === active ? "bg-surface-2" : ""}`}
              >
                <span className="num w-16 shrink-0 font-semibold">{r.ticker}</span>
                <span className="truncate text-muted">{r.name}</span>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
