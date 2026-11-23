import { Suspense } from "react";
import type { Metadata } from "next";
import { LoginForm, LoginFromUrl } from "./LoginForm";

export const metadata: Metadata = { title: "Sign in" };

export default function Page() {
  return (
    <div style={{ flex: 1, display: "grid", placeItems: "center", padding: 16 }}>
      <section className="pane" style={{ width: "100%", maxWidth: 380, border: "1px solid var(--rule)" }} aria-labelledby="signin">
        <div className="tb">
          <h1 id="signin" style={{ margin: 0, font: "inherit" }}>
            Sign in
          </h1>
          <span>PRIVATE</span>
        </div>
        <p className="dim" style={{ margin: 0, padding: "12px 12px 0", fontSize: 13 }}>
          This hub is private. Enter the site password to continue.
        </p>
        {/* ?next and ?error are request-time data, so they are read behind a boundary. */}
        <Suspense fallback={<LoginForm next="/" error={false} />}>
          <LoginFromUrl />
        </Suspense>
      </section>
    </div>
  );
}
