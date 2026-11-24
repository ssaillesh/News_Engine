"use client";

import { useEffect, useRef } from "react";

/** Decorative only: random-walk price lines drifting left behind the sign-in card,
 *  with a chart crosshair that follows the pointer. No real data is shown here. */
export function Backdrop() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const STEP = 7; // px between points
    let w = 0;
    let h = 0;
    let frame = 0;
    let raf = 0;
    let offset = 0;
    const pointer = { x: -1, y: -1 };
    let colors = { amb: "#fb8b1e", rule: "#262626", hot: "#ffd23f" };

    const readColors = () => {
      const cs = getComputedStyle(document.documentElement);
      colors = {
        amb: cs.getPropertyValue("--amb").trim() || colors.amb,
        rule: cs.getPropertyValue("--rule").trim() || colors.rule,
        hot: cs.getPropertyValue("--hot").trim() || colors.hot,
      };
    };

    type Series = { ys: number[]; base: number; vol: number; alpha: number; width: number; drift: number };
    let series: Series[] = [];

    const walk = (sr: Series, prev: number) => {
      // Mean-reverting random walk so lines wander but stay in their band.
      const pull = (sr.base - prev) * 0.02;
      return prev + pull + sr.drift + (Math.random() - 0.5) * sr.vol;
    };

    const seed = () => {
      const n = Math.ceil(w / STEP) + 3;
      const bands = [0.22, 0.38, 0.55, 0.7, 0.84];
      series = bands.map((b, i) => {
        const sr: Series = {
          ys: [],
          base: h * b,
          vol: 6 + i * 2.5,
          alpha: i === 2 ? 0.55 : 0.12 + i * 0.03,
          width: i === 2 ? 1.6 : 1,
          drift: 0,
        };
        let y = sr.base;
        for (let k = 0; k < n; k++) sr.ys.push((y = walk(sr, y)));
        return sr;
      });
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
    };

    const draw = () => {
      ctx.clearRect(0, 0, w, h);

      // Faint chart grid that scrolls with the lines.
      ctx.strokeStyle = colors.rule;
      ctx.globalAlpha = 0.55;
      ctx.lineWidth = 1;
      ctx.beginPath();
      const G = 56;
      for (let x = -((offset * 1) % G); x < w; x += G) {
        ctx.moveTo(Math.round(x) + 0.5, 0);
        ctx.lineTo(Math.round(x) + 0.5, h);
      }
      for (let y = G; y < h; y += G) {
        ctx.moveTo(0, y + 0.5);
        ctx.lineTo(w, y + 0.5);
      }
      ctx.stroke();

      for (const sr of series) {
        ctx.globalAlpha = sr.alpha;
        ctx.strokeStyle = colors.amb;
        ctx.lineWidth = sr.width;
        ctx.beginPath();
        sr.ys.forEach((y, i) => {
          const x = i * STEP - offset;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();

        if (sr.width > 1) {
          // Area fill under the lead line, plus a live "last price" dot.
          const grad = ctx.createLinearGradient(0, sr.base - 80, 0, h);
          grad.addColorStop(0, colors.amb);
          grad.addColorStop(1, "transparent");
          ctx.globalAlpha = 0.08;
          ctx.fillStyle = grad;
          ctx.lineTo((sr.ys.length - 1) * STEP - offset, h);
          ctx.lineTo(-offset, h);
          ctx.closePath();
          ctx.fill();

          const lx = (sr.ys.length - 3) * STEP - offset;
          const ly = sr.ys[sr.ys.length - 3];
          ctx.globalAlpha = 0.9;
          ctx.fillStyle = colors.hot;
          ctx.beginPath();
          ctx.arc(Math.min(lx, w - 6), ly, 2.5, 0, Math.PI * 2);
          ctx.fill();
          ctx.globalAlpha = 0.25 + 0.2 * Math.sin(frame / 12);
          ctx.beginPath();
          ctx.arc(Math.min(lx, w - 6), ly, 7, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Crosshair, like hovering a chart.
      if (pointer.x >= 0) {
        ctx.globalAlpha = 0.35;
        ctx.strokeStyle = colors.amb;
        ctx.setLineDash([3, 4]);
        ctx.beginPath();
        ctx.moveTo(pointer.x + 0.5, 0);
        ctx.lineTo(pointer.x + 0.5, h);
        ctx.moveTo(0, pointer.y + 0.5);
        ctx.lineTo(w, pointer.y + 0.5);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      ctx.globalAlpha = 1;
    };

    const tick = () => {
      frame++;
      if (frame % 90 === 1) readColors();
      offset += 0.45;
      if (offset >= STEP) {
        offset -= STEP;
        for (const sr of series) {
          sr.ys.shift();
          sr.ys.push(walk(sr, sr.ys[sr.ys.length - 1]));
        }
      }
      draw();
      raf = requestAnimationFrame(tick);
    };

    const onMove = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect();
      pointer.x = e.clientX - r.left;
      pointer.y = e.clientY - r.top;
      if (still) draw();
    };
    const onLeave = () => {
      pointer.x = pointer.y = -1;
      if (still) draw();
    };

    readColors();
    resize();
    const ro = new ResizeObserver(() => {
      resize();
      if (still) draw();
    });
    ro.observe(canvas);
    window.addEventListener("pointermove", onMove);
    document.addEventListener("pointerleave", onLeave);
    if (still) draw();
    else raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  return <canvas ref={ref} className="lg-canvas" aria-hidden />;
}
