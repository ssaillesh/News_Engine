import { Suspense } from "react";
import type { Metadata } from "next";
import { Backdrop } from "./Backdrop";
import { MarketLine } from "./MarketLine";
import { SignInForm, SignInFromUrl } from "./SignIn";
import "./login.css";

export const metadata: Metadata = { title: { absolute: "Sign in · The Hub" } };

export default function Page() {
  return (
    <div className="lg-stage">
      <Backdrop />
      <div className="lg-center">
        <header className="lg-brand">
          <span className="lg-mark" aria-hidden />
          <h1>The Hub</h1>
          <p>From policy to price, in one terminal.</p>
        </header>

        <section className="lg-card" aria-label="Sign in">
          {/* ?next and ?error are request-time data, so the form reads them behind a boundary. */}
          <Suspense fallback={<SignInForm next="/" error={false} />}>
            <SignInFromUrl />
          </Suspense>
          <p className="lg-note">Private access. You’ll stay signed in on this device for 30 days.</p>
        </section>

        <MarketLine />
      </div>
      <footer className="lg-legal">For information only. Not investment advice.</footer>
    </div>
  );
}
