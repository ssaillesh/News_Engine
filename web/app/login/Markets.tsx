"use client";

import { EXCHANGES, nextBell, status, useTick, type Status } from "./exchanges";

const SHOWN = ["NYSE", "TSX", "LSE", "XETRA", "EURONEXT", "TSE", "HKEX", "ASX"];
const BOARD = EXCHANGES.filter((ex) => SHOWN.includes(ex.code));
const TONE: Record<Status, string> = { OPEN: "open", LUNCH: "lunch", CLOSED: "closed" };
const WORD: Record<Status, string> = { OPEN: "Open", LUNCH: "Lunch", CLOSED: "Closed" };

/** A band of world exchanges: local time and session state, worked out from each
 *  exchange's regular hours in the browser (no API call, holidays not modelled). */
export function MarketsBand() {
  const now = useTick(15_000);
  const open = now === null ? null : BOARD.filter((ex) => status(ex, now).status === "OPEN").length;
  return (
    <section className="lg-band" aria-label="World markets">
      <div className="lg-band-head">
        <span className="lg-eyebrow">World markets</span>
        <span className="lg-band-sum">
          {now === null ? " " : `${open} of ${BOARD.length} open · NYSE ${nextBell(BOARD[0], now).toLowerCase()}`}
        </span>
      </div>
      <ul>
        {BOARD.map((ex) => {
          const st = now === null ? null : status(ex, now);
          return (
            <li key={ex.code}>
              <span className="lg-band-code">
                <i className={`lg-dot ${st ? TONE[st.status] : ""}`} aria-hidden />
                {ex.code}
              </span>
              <span className="lg-band-city">{ex.city.toLowerCase()}</span>
              <span className="lg-band-time m">{st ? st.clock.slice(0, 5) : "--:--"}</span>
              <span className={`lg-band-state ${st ? TONE[st.status] : ""}`}>{st ? WORD[st.status] : " "}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
