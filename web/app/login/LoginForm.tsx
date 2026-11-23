"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";

export function LoginForm({ next, error }: { next: string; error: boolean }) {
  const [busy, setBusy] = useState(false);
  return (
    <form method="post" action="/auth/login" onSubmit={() => setBusy(true)} style={{ padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
      <input type="hidden" name="next" value={next} />
      <label htmlFor="password" className="m dim" style={{ fontSize: 11 }}>
        SITE PASSWORD
      </label>
      <input
        id="password"
        type="password"
        name="password"
        required
        autoFocus
        autoComplete="current-password"
        className="fld"
        style={{ width: "100%", fontSize: 14, padding: "6px 8px" }}
        aria-invalid={error || undefined}
      />
      {error ? (
        <p role="alert" className="m dn" style={{ fontSize: 11, margin: 0 }}>
          THAT PASSWORD ISN’T RIGHT.
        </p>
      ) : null}
      <button type="submit" disabled={busy} className="btn on" style={{ justifyContent: "center" }}>
        {busy ? "SIGNING IN…" : "SIGN IN ›"}
      </button>
    </form>
  );
}

export function LoginFromUrl() {
  const params = useSearchParams();
  return <LoginForm next={params.get("next") ?? "/"} error={params.get("error") === "1"} />;
}
