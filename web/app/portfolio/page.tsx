import { Suspense } from "react";
import type { Metadata } from "next";
import { PortfolioSkeleton, PortfolioView } from "./PortfolioView";

export const metadata: Metadata = { title: "Portfolio" };

export default function Page() {
  // ?add=TICKER (from a stock page) is request-time data.
  return (
    <Suspense fallback={<PortfolioSkeleton />}>
      <PortfolioView />
    </Suspense>
  );
}
