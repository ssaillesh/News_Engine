"use client";

import { Suspense } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { TickerSearch } from "./TickerSearch";

const LINKS = [
  { href: "/", label: "Dashboard" },
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

// usePathname suspends on routes with unknown dynamic params (/ticker/[symbol])
// under Cache Components, so only this piece sits behind a boundary.
function ActiveLinks() {
  return <Links path={usePathname()} />;
}

export function Nav() {
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
        <Suspense fallback={<Links path={null} />}>
          <ActiveLinks />
        </Suspense>
        <TickerSearch className="ml-auto w-full sm:w-72" />
      </div>
    </header>
  );
}
