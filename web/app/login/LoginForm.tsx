"use client";

import { useState, type CSSProperties } from "react";
import { useSearchParams } from "next/navigation";
import { Countdown } from "./Countdown";

const MODULES = ["TODAY", "WASHINGTON", "NEWS", "MARKETS", "STOCK", "PORTFOLIO", "POLYMARKET"];
const BOOT = ["ESTABLISHING SECURE LINK", "7 MODULES MOUNTED", "AUTHORIZATION REQUIRED"];

const delay = (i: number, base = 0, step = 0.12) => ({ "--d": `${base + i * step}s` }) as CSSProperties;

export function LoginForm({ next, error }: { next: string; error: boolean }) {
  const [busy, setBusy] = useState(false);
  const state = busy ? "VERIFY" : error ? "DENIED" : "LOCKED";

  return (
    <section className={`lg-card ${error && !busy ? "lg-denied" : ""}`} aria-labelledby="signin">
      <header className="lg-head">
        <span className="m">INVESTMENT</span>
        <h1 id="signin" className="lg-glitch" data-text="HUB">
          HUB
        </h1>
        <p className="m lg-type">POLICY → MARKETS, ONE TERMINAL</p>
      </header>

      <ol className="m lg-boot" aria-hidden>
        {BOOT.map((line, i) => (
          <li key={line} style={delay(i, 0.5, 0.35)}>
            <span className="dim">{String(i).padStart(2, "0")}</span> › {line}
            {i === BOOT.length - 1 ? <span className="lg-cursor" /> : <span className="up"> OK</span>}
          </li>
        ))}
      </ol>

      <ul className="m lg-mods" aria-label="Pages behind the sign-in">
        {MODULES.map((m, i) => (
          <li key={m} style={delay(i, 1.4, 0.07)} data-state={state.toLowerCase()}>
            <b>{i + 1}</b>
            <span className="trunc">{m}</span>
            <em>{state}</em>
          </li>
        ))}
      </ul>

      <form method="post" action="/auth/login" onSubmit={() => setBusy(true)} className="lg-form">
        <input type="hidden" name="next" value={next} />
        <label htmlFor="password" className="m">
          SITE PASSWORD
        </label>
        <div className="lg-prompt">
          <span className="m" aria-hidden>
            ›
          </span>
          <input
            id="password"
            type="password"
            name="password"
            required
            autoFocus
            autoComplete="current-password"
            placeholder="••••••••"
            aria-invalid={error || undefined}
            aria-describedby={error ? "signin-error" : undefined}
          />
        </div>
        {error && !busy ? (
          <p id="signin-error" role="alert" className="m lg-err">
            ACCESS DENIED · THAT PASSWORD ISN’T RIGHT
          </p>
        ) : null}
        <button type="submit" disabled={busy} className="m lg-go">
          {busy ? (
            <>
              AUTHENTICATING<span className="lg-dots" />
            </>
          ) : (
            <>
              SIGN IN <kbd>↵</kbd>
            </>
          )}
        </button>
        {busy ? <div className="lg-progress" aria-hidden /> : null}
      </form>

      <Countdown />
    </section>
  );
}

export function LoginFromUrl() {
  const params = useSearchParams();
  return <LoginForm next={params.get("next") ?? "/"} error={params.get("error") === "1"} />;
}
