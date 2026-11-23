/** S&P 500 sector SPDRs, keyed to the GICS sector names stored on securities. */
export const SECTOR_ETFS = [
  { etf: "XLK", gics: "Information Technology", name: "Technology" },
  { etf: "XLC", gics: "Communication Services", name: "Communication" },
  { etf: "XLY", gics: "Consumer Discretionary", name: "Consumer disc." },
  { etf: "XLF", gics: "Financials", name: "Financials" },
  { etf: "XLV", gics: "Health Care", name: "Health care" },
  { etf: "XLI", gics: "Industrials", name: "Industrials" },
  { etf: "XLP", gics: "Consumer Staples", name: "Staples" },
  { etf: "XLE", gics: "Energy", name: "Energy" },
  { etf: "XLU", gics: "Utilities", name: "Utilities" },
  { etf: "XLRE", gics: "Real Estate", name: "Real estate" },
  { etf: "XLB", gics: "Materials", name: "Materials" },
] as const;

/** Cross-asset proxies: every one is an ETF with stored daily bars. */
export const CROSS_ASSET = [
  { t: "SPY", n: "S&P 500" },
  { t: "QQQ", n: "Nasdaq 100" },
  { t: "IWM", n: "Russell 2000" },
  { t: "TLT", n: "20Y Treasuries" },
  { t: "GLD", n: "Gold" },
  { t: "USO", n: "Crude oil" },
  { t: "UUP", n: "US dollar" },
  { t: "IBIT", n: "Bitcoin" },
] as const;

/** Bottom tape on the Today page. */
export const TAPE = ["SPY", "QQQ", "DIA", "IWM", "TLT", "GLD", "USO", "UUP", "IBIT", "SMH"] as const;

export const shortSector = (gics: string | null | undefined) =>
  SECTOR_ETFS.find((s) => s.gics === gics)?.name ?? gics ?? "—";
