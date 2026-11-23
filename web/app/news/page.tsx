import { Suspense } from "react";
import type { Metadata } from "next";
import { NewsFeed } from "./NewsFeed";
import { NewsSkeleton } from "@/components/News";

export const metadata: Metadata = { title: "News" };

export default function Page() {
  return (
    <Suspense fallback={<NewsSkeleton rows={6} />}>
      <NewsFeed />
    </Suspense>
  );
}
