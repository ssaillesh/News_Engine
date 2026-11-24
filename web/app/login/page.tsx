import { Suspense } from "react";
import type { Metadata } from "next";
import { Backdrop } from "./Backdrop";
import { LoginForm, LoginFromUrl } from "./LoginForm";
import "./login.css";

export const metadata: Metadata = { title: "Sign in" };

export default function Page() {
  return (
    <div className="lg-stage">
      <Backdrop />
      <div className="lg-crt" aria-hidden />
      {/* ?next and ?error are request-time data, so they are read behind a boundary. */}
      <Suspense fallback={<LoginForm next="/" error={false} />}>
        <LoginFromUrl />
      </Suspense>
    </div>
  );
}
