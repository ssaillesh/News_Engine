"use client";

import { useEffect, useRef } from "react";

/** Decorative only: faint random-walk lines drifting slowly behind the brand panel.
 *  No real prices are drawn. Static under prefers-reduced-motion. */
export function Backdrop() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const STEP = 8;
    let w = 0;
    let h = 0;
    let raf = 0;
    let frame = 0;
    let offset = 0;
    let amb = "#fb8b1e";
    let rule = "#262626";

    const readColors = () => {
      const cs = getComputedStyle(document.documentElement);
      amb = cs.getPropertyValue("--amb").trim() || amb;
      rule = cs.getPropertyValue("--rule").trim() || rule;
    };

    type Series = { ys: number[]; base: number; vol: number; alpha: number };
    let series: Series[] = [];
    const walk = (sr: Series, prev: number) => prev + (sr.base - prev) * 0.015 + (Math.random() - 0.5) * sr.vol;

    const seed = () => {
      const n = Math.ceil(w / STEP) + 3;
      series = [0.66, 0.8, 0.92].map((b, i) => {
        const sr: Series = { ys: [], base: h * b, vol: 5 + i * 2, alpha: i === 1 ? 0.32 : 0.12 };
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
      ctx.strokeStyle = rule;
      ctx.globalAlpha = 0.5;
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let y = 64; y < h; y += 64) {
        ctx.moveTo(0, y + 0.5);
        ctx.lineTo(w, y + 0.5);
      }
      ctx.stroke();

      for (const sr of series) {
        ctx.globalAlpha = sr.alpha;
        ctx.strokeStyle = amb;
        ctx.lineWidth = 1.25;
        ctx.beginPath();
        sr.ys.forEach((y, i) => (i ? ctx.lineTo(i * STEP - offset, y) : ctx.moveTo(-offset, y)));
        ctx.stroke();
      }
      // Soft fill under the middle line.
      const lead = series[1];
      if (lead) {
        const grad = ctx.createLinearGradient(0, lead.base - 60, 0, h);
        grad.addColorStop(0, amb);
        grad.addColorStop(1, "transparent");
        ctx.globalAlpha = 0.06;
        ctx.fillStyle = grad;
        ctx.beginPath();
        lead.ys.forEach((y, i) => (i ? ctx.lineTo(i * STEP - offset, y) : ctx.moveTo(-offset, y)));
        ctx.lineTo((lead.ys.length - 1) * STEP - offset, h);
        ctx.lineTo(-offset, h);
        ctx.closePath();
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    };

    const tick = () => {
      frame++;
      if (frame % 120 === 1) readColors();
      offset += 0.2;
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

    readColors();
    resize();
    const ro = new ResizeObserver(() => {
      resize();
      if (still) draw();
    });
    ro.observe(canvas);
    if (still) draw();
    else raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return <canvas ref={ref} className="lg-canvas" aria-hidden />;
}
