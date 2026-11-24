"use client";

import { useEffect, useState } from "react";
import { EXCHANGES, status, useTick, type Status } from "./exchanges";

const DOT: Record<Status, string> = { OPEN: "up", LUNCH: "amb", CLOSED: "dn" };

/** Scrolling tape of world exchanges with their real local time and session state. */
export function Tape() {
  const now = useTick(1000);
  const items = EXCHANGES.map((ex) => {
    const st = now === null ? null : status(ex, now);
    return (
      <span key={ex.code} className="lg-tick">
        <b>{ex.code}</b>
        <span className="dim">{st ? st.clock.slice(0, 5) : "--:--"}</span>
        {st ? <span className={DOT[st.status]}>● {st.status}</span> : null}
      </span>
    );
  });
  return (
    <div className="lg-tape m" aria-hidden>
      {/* Two copies so the loop is seamless. */}
      <div className="lg-tape-run">
        {items}
        {items}
      </div>
    </div>
  );
}

/** WCLK-style board: every exchange's local time and whether it is trading. */
export function WorldPanel() {
  const now = useTick(1000);
  const open = now === null ? 0 : EXCHANGES.filter((ex) => status(ex, now).status === "OPEN").length;
  return (
    <aside className="lg-panel m" aria-label="World markets">
      <div className="tb">
        <span>WCLK · WORLD MARKETS</span>
        <span>
          {open}/{EXCHANGES.length} OPEN
        </span>
      </div>
      <table className="lg-wclk">
        <tbody>
          {EXCHANGES.map((ex) => {
            const st = now === null ? null : status(ex, now);
            return (
              <tr key={ex.code}>
                <td className="amb">{ex.code}</td>
                <td className="dim">{ex.city}</td>
                <td>{st?.clock ?? "--:--:--"}</td>
                <td className={st ? DOT[st.status] : "dim"}>{st?.status ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="lg-foot dim">REGULAR SESSIONS · LOCAL TIME · HOLIDAYS NOT SHOWN</p>
    </aside>
  );
}

// ── decorative hex stream ────────────────────────────────────────────────
const HEX = "0123456789abcdef";
const PRINT = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$#%&*+=<>?";
const rnd = (n: number) => Math.floor(Math.random() * n);

function line(addr: number) {
  const bytes = Array.from({ length: 8 }, () => HEX[rnd(16)] + HEX[rnd(16)]);
  const ascii = Array.from({ length: 8 }, () => (Math.random() < 0.35 ? "." : PRINT[rnd(PRINT.length)])).join("");
  return { addr: addr.toString(16).padStart(6, "0"), bytes, ascii, hot: rnd(8) };
}

const ROWS = 20;

/** Pure noise styled as a packet dump: it carries no data, it is there for the look. */
export function StreamPanel() {
  const [rows, setRows] = useState<ReturnType<typeof line>[]>([]);
  const [addr, setAddr] = useState(0);

  useEffect(() => {
    let a = rnd(0xffff) * 16;
    const fill = () => Array.from({ length: ROWS }, (_, i) => line(a + i * 8));
    // Random bytes exist only in the browser, so the first fill waits for mount.
    const first = setTimeout(() => setRows(fill()), 0);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return () => clearTimeout(first);
    const id = setInterval(() => {
      a += 8;
      setAddr(a);
      setRows((r) => [...r.slice(1), line(a + ROWS * 8)]);
    }, 140);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, []);

  return (
    <aside className="lg-panel m" aria-hidden>
      <div className="tb">
        <span>SYS · SECURE CHANNEL</span>
        <span>0x{addr.toString(16).padStart(6, "0")}</span>
      </div>
      <div className="lg-hex">
        {rows.map((r, i) => (
          <div key={r.addr + i}>
            <span className="dim">{r.addr}</span>
            <span>
              {r.bytes.map((b, j) => (
                <span key={j} className={j === r.hot ? "amb" : undefined}>
                  {b}{" "}
                </span>
              ))}
            </span>
            <span className="dim">{r.ascii}</span>
          </div>
        ))}
      </div>
      <p className="lg-foot dim">
        NOISE ONLY · SESSION: HTTP-ONLY COOKIE, 30 DAYS
      </p>
    </aside>
  );
}
