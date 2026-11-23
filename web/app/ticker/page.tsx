"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { LAST_TICKER_KEY } from "@/components/Shell";
import { SkRows } from "@/components/term";

/** "5 STOCK" with no symbol: reopen the last ticker viewed (SPY the first time). */
export default function LastTicker() {
  const router = useRouter();
  useEffect(() => {
    let t = "SPY";
    try {
      t = localStorage.getItem(LAST_TICKER_KEY) || t;
    } catch {}
    router.replace(`/ticker/${encodeURIComponent(t)}`);
  }, [router]);
  return <SkRows rows={4} />;
}
