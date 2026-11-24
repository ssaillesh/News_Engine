"use client";

import { EXCHANGES, nextBell, status, useTick } from "./exchanges";

const NYSE = EXCHANGES[0];

/** One quiet line under the card: is New York trading, and when does that change.
 *  Worked out from regular hours in the browser; holidays are not modelled. */
export function MarketLine() {
  const now = useTick(15_000);
  if (now === null) return <p className="lg-market" style={{ visibility: "hidden" }}>&nbsp;</p>;
  const st = status(NYSE, now);
  const open = st.status === "OPEN";
  return (
    <p className="lg-market">
      <i className={`lg-dot ${open ? "open" : "closed"}`} aria-hidden />
      NYSE {open ? "open" : st.status === "LUNCH" ? "paused" : "closed"}
      <span aria-hidden> · </span>
      {nextBell(NYSE, now).toLowerCase()}
    </p>
  );
}
