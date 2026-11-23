import type { Metadata } from "next";
import { PortfolioView } from "./PortfolioView";

export const metadata: Metadata = { title: "Portfolio" };

export default function Page() {
  return <PortfolioView />;
}
