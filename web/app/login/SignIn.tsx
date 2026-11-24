"use client";

import { useState, type KeyboardEvent } from "react";
import { useSearchParams } from "next/navigation";
import { Backdrop } from "./Backdrop";
import { EXCHANGES, nextBell, status, useTick, type Status } from "./exchanges";

const SHOWN = ["NYSE", "TSX", "LSE", "XETRA", "EURONEXT", "TSE", "HKEX", "ASX"];
const BOARD = EXCHANGES.filter((ex) => SHOWN.includes(ex.code));
const NYSE = EXCHANGES[0];

const FEATURES = [
  ["Impact-scored news", "Executive orders, filings and headlines ranked by how much they could move markets."],
  ["Live portfolio", "NYSE and TSX holdings in one view, totalled in Canadian dollars at today’s rate."],
  ["Prediction markets", "Polymarket odds lined up with the coverage behind them."],
] as const;

const TONE: Record<Status, string> = { OPEN: "open", LUNCH: "lunch", CLOSED: "closed" };
const WORD: Record<Status, string> = { OPEN: "Open", LUNCH: "Lunch", CLOSED: "Closed" };

function Markets() {
  const now = useTick(15_000);
  const rows = BOARD.map((ex) => ({ ex, st: now === null ? null : status(ex, now) }));
  const open = rows.filter((r) => r.st?.status === "OPEN").length;
  return (
    <section className="lg-markets" aria-labelledby="lg-markets-h">
      <header>
        <h2 id="lg-markets-h">Global markets</h2>
        <span className="m">{now === null ? "" : `${open} of ${BOARD.length} open`}</span>
      </header>
      <ul>
        {rows.map(({ ex, st }) => (
          <li key={ex.code}>
            <i className={`lg-dot ${st ? TONE[st.status] : ""}`} aria-hidden />
            <b className="m">{ex.code}</b>
            <span className="lg-city">{ex.city.toLowerCase()}</span>
            <span className="m lg-time">{st ? st.clock.slice(0, 5) : "--:--"}</span>
            <span className={`lg-state ${st ? TONE[st.status] : ""}`}>{st ? WORD[st.status] : ""}</span>
          </li>
        ))}
      </ul>
      <p>
        {now === null ? " " : `NYSE · ${nextBell(NYSE, now)}`}
        <span> · Regular hours, local time. Holidays not shown.</span>
      </p>
    </section>
  );
}

function Brand() {
  return (
    <aside className="lg-brand">
      <Backdrop />
      <div className="lg-brand-inner">
        <div className="lg-lockup">
          <span className="lg-mark" role="img" aria-label="SM" />
          <span className="lg-word">The Hub</span>
        </div>
        <div className="lg-pitch">
          <h2>From policy to price, in one terminal.</h2>
          <p>
            Washington, the news and the markets, linked. Every story is scored for sentiment and market impact,
            next to the prices it moves.
          </p>
          <dl>
            {FEATURES.map(([term, desc]) => (
              <div key={term}>
                <dt>{term}</dt>
                <dd>{desc}</dd>
              </div>
            ))}
          </dl>
        </div>
        <Markets />
      </div>
    </aside>
  );
}

export function LoginForm({ next, error }: { next: string; error: boolean }) {
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);
  const [caps, setCaps] = useState(false);
  const failed = error && !busy;
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => setCaps(e.getModifierState?.("CapsLock") ?? false);

  return (
    <div className="lg-split">
      <Brand />
      <section className="lg-auth" aria-labelledby="signin">
        <div className="lg-panel">
          <div className="lg-lockup lg-lockup-sm">
            <span className="lg-mark" role="img" aria-label="SM" />
            <span className="lg-word">The Hub</span>
          </div>
          <h1 id="signin">Sign in</h1>
          <p className="lg-lede">The Hub is private. Enter the access password to continue.</p>

          <form method="post" action="/auth/login" onSubmit={() => setBusy(true)} className="lg-form">
            <input type="hidden" name="next" value={next} />
            <label htmlFor="password">Password</label>
            <div className={`lg-field ${failed ? "lg-field-err" : ""}`}>
              <input
                id="password"
                type={show ? "text" : "password"}
                name="password"
                required
                autoFocus
                autoComplete="current-password"
                spellCheck={false}
                onKeyDown={onKey}
                onKeyUp={onKey}
                aria-invalid={failed || undefined}
                aria-describedby={failed ? "signin-error" : caps ? "signin-caps" : undefined}
              />
              <button
                type="button"
                className="lg-reveal"
                onClick={() => setShow((v) => !v)}
                aria-pressed={show}
                aria-controls="password"
              >
                {show ? "Hide" : "Show"}
              </button>
            </div>
            {failed ? (
              <p id="signin-error" role="alert" className="lg-msg lg-msg-err">
                That password isn’t right. Try again.
              </p>
            ) : caps ? (
              <p id="signin-caps" className="lg-msg">
                Caps Lock is on.
              </p>
            ) : null}
            <button type="submit" disabled={busy} className="lg-submit">
              {busy ? (
                <>
                  <span className="lg-spin" aria-hidden />
                  Signing in…
                </>
              ) : (
                "Sign in"
              )}
            </button>
          </form>

          <p className="lg-note">You’ll stay signed in on this device for 30 days.</p>
        </div>
        <footer className="lg-legal">
          <span>© The Hub</span>
          <span>For information only. Not investment advice.</span>
        </footer>
      </section>
    </div>
  );
}

export function LoginFromUrl() {
  const params = useSearchParams();
  return <LoginForm next={params.get("next") ?? "/"} error={params.get("error") === "1"} />;
}
