import type { NewsItem } from "./api";
import { sentimentTone } from "./format";

/** Washington's own output: White House releases, presidential documents, the Federal Register. */
export const WASHINGTON_SOURCES = ["whitehouse", "presidential_documents", "federal_register"];

/** News-page source filters → the `source` values they cover. */
export const SOURCE_FILTERS = [
  { key: "all", label: "ALL", sources: [] as string[] },
  { key: "wh", label: "WHITE HOUSE", sources: ["whitehouse", "presidential_documents"] },
  { key: "fr", label: "FED REGISTER", sources: ["federal_register"] },
  { key: "co", label: "COMPANY", sources: ["market_news"] },
  { key: "press", label: "PRESS", sources: ["news"] },
] as const;
export type SourceFilter = (typeof SOURCE_FILTERS)[number]["key"];

const SHORT: Record<string, string> = {
  whitehouse: "WH",
  presidential_documents: "PD",
  federal_register: "FR",
  market_news: "CO",
};
const LONG: Record<string, string> = {
  whitehouse: "WHITE HOUSE",
  presidential_documents: "PRESIDENTIAL DOCUMENTS",
  federal_register: "FEDERAL REGISTER",
  market_news: "COMPANY NEWS",
};

/** Short source code for dense rows: WH, FR, CO, or the publisher. */
export function srcShort(item: NewsItem) {
  return SHORT[item.source] ?? (item.publisher || item.kind || item.source).toUpperCase();
}

export function srcLong(item: NewsItem) {
  return LONG[item.source] ?? (item.publisher || item.kind || item.source).toUpperCase();
}

/** Document type for Washington items: "EXEC ORDER", "PROCLAMATION", "FACT SHEET"… */
export function kindShort(kind: string | null | undefined) {
  if (!kind) return "DOCUMENT";
  const k = kind.toUpperCase();
  const map: Record<string, string> = {
    "EXECUTIVE ORDER": "EXEC ORDER",
    "BRIEFINGS & STATEMENTS": "STATEMENT",
    "FACT SHEETS": "FACT SHEET",
    "PRESIDENTIAL ACTIONS": "ACTION",
    RELEASES: "RELEASE",
    MEMORANDUM: "MEMO",
    PRESDOC: "DOCUMENT",
  };
  return map[k] ?? k;
}

/** Washington type filters → the `kind` values they cover across sources. */
export const ACTION_TYPES = [
  { key: "all", label: "ALL", kinds: [] as string[] },
  { key: "eo", label: "EXEC ORDERS", kinds: ["Executive Order"] },
  { key: "proc", label: "PROCLAMATIONS", kinds: ["Proclamation"] },
  { key: "stmt", label: "STATEMENTS", kinds: ["Briefings & Statements", "Statement", "Remarks", "Message"] },
  { key: "memo", label: "MEMOS", kinds: ["Memorandum", "Notice", "Determination", "Presidential Order"] },
] as const;

export type ToneLabel = { tone: "POS" | "NEG" | "NEU"; cls: "up" | "dn" | "dim" } | null;

export function toneOf(item: NewsItem): ToneLabel {
  const s = item.sentiment;
  if (!s) return null;
  const t = sentimentTone(s.compound);
  return t === "up" ? { tone: "POS", cls: "up" } : t === "down" ? { tone: "NEG", cls: "dn" } : { tone: "NEU", cls: "dim" };
}

const TOPIC_SHORT: Record<string, string> = {
  tariffs_trade: "TRADE",
  economy_fiscal: "ECONOMY",
  foreign_policy: "FOREIGN",
  legal_judicial: "LEGAL",
  political_conflict: "POLITICS",
  energy_environment: "ENERGY",
  defense: "DEFENSE",
  immigration: "IMMIGRATION",
};

export function topicShort(item: NewsItem) {
  const t = item.topics[0];
  if (!t) return item.sectors[0] ? item.sectors[0].label.split(" ")[0].toUpperCase() : "GENERAL";
  return TOPIC_SHORT[t.key] ?? t.label.toUpperCase();
}

/** Impact score 0–1 → 0–100 for display; null when unscored. */
export const impact100 = (item: NewsItem) => (item.impact ? Math.round(item.impact.score * 100) : null);

export function sectorWords(item: NewsItem, max = 2) {
  return item.sectors
    .slice(0, max)
    .map((s) => s.label.split(/[ &]/)[0].toUpperCase())
    .join(" ");
}

export const summaryOf = (item: NewsItem) => item.generated_summary?.text || item.summary || "";
