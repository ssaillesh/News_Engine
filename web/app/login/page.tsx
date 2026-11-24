import { Suspense } from "react";
import type { Metadata } from "next";
import { Backdrop } from "./Backdrop";
import { MarketsBand } from "./Markets";
import { SignInButton, SignInForm, SignInFromUrl } from "./SignIn";
import "./login.css";

export const metadata: Metadata = {
  title: { absolute: "The Hub · From policy to price" },
  description:
    "A private markets terminal linking Washington, the news and prices: every story scored for sentiment and market impact, next to the stocks, sectors and prediction markets it moves.",
};

// What each page behind the sign-in does, in the order of the app's 1–7 keys.
const MODULES = [
  ["Today", "What moved markets in the last 48 hours, sector moves, market odds, the latest from Washington and your watchlist."],
  ["Washington", "Policy focus, market tone and the sectors most affected by executive action, with the latest Federal Register filings."],
  ["News", "Every story ranked by impact, with a breakdown of why it scored that way and how the market reacted against SPY."],
  ["Markets", "Cross-asset moves, an S&P 500 sector map, the day’s movers and a screener across thousands of symbols."],
  ["Stock", "Price history with news markers, key stats, peers, and how coverage tracked the price over the last year."],
  ["Portfolio", "Holdings and allocation across NYSE and TSX listings, totalled in Canadian dollars at today’s rate."],
  ["Polymarket", "Prediction-market odds on rates, tariffs, elections and conflicts, matched to the headlines behind them."],
] as const;

const STEPS = [
  ["Collect", "White House releases, presidential documents, Federal Register filings and around twenty news publishers, gathered on a schedule through the day."],
  ["Score", "Each story gets a FinBERT sentiment score and an impact score built from who said it, the topic, how actionable it is and how widely it is reported."],
  ["Connect", "Stories are linked to the stocks and sectors they mention, the price moves that followed, and the prediction markets they bear on."],
] as const;

const FACTS = ["7 modules", "NYSE + TSX", "FinBERT sentiment", "Polymarket odds"];

export default function Page() {
  return (
    <div className="lg-page">
      {/* ── hero ─────────────────────────────────────────────────────── */}
      <section className="lg-hero">
        <Backdrop />
        <div className="lg-hero-grid">
          <div className="lg-title">
            <p className="lg-eyebrow">
              <i className="lg-dot open" aria-hidden /> Policy · News · Markets
            </p>
            <h1>
              <span className="lg-mark" aria-hidden />
              The Hub
            </h1>
            <p className="lg-lead">From policy to price, in one terminal.</p>
            <p className="lg-sub">
              Washington, the news and the markets, linked. Every story is scored for sentiment and market impact and
              shown next to the stocks, sectors and prediction markets it moves.
            </p>
            <ul className="lg-facts" aria-label="At a glance">
              {FACTS.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </div>

          <div className="lg-card" aria-labelledby="signin">
            <h2 id="signin">Sign in</h2>
            <p className="lg-card-sub">The Hub is private. Enter the access password to continue.</p>
            {/* ?next and ?error are request-time data, so the form reads them behind a boundary. */}
            <Suspense fallback={<SignInForm next="/" error={false} />}>
              <SignInFromUrl />
            </Suspense>
            <p className="lg-note">You’ll stay signed in on this device for 30 days.</p>
          </div>
        </div>
        <a href="#inside" className="lg-scroll">
          What’s inside <span aria-hidden>↓</span>
        </a>
      </section>

      <MarketsBand />

      {/* ── modules ──────────────────────────────────────────────────── */}
      <section id="inside" className="lg-section">
        <header className="lg-section-head">
          <p className="lg-eyebrow">Inside the terminal</p>
          <h2>Seven views, one keystroke apart.</h2>
          <p>Press 1 to 7 anywhere in the app to jump between them, or type a ticker into the command line.</p>
        </header>
        <ol className="lg-modules">
          {MODULES.map(([name, desc], i) => (
            <li key={name}>
              <kbd className="m">{i + 1}</kbd>
              <h3>{name}</h3>
              <p>{desc}</p>
            </li>
          ))}
          <li className="lg-module-cmd">
            <kbd className="m">/</kbd>
            <h3>Command line</h3>
            <p>
              Type a ticker or a page name to jump to it, or log a trade with <code className="m">BUY 10 AAPL @ 180</code>.
            </p>
          </li>
        </ol>
      </section>

      {/* ── how it works ─────────────────────────────────────────────── */}
      <section className="lg-section lg-section-alt">
        <header className="lg-section-head">
          <p className="lg-eyebrow">How it works</p>
          <h2>From headline to market move.</h2>
        </header>
        <ol className="lg-steps">
          {STEPS.map(([name, desc], i) => (
            <li key={name}>
              <span className="lg-step-n m">0{i + 1}</span>
              <h3>{name}</h3>
              <p>{desc}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* ── closing call to action ───────────────────────────────────── */}
      <section className="lg-closing">
        <span className="lg-mark lg-mark-lg" aria-hidden />
        <h2>Have access?</h2>
        <p>Sign in with the password you were given.</p>
        <SignInButton>
          Sign in <span aria-hidden>↑</span>
        </SignInButton>
      </section>

      <footer className="lg-footer">
        <span>© The Hub</span>
        <span>Sources include the Federal Register, the White House, Finnhub, Yahoo Finance and Polymarket.</span>
        <span>For information only. Not investment advice.</span>
      </footer>
    </div>
  );
}
