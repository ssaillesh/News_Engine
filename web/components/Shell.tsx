"use client";

import { Suspense, useEffect, useId, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { fetcher, qs, send, useApi, writeErrorMessage, type ReturnsResponse, type SecuritiesPage } from "@/lib/api";
import { fixed } from "@/lib/format";
import { useHotkeys } from "@/lib/hotkeys";
import { etClock, etDateShort, marketStatus, useNow } from "@/lib/time";

export const LAST_TICKER_KEY = "hub:last-ticker";
const THEME_KEY = "hub:theme";

const PAGES = [
  { key: "1", label: "TODAY", href: "/", match: (p: string) => p === "/" },
  { key: "2", label: "WASHINGTON", href: "/washington", match: (p: string) => p.startsWith("/washington") },
  { key: "3", label: "NEWS", href: "/news", match: (p: string) => p.startsWith("/news") },
  { key: "4", label: "MARKETS", href: "/markets", match: (p: string) => p.startsWith("/markets") },
  { key: "5", label: "STOCK", href: "/ticker", match: (p: string) => p.startsWith("/ticker") },
  { key: "6", label: "PORTFOLIO", href: "/portfolio", match: (p: string) => p.startsWith("/portfolio") },
  { key: "7", label: "POLYMARKET", href: "/polymarket", match: (p: string) => p.startsWith("/polymarket") },
] as const;

const ALIASES: Record<string, string> = {
  TODAY: "/",
  HOME: "/",
  WASH: "/washington",
  WASHINGTON: "/washington",
  WH: "/washington",
  NEWS: "/news",
  MKTS: "/markets",
  MARKETS: "/markets",
  PORT: "/portfolio",
  PORTFOLIO: "/portfolio",
  POLY: "/polymarket",
  POLYMARKET: "/polymarket",
  ODDS: "/polymarket",
  PM: "/polymarket",
};

const PLACEHOLDER: [string, string][] = [
  ["/washington", "TARIFFS  |  EO  |  NVDA   then ENTER"],
  ["/news", "Filter: TARIFFS  |  NVDA  |  ENERGY   then ENTER"],
  ["/markets", "NVDA  |  ENERGY  |  XLK   then ENTER"],
  ["/portfolio", "BUY 10 AAPL @ 340  |  NVDA   then ENTER"],
  ["/polymarket", "POLY  |  NVDA  |  WASH   then ENTER"],
  ["/ticker", "TICKER  |  TOPIC   then ENTER"],
  ["/", "NVDA  |  TARIFFS  |  WASH   then ENTER"],
];

function lastTicker() {
  try {
    return localStorage.getItem(LAST_TICKER_KEY) || "SPY";
  } catch {
    return "SPY";
  }
}

function pageHref(key: string) {
  const page = PAGES.find((p) => p.key === key);
  if (!page) return null;
  return page.key === "5" ? `/ticker/${encodeURIComponent(lastTicker())}` : page.href;
}

// ── theme ──────────────────────────────────────────────────────────────────
function subscribeTheme(cb: () => void) {
  const obs = new MutationObserver(cb);
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => obs.disconnect();
}
const readTheme = () => (document.documentElement.dataset.theme === "light" ? "light" : "dark");

function ThemeToggle() {
  // The pre-paint script in layout.tsx sets data-theme; this mirrors it.
  const theme = useSyncExternalStore(subscribeTheme, readTheme, () => null);
  const flip = () => {
    const next = theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {}
  };
  return (
    <button type="button" className="btn" onClick={flip} aria-label="Switch colour theme">
      {theme === "light" ? "DARK" : "LIGHT"}
    </button>
  );
}

// ── clock / close date ─────────────────────────────────────────────────────
function Clock({ path }: { path: string | null }) {
  const now = useNow();
  const showClose = path !== null && (path.startsWith("/markets") || path.startsWith("/ticker") || path.startsWith("/portfolio"));
  const spy = useApi<ReturnsResponse>(showClose ? "/api/hub/returns?tickers=SPY" : null);
  if (showClose) {
    const d = spy.data?.items.SPY?.date;
    if (d && d === spy.data?.live)
      return (
        <span className="cell m">
          <span className="up" aria-hidden>
            ●
          </span>
          &nbsp;LIVE {now !== null ? etClock(now) : ""}
        </span>
      );
    return <span className="cell m dim">{d ? `CLOSE ${etDateShort(d)}` : "CLOSE —"}</span>;
  }
  if (now === null) return <span className="cell m dim">&nbsp;</span>;
  const st = marketStatus(now);
  return (
    <>
      <span className="cell m dim">{etClock(now)}</span>
      <span className="cell m">
        <span className={st.open ? "up" : "dn"} aria-hidden>
          ●
        </span>
        &nbsp;{st.label}
      </span>
    </>
  );
}

// ── command line ───────────────────────────────────────────────────────────
type Result = { ticker: string; name: string };
const BUY = /^BUY\s+([\d.]+)\s+([A-Z][A-Z0-9.-]{0,9})(?:\s*@\s*([\d.]+))?$/i;
const TICKERISH = /^[A-Z][A-Z0-9.-]{0,9}$/;

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function Command({ path, inputRef }: { path: string | null; inputRef: React.RefObject<HTMLInputElement | null> }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [msg, setMsg] = useState<{ text: string; bad?: boolean } | null>(null);
  const debounced = useDebounced(q.trim(), 180);
  const searchable = debounced && !BUY.test(debounced) && debounced.length <= 40;
  const { data } = useApi<{ results: Result[] }>(searchable ? `/api/hub/search${qs({ q: debounced })}` : null);
  const results = searchable ? (data?.results ?? []).slice(0, 8) : [];
  const listId = useId();
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 5000);
    return () => clearTimeout(t);
  }, [msg]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const done = () => {
    setQ("");
    setOpen(false);
    setActive(-1);
    inputRef.current?.blur();
  };
  const goTicker = (t: string) => {
    done();
    router.push(`/ticker/${encodeURIComponent(t.toUpperCase())}`);
  };

  const run = async (raw: string) => {
    const text = raw.trim();
    if (!text) return;
    const up = text.toUpperCase();
    const buy = BUY.exec(text);
    if (buy) {
      const [, shares, ticker, price] = buy;
      if (!price) {
        setMsg({ text: "BUY NEEDS A PRICE: BUY 10 AAPL @ 340", bad: true });
        return;
      }
      try {
        await send("POST", "/api/hub/holdings", { ticker: ticker.toUpperCase(), shares: Number(shares), avg_cost: Number(price) });
        setMsg({ text: `ADDED ${shares} ${ticker.toUpperCase()} @ ${fixed(Number(price))}` });
        done();
        if (!path?.startsWith("/portfolio")) router.push("/portfolio");
      } catch (e) {
        setMsg({ text: writeErrorMessage(e).toUpperCase(), bad: true });
      }
      return;
    }
    if (/^[1-7]$/.test(up)) {
      const href = pageHref(up);
      if (href) {
        done();
        router.push(href);
      }
      return;
    }
    if (ALIASES[up]) {
      done();
      router.push(ALIASES[up]);
      return;
    }
    if (active >= 0 && results[active]) return goTicker(results[active].ticker);
    if (TICKERISH.test(up)) {
      let list = debounced === text ? results : null;
      if (!list) {
        try {
          list = (await fetcher<{ results: Result[] }>(`/api/hub/search${qs({ q: text })}`)).results;
        } catch {
          list = [];
        }
      }
      if (list.some((r) => r.ticker === up)) return goTicker(up);
    }
    done();
    router.push(`/news${qs({ q: text })}`);
  };

  const placeholder = PLACEHOLDER.find(([p]) => path !== null && (p === "/" ? path === "/" : path.startsWith(p)))?.[1] ?? PLACEHOLDER[5][1];

  return (
    <div ref={box} style={{ position: "relative", flex: 1, display: "flex", minWidth: 0 }}>
      <label htmlFor="cmd" className="m amb" style={{ display: "flex", alignItems: "center", padding: "0 8px", fontSize: 14 }}>
        &gt;
      </label>
      <input
        id="cmd"
        ref={inputRef}
        className="cmd"
        role="combobox"
        aria-label="Command: ticker, topic, page, or BUY order"
        aria-expanded={open && results.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        spellCheck={false}
        value={q}
        placeholder={placeholder}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, results.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, -1));
          } else if (e.key === "Enter") {
            e.preventDefault();
            void run(q);
          } else if (e.key === "Escape") {
            done();
          }
        }}
      />
      {msg ? (
        <span role="status" className={`m ${msg.bad ? "dn" : "up"}`} style={{ alignSelf: "center", padding: "0 10px", fontSize: 11, whiteSpace: "nowrap" }}>
          {msg.text}
        </span>
      ) : null}
      {open && results.length ? (
        <ul
          id={listId}
          role="listbox"
          className="m"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            zIndex: 30,
            margin: 0,
            padding: 0,
            listStyle: "none",
            background: "var(--pane)",
            border: "1px solid var(--amb)",
            maxHeight: 320,
            overflow: "auto",
          }}
        >
          {results.map((r, i) => (
            <li
              key={`${r.ticker}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                goTicker(r.ticker);
              }}
              className="r"
              style={{ justifyContent: "flex-start", cursor: "pointer", fontSize: 13, background: i === active ? "var(--sel)" : undefined }}
            >
              <span className="amb" style={{ width: 70, fontWeight: 600 }}>
                {r.ticker}
              </span>
              <span className="dim trunc" style={{ fontFamily: "var(--font-archivo)" }}>
                {r.name}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

// ── nav ────────────────────────────────────────────────────────────────────
function Hint({ path, signOut }: { path: string; signOut: boolean }) {
  const core = useApi<SecuritiesPage>(path.startsWith("/markets") ? "/api/hub/securities?limit=1" : null);
  const all = useApi<SecuritiesPage>(path.startsWith("/markets") ? "/api/hub/securities?scope=all&limit=1" : null);
  let text = "1–7 PAGES · / SEARCH · J/K NEXT STORY · ENTER OPEN";
  if (path.startsWith("/washington")) text = "SOURCES: WHITE HOUSE · PRESIDENTIAL DOCS · FEDERAL REGISTER";
  else if (path.startsWith("/news")) text = "J/K MOVE · ENTER OPEN SOURCE";
  else if (path.startsWith("/markets"))
    text = `${core.data ? core.data.total.toLocaleString() : "—"} CORE · ${all.data ? all.data.total.toLocaleString() : "—"} LISTED`;
  else if (path.startsWith("/ticker")) text = "W WATCH · H ADD HOLDING · R REFRESH";
  else if (path.startsWith("/portfolio")) text = signOut ? "PRIVATE · PASSWORD PROTECTED" : "PRIVATE";
  return (
    <span className="m dim" style={{ marginLeft: "auto", alignSelf: "center", padding: "0 12px", fontSize: 11 }}>
      {text}
    </span>
  );
}

function Nav({ path, signOut }: { path: string; signOut: boolean }) {
  return (
    <nav aria-label="Pages" style={{ display: "flex", flexWrap: "wrap", borderBottom: "1px solid var(--rule)" }}>
      {PAGES.map((p) => {
        const on = p.match(path);
        return (
          <Link
            key={p.key}
            href={p.href}
            className={on ? "fk on" : "fk"}
            aria-current={on ? "page" : undefined}
          >
            <b>{p.key}</b>
            {p.label}
          </Link>
        );
      })}
      <Hint path={path} signOut={signOut} />
    </nav>
  );
}

// ── header ─────────────────────────────────────────────────────────────────
function Header({ path, signOut }: { path: string | null; signOut: boolean }) {
  const router = useRouter();
  const cmd = useRef<HTMLInputElement>(null);
  const login = path === "/login";

  useHotkeys(
    login
      ? {}
      : {
          "/": () => cmd.current?.focus(),
          ...Object.fromEntries(
            PAGES.map((p) => [
              p.key,
              () => {
                const href = pageHref(p.key);
                if (href) router.push(href);
              },
            ]),
          ),
        },
  );

  return (
    <>
      <header className="hdr">
        <Link href="/" className="logo m" aria-label="The Hub home">
          <span className="logo-mark" aria-hidden />
        </Link>
        {login ? <span style={{ flex: 1 }} /> : <Command path={path} inputRef={cmd} />}
        <Clock path={path} />
        {signOut && !login ? (
          <form method="post" action="/auth/logout" className="cell" style={{ padding: "0 8px" }}>
            <button type="submit" className="btn">
              LOGOUT
            </button>
          </form>
        ) : null}
        <span className="cell" style={{ padding: "0 8px" }}>
          <ThemeToggle />
        </span>
      </header>
      {path !== null && !login ? <Nav path={path} signOut={signOut} /> : null}
    </>
  );
}

// usePathname suspends on routes with unknown dynamic params (/ticker/[symbol])
// under Cache Components, so only this piece sits behind a boundary.
function ActiveHeader({ signOut }: { signOut: boolean }) {
  return <Header path={usePathname()} signOut={signOut} />;
}

export function Shell({ signOut, children }: { signOut: boolean; children: ReactNode }) {
  return (
    <div className="root">
      <Suspense fallback={<Header path={null} signOut={signOut} />}>
        <ActiveHeader signOut={signOut} />
      </Suspense>
      <main>{children}</main>
    </div>
  );
}
