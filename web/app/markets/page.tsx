import { Suspense } from "react";
import type { Metadata } from "next";
import { MarketsSkeleton, MarketsView } from "./MarketsView";

export const metadata: Metadata = { title: "Markets" };

export default function Page() {
  // Filters, sort and page live in the URL, which is request-time data.
  return (
    <Suspense fallback={<MarketsSkeleton />}>
      <MarketsView />
    </Suspense>
  );
}
