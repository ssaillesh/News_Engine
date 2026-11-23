import { Suspense } from "react";
import type { Metadata } from "next";
import { LoginForm, LoginFromUrl } from "./LoginForm";

export const metadata: Metadata = { title: "Sign in" };

export default function Page() {
  return (
    <div className="grid min-h-[60vh] place-items-center">
      <div className="w-full max-w-sm rounded-xl border border-border bg-surface p-6">
        <h1 className="text-lg font-semibold tracking-tight">Sign in</h1>
        <p className="mt-1 text-sm text-muted">This hub is private. Enter the site password to continue.</p>
        {/* ?next and ?error are request-time data, so they are read behind a boundary. */}
        <Suspense fallback={<LoginForm next="/" error={false} />}>
          <LoginFromUrl />
        </Suspense>
      </div>
    </div>
  );
}
