import { Suspense } from "react";
import type { Metadata } from "next";
import { NewsSkeleton, NewsView } from "./NewsView";

export const metadata: Metadata = { title: "News" };

export default function Page() {
  // Filters and the selected story live in the URL, which is request-time data.
  return (
    <Suspense fallback={<NewsSkeleton />}>
      <NewsView />
    </Suspense>
  );
}
