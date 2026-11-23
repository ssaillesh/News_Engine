import { useSyncExternalStore } from "react";

const noop = () => () => {};
const label = () => new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });

/** Today's date, rendered only in the browser so prerendered HTML never bakes in a stale day. */
export function useToday(): string | null {
  return useSyncExternalStore(noop, label, () => null);
}
