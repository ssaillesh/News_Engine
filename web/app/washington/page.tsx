import type { Metadata } from "next";
import { WashingtonView } from "./WashingtonView";

export const metadata: Metadata = { title: "Washington" };

export default function Page() {
  return <WashingtonView />;
}
