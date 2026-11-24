"use client";

import { useState, type KeyboardEvent } from "react";
import { useSearchParams } from "next/navigation";

/** The password form. A plain POST, so it works before JavaScript loads. */
export function SignInForm({ next, error }: { next: string; error: boolean }) {
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);
  const [caps, setCaps] = useState(false);
  const failed = error && !busy;
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => setCaps(e.getModifierState?.("CapsLock") ?? false);

  return (
    <form method="post" action="/auth/login" onSubmit={() => setBusy(true)} className="lg-form">
      <input type="hidden" name="next" value={next} />
      <label htmlFor="password">Access password</label>
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
          <>
            Enter The Hub <span aria-hidden>→</span>
          </>
        )}
      </button>
    </form>
  );
}

export function SignInFromUrl() {
  const params = useSearchParams();
  return <SignInForm next={params.get("next") ?? "/"} error={params.get("error") === "1"} />;
}

/** Scrolls back to the form and puts the cursor in the password field. */
export function SignInButton({ children }: { children: React.ReactNode }) {
  return (
    <button
      type="button"
      className="lg-cta"
      onClick={() => {
        const input = document.getElementById("password");
        input?.scrollIntoView({ behavior: "smooth", block: "center" });
        input?.focus({ preventScroll: true });
      }}
    >
      {children}
    </button>
  );
}
