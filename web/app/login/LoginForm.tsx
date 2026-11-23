"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { buttonCls, inputCls } from "@/components/ui";

export function LoginForm({ next, error }: { next: string; error: boolean }) {
  const [busy, setBusy] = useState(false);
  return (
    <form method="post" action="/auth/login" onSubmit={() => setBusy(true)} className="mt-5 space-y-3">
      <input type="hidden" name="next" value={next} />
      <label className="flex flex-col gap-1 text-xs text-muted">
        Password
        <input
          type="password"
          name="password"
          required
          autoFocus
          autoComplete="current-password"
          className={inputCls}
          aria-invalid={error || undefined}
        />
      </label>
      {error ? (
        <p role="alert" className="text-xs text-down">
          That password isn’t right.
        </p>
      ) : null}
      <button type="submit" disabled={busy} className={`${buttonCls.primary} w-full`}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

export function LoginFromUrl() {
  const params = useSearchParams();
  return <LoginForm next={params.get("next") ?? "/"} error={params.get("error") === "1"} />;
}
