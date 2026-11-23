"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type SeriesType,
  type Time,
} from "lightweight-charts";
import type { Bar, NewsMarker } from "@/lib/api";
import { cls, compact, money, num, pct, sentimentTone, shortDate } from "@/lib/format";

export type ChartMode = "candle" | "area";

/** One marker per trading bar, built from the backend's per-calendar-day markers. */
export type NewsDay = {
  time: string; // the bar the news is drawn on
  dates: string[]; // calendar days folded into it (weekend news lands on Monday)
  count: number;
  sentiment: number | null;
  impact: number | null;
};

type CleanBar = { time: string; open: number; high: number; low: number; close: number; volume: number | null };

function cleanBars(bars: Bar[]): CleanBar[] {
  const out: CleanBar[] = [];
  for (const b of bars) {
    if (b.close === null) continue;
    const open = b.open ?? b.close;
    out.push({
      time: b.date,
      open,
      high: b.high ?? Math.max(open, b.close),
      low: b.low ?? Math.min(open, b.close),
      close: b.close,
      volume: b.volume,
    });
  }
  return out;
}

/**
 * News arrives on calendar days; bars exist only on trading days. Each news day
 * is attached to the first bar on or after it (news over a weekend moves
 * Monday's open), or to the last bar when it is newer than any price.
 */
export function snapNewsDays(bars: CleanBar[], markers: NewsMarker[]): Map<string, NewsDay> {
  const out = new Map<string, NewsDay>();
  if (!bars.length) return out;
  const first = bars[0].time;
  for (const m of markers) {
    if (m.date < first) continue;
    let lo = 0;
    let hi = bars.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (bars[mid].time < m.date) lo = mid + 1;
      else hi = mid;
    }
    const time = bars[Math.min(lo, bars.length - 1)].time;
    const prev = out.get(time);
    if (!prev) {
      out.set(time, { time, dates: [m.date], count: m.count, sentiment: m.avg_sentiment, impact: m.max_impact });
      continue;
    }
    const total = prev.count + m.count;
    const sentiment =
      prev.sentiment === null
        ? m.avg_sentiment
        : m.avg_sentiment === null
          ? prev.sentiment
          : (prev.sentiment * prev.count + m.avg_sentiment * m.count) / total;
    out.set(time, {
      time,
      dates: [...prev.dates, m.date],
      count: total,
      sentiment,
      impact: Math.max(prev.impact ?? 0, m.max_impact ?? 0) || null,
    });
  }
  return out;
}

function timeKey(t: Time | undefined): string | null {
  if (t === undefined) return null;
  if (typeof t === "string") return t;
  if (typeof t === "number") return new Date(t * 1000).toISOString().slice(0, 10);
  const mm = String(t.month).padStart(2, "0");
  const dd = String(t.day).padStart(2, "0");
  return `${t.year}-${mm}-${dd}`;
}

function palette() {
  const s = getComputedStyle(document.documentElement);
  const v = (name: string) => s.getPropertyValue(name).trim();
  return {
    text: v("--dim"),
    border: v("--rule"),
    grid: v("--rule"),
    up: v("--up"),
    down: v("--dn"),
    accent: v("--amb"),
    neutral: v("--dim"),
    ink: v("--ink"),
  };
}

/** Append an alpha byte to #rgb / #rrggbb colours; anything else passes through. */
function alpha(hex: string, a: string) {
  if (/^#[0-9a-f]{3}$/i.test(hex)) hex = "#" + [...hex.slice(1)].map((c) => c + c).join("");
  return /^#[0-9a-f]{6}$/i.test(hex) ? hex + a : hex;
}

export function PriceChart({
  bars,
  markers,
  mode,
  currency = "USD",
  selected,
  onSelectDay,
  height,
}: {
  bars: Bar[];
  markers: NewsMarker[];
  mode: ChartMode;
  currency?: string;
  selected: string | null;
  onSelectDay: (day: NewsDay | null) => void;
  height?: number;
}) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const priceSeries = useRef<ISeriesApi<SeriesType> | null>(null);
  const volumeSeries = useRef<ISeriesApi<"Histogram"> | null>(null);
  const markerApi = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const [theme, setTheme] = useState(0);
  const [hover, setHover] = useState<string | null>(null);

  const data = useMemo(() => cleanBars(bars), [bars]);
  const byTime = useMemo(() => new Map(data.map((b, i) => [b.time, { bar: b, prev: data[i - 1] }])), [data]);
  const newsDays = useMemo(() => snapNewsDays(data, markers), [data, markers]);

  // Latest values for chart event handlers, which are subscribed once.
  const newsRef = useRef(newsDays);
  const selectRef = useRef(onSelectDay);
  const selectedRef = useRef(selected);
  useEffect(() => {
    newsRef.current = newsDays;
    selectRef.current = onSelectDay;
    selectedRef.current = selected;
  });

  // Create the chart once per mount. Hidden routes (Activity) re-run this on return.
  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const c = createChart(el, {
      autoSize: true,
      crosshair: { mode: CrosshairMode.Magnet },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, fixLeftEdge: true, rightOffset: 4 },
      // The chart sits mid-page: leave the wheel to page scrolling, zoom by dragging the axis.
      handleScroll: { mouseWheel: false },
      handleScale: { mouseWheel: false, axisPressedMouseMove: { time: true, price: false } },
    });
    chart.current = c;

    c.subscribeClick((p) => {
      const key = timeKey(p.time);
      if (!key) return;
      const day = newsRef.current.get(key);
      if (!day) return;
      selectRef.current(selectedRef.current === key ? null : day);
    });
    c.subscribeCrosshairMove((p) => setHover(timeKey(p.time)));

    // The header toggle flips data-theme on <html>; recolour when it does.
    const obs = new MutationObserver(() => setTheme((n) => n + 1));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      obs.disconnect();
      c.remove();
      chart.current = null;
      priceSeries.current = null;
      volumeSeries.current = null;
      markerApi.current = null;
    };
  }, []);

  // Theme-dependent chart chrome.
  useEffect(() => {
    const p = palette();
    chart.current?.applyOptions({
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: p.text,
        fontFamily: getComputedStyle(document.body).getPropertyValue("--font-plex-mono") || "ui-monospace, monospace",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: p.grid } },
      crosshair: { vertLine: { color: p.text, labelBackgroundColor: p.accent }, horzLine: { color: p.text, labelBackgroundColor: p.accent } },
    });
  }, [theme]);

  // Series: rebuilt when the data, the chart type or the theme changes.
  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    const p = palette();
    if (priceSeries.current) c.removeSeries(priceSeries.current);
    if (volumeSeries.current) c.removeSeries(volumeSeries.current);
    markerApi.current = null;

    const priceFormat = { type: "price" as const, precision: 2, minMove: 0.01 };
    let series: ISeriesApi<SeriesType>;
    if (mode === "candle") {
      series = c.addSeries(CandlestickSeries, {
        upColor: p.up,
        downColor: p.down,
        borderVisible: false,
        wickUpColor: p.up,
        wickDownColor: p.down,
        priceFormat,
      });
      series.setData(data.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })));
    } else {
      const line = p.accent;
      series = c.addSeries(AreaSeries, {
        lineColor: line,
        lineWidth: 2,
        topColor: alpha(line, "33"),
        bottomColor: alpha(line, "00"),
        priceFormat,
      });
      series.setData(data.map(({ time, close }) => ({ time, value: close })));
    }
    series.priceScale().applyOptions({ scaleMargins: { top: 0.12, bottom: 0.22 } });

    const vol = c.addSeries(HistogramSeries, { priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(
      data
        .filter((b) => b.volume !== null)
        .map((b) => ({ time: b.time, value: b.volume as number, color: alpha(b.close >= b.open ? p.up : p.down, "55") })),
    );

    priceSeries.current = series;
    volumeSeries.current = vol;
    markerApi.current = createSeriesMarkers(series, []);
    c.timeScale().fitContent();
  }, [data, mode, theme]);

  // News markers: coloured by mean sentiment, sized by peak impact.
  useEffect(() => {
    const api = markerApi.current;
    if (!api) return;
    const p = palette();
    const list: SeriesMarker<Time>[] = [...newsDays.values()].map((d) => {
      const isSel = d.time === selected;
      const t = sentimentTone(d.sentiment);
      return {
        time: d.time,
        position: "aboveBar",
        shape: "circle",
        // Selected: ink. High impact (70+): amber. Otherwise by mean sentiment.
        color: isSel ? p.ink : (d.impact ?? 0) >= 0.7 ? p.accent : t === "up" ? p.up : t === "down" ? p.down : p.neutral,
        size: (isSel ? 1.25 : 0.9) + Math.min(1, d.impact ?? 0) * 0.6,
        text: String(d.count),
        id: d.time,
      };
    });
    api.setMarkers(list);
  }, [newsDays, selected, data, mode, theme]);

  const legendKey = hover ?? data[data.length - 1]?.time ?? null;
  const legend = legendKey ? byTime.get(legendKey) : undefined;
  const legendNews = legendKey ? newsDays.get(legendKey) : undefined;
  const dayChange = legend?.prev ? ((legend.bar.close - legend.prev.close) / legend.prev.close) * 100 : null;

  const newsCls = legendNews ? { up: "up", down: "dn", flat: "dim" }[sentimentTone(legendNews.sentiment)] : "";
  return (
    <div style={{ position: "relative", height: height ?? "100%", minHeight: 260 }}>
      <div ref={container} style={{ position: "absolute", inset: 0 }} />
      {legend ? (
        <div
          className="m dim"
          style={{ pointerEvents: "none", position: "absolute", left: 8, top: 4, zIndex: 10, display: "flex", flexWrap: "wrap", gap: "2px 12px", alignItems: "baseline", background: "color-mix(in srgb, var(--pane) 85%, transparent)", padding: "2px 6px", fontSize: 11 }}
        >
          <span style={{ color: "var(--ink)" }}>{shortDate(legend.bar.time).toUpperCase()}</span>
          <span>O {num(legend.bar.open)}</span>
          <span>H {num(legend.bar.high)}</span>
          <span>L {num(legend.bar.low)}</span>
          <span style={{ color: "var(--ink)" }}>C {money(legend.bar.close, currency)}</span>
          <span className={cls(dayChange)}>{pct(dayChange)}</span>
          {legend.bar.volume !== null ? <span>VOL {compact(legend.bar.volume)}</span> : null}
          {legendNews ? (
            <span className={newsCls}>
              {legendNews.count} {legendNews.count === 1 ? "STORY" : "STORIES"} · CLICK TO FILTER
            </span>
          ) : null}
        </div>
      ) : null}
      {!data.length ? (
        <div className="m dim" style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", fontSize: 12 }}>
          NO PRICE HISTORY FOR THIS RANGE.
        </div>
      ) : null}
    </div>
  );
}
