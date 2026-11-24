"use client";

import { useState, type CSSProperties } from "react";
import { useSearchParams } from "next/navigation";
import { Countdown } from "./Countdown";
import { StreamPanel, Tape, WorldPanel } from "./Panels";

const MODULES = ["TODAY", "WASHINGTON", "NEWS", "MARKETS", "STOCK", "PORTFOLIO", "POLYMARKET"];
const BOOT = ["HANDSHAKE", "7 MODULES MOUNTED", "AUTHORIZATION REQUIRED"];

const delay = (i: number, base = 0, step = 0.12) => ({ "--d": `${base + i * step}s` }) as CSSProperties;

export function LoginForm({ next, error }: { next: string; error: boolean }) {
  const [busy, setBusy] = useState(false);
  const state = busy ? "verify" : error ? "denied" : "locked";

  return (
    <>
      <Tape />
      <div className="lg-main">
        <WorldPanel />
        <section className={`lg-card ${error && !busy ? "lg-denied" : ""}`} aria-labelledby="signin">
          <header className="lg-head">
            <div className="lg-mark" role="img" aria-label="SM">
              <span />
              <span />
              <span />
            </div>
            <div>
              <h1 id="signin" className="lg-name" data-text="THE HUB">
                THE HUB
              </h1>
              <p className="m lg-type">INVESTMENT TERMINAL · POLICY → MARKETS</p>
            </div>
          </header>

          <ol className="m lg-boot" aria-hidden>
            {BOOT.map((text, i) => (
              <li key={text} style={delay(i, 0.5, 0.35)}>
                <span className="dim">[{String(i).padStart(2, "0")}]</span> {text}
                {i === BOOT.length - 1 ? (
                  <span className={`lg-cursor ${error && !busy ? "lg-cursor-dn" : ""}`} />
                ) : (
                  <span className="up"> ✓</span>
                )}
              </li>
            ))}
          </ol>

          <form method="post" action="/auth/login" onSubmit={() => setBusy(true)} className="lg-form">
            <input type="hidden" name="next" value={next} />
            <label htmlFor="password" className="m">
              <span>LOGIN</span>
              <span className="dim">SITE PASSWORD</span>
            </label>
            <div className="lg-prompt">
              <span className="m" aria-hidden>
                PWD&gt;
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
                ✕ ACCESS DENIED · THAT PASSWORD ISN’T RIGHT
              </p>
            ) : null}
            <button type="submit" disabled={busy} className="m lg-go">
              {busy ? (
                <>
                  AUTHENTICATING<span className="lg-dots" />
                </>
              ) : (
                <>
                  SIGN IN <kbd>&lt;GO&gt;</kbd>
                </>
              )}
            </button>
            {busy ? <div className="lg-progress" aria-hidden /> : null}
          </form>

          <Countdown />
        </section>
        <StreamPanel />
      </div>

      <nav className="lg-keys m" aria-label="Pages behind the sign-in">
        {MODULES.map((m, i) => (
          <span key={m} style={delay(i, 1.2, 0.06)} data-state={state}>
            <b>{i + 1}</b>
            {m}
            <em>{state === "verify" ? "···" : state === "denied" ? "DENIED" : "LOCKED"}</em>
          </span>
        ))}
      </nav>
    </>
  );
}

export function LoginFromUrl() {
  const params = useSearchParams();
  return <LoginForm next={params.get("next") ?? "/"} error={params.get("error") === "1"} />;
}
