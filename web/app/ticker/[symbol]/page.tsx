import { Suspense } from "react";
import { TickerView, TickerSkeleton } from "./TickerView";

// The symbol is runtime data (no generateStaticParams), so reading it sits
// behind a Suspense boundary and the page shell still prerenders.
async function Ticker({ params }: { params: PageProps<"/ticker/[symbol]">["params"] }) {
  const { symbol } = await params;
  return <TickerView symbol={decodeURIComponent(symbol).toUpperCase()} />;
}

export default function Page({ params }: PageProps<"/ticker/[symbol]">) {
  return (
    <Suspense fallback={<TickerSkeleton />}>
      <Ticker params={params} />
    </Suspense>
  );
}
