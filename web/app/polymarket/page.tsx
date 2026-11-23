import type { Metadata } from "next";
import { PolymarketView } from "./PolymarketView";

export const metadata: Metadata = { title: "Polymarket" };

export default function Page() {
  return <PolymarketView />;
}
