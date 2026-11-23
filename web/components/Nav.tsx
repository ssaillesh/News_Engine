"use client";

import { Suspense } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { TickerSearch } from "./TickerSearch";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/markets", label: "Markets" },
  { href: "/news", label: "News" },
  { href: "/portfolio", label: "Portfolio" },
] as const;

function Links({ path }: { path: string | null }) {
  return (
    <nav className="flex items-center gap-1 text-sm">
      {LINKS.map((l) => {
        const active = path !== null && (l.href === "/" ? path === "/" : path.startsWith(l.href));
        return (
          <Link
            key={l.href}
            href={l.href}
            aria-current={active ? "page" : undefined}
            className={`rounded-md px-2.5 py-1 font-medium ${active ? "bg-surface-2 text-text" : "text-muted hover:text-text"}`}
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}

function Controls({ path, signOut }: { path: string | null; signOut: boolean }) {
  if (path === "/login") return null; // signed out: nothing here would work yet
  return (
    <>
      <Links path={path} />
      <div className="ml-auto flex w-full items-center gap-2 sm:w-auto">
        <TickerSearch className="flex-1 sm:w-72" />
        {signOut ? (
          <form method="post" action="/auth/logout">
            <button type="submit" className="rounded-md px-2 py-1.5 text-xs font-medium text-muted hover:bg-surface-2 hover:text-text">
              Sign out
            </button>
          </form>
        ) : null}
      </div>
    </>
  );
}

// usePathname suspends on routes with unknown dynamic params (/ticker/[symbol])
// under Cache Components, so only this piece sits behind a boundary.
function ActiveControls({ signOut }: { signOut: boolean }) {
  return <Controls path={usePathname()} signOut={signOut} />;
}

export function Nav({ signOut = false }: { signOut?: boolean }) {
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-surface/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden className="text-accent">
            <path
              d="M2 15 L7 9 L11 12 L18 4"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Hub
        </Link>
        <Suspense fallback={<Controls path={null} signOut={signOut} />}>
          <ActiveControls signOut={signOut} />
        </Suspense>
      </div>
    </header>
  );
}
