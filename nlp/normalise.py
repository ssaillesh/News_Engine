"""
nlp/normalise.py
Post-processing for raw NER entity strings coming out of entity_sentiments.

Handles:
  - BERT subword artifacts (##Vidia, ##Sk …)
  - Single chars, numbers, punctuation-only strings
  - Ticker → canonical company name  (AAPL → Apple, NVDA → Nvidia …)
  - Company variant → canonical      (Apple Inc. → Apple, Amazon. Com → Amazon …)
  - Person name detection            (known list + partial-name merging)
  - Noise phrases                    (Cuts Tesla, Benzinga Nvidia, & P …)
"""
from __future__ import annotations

import re
from typing import Literal

EntityType = Literal["company", "person", "noise"]

# ── Ticker symbol → canonical company name ─────────────────────────────────────
_TICKER: dict[str, str] = {
    "aapl":  "Apple",
    "msft":  "Microsoft",
    "tsla":  "Tesla",
    "nvda":  "Nvidia",
    "amzn":  "Amazon",
    "googl": "Alphabet",
    "goog":  "Alphabet",
    "meta":  "Meta",
    "nflx":  "Netflix",
    "orcl":  "Oracle",
    "crm":   "Salesforce",
    "amd":   "AMD",
    "intc":  "Intel",
    "qcom":  "Qualcomm",
    "avgo":  "Broadcom",
    "mu":    "Micron",
    "csco":  "Cisco",
    "adbe":  "Adobe",
    "hpe":   "Hewlett Packard Enterprise",
    "pltr":  "Palantir",
    "mrvl":  "Marvell",
    "mstr":  "MicroStrategy",
    "cgc":   "Canopy Growth",
    "voo":   "Vanguard",
    "btc":   "Bitcoin",
    "spus":  "S&P",
    "uex":   "U3O8",
    "gm":    "General Motors",
    "rtx":   "Raytheon",
    "mrvl":  "Marvell",
}

# ── Company variant → canonical (None = noise phrase, discard) ─────────────────
_ALIAS: dict[str, str | None] = {
    # Apple
    "apple":                          "Apple",
    "apple inc":                      "Apple",
    "apple inc.":                     "Apple",
    "apple rises":                    None,
    "apple ai":                       None,
    "aapl stock":                     None,
    "marketbeat apple":               None,
    # Microsoft
    "microsoft":                      "Microsoft",
    "microsoft corporation":          "Microsoft",
    "microsoft corp":                 "Microsoft",
    # Tesla
    "tesla":                          "Tesla",
    "tesla inc":                      "Tesla",
    "cuts tesla":                     None,
    "drive tesla canada":             None,
    # Nvidia
    "nvidia":                         "Nvidia",
    "nvidia corporation":             "Nvidia",
    "benzinga nvidia":                None,
    "nvidia edge ai partnership":     None,
    "nvidia sin":                     None,
    # Amazon
    "amazon":                         "Amazon",
    "amazon. com":                    "Amazon",
    "amazon.com":                     "Amazon",
    # Alphabet / Google
    "alphabet":                       "Alphabet",
    "google":                         "Alphabet",
    "alphabet inc":                   "Alphabet",
    "alphabet stock alphabet":        None,
    "google gemini":                  "Alphabet",
    # Meta
    "meta":                           "Meta",
    "meta platforms":                 "Meta",
    "meta platform":                  "Meta",
    # S&P / index funds
    "s & p":                          "S&P",
    "s&p":                            "S&P",
    "& p":                            None,
    "sp":                             None,
    "sp fund":                        None,
    "vanguard s & p":                 "Vanguard",
    "msci world etf":                 "MSCI",
    "msci world et":                  "MSCI",
    "msci world":                     "MSCI",
    "msci":                           "MSCI",
    # SpaceX / xAI
    "spacex":                         "SpaceX",
    "xai":                            "xAI",
    # OpenAI
    "openai":                         "OpenAI",
    "open ai":                        "OpenAI",
    # SoftBank
    "softbank":                       "SoftBank",
    "softbank group":                 "SoftBank",
    # Berkshire
    "berkshire":                      "Berkshire Hathaway",
    "berkshire hathaway":             "Berkshire Hathaway",
    # Canopy Growth
    "canopy growth":                  "Canopy Growth",
    "canopy growth corporation":      "Canopy Growth",
    # Hewlett Packard
    "hewlett packard":                "Hewlett Packard",
    # Marvell
    "marvell":                        "Marvell",
    # PayPal
    "paypal":                         "PayPal",
    # General
    "yahoo finance":                  "Yahoo Finance",
    "bloomberg":                      "Bloomberg",
    "reuters":                        "Reuters",
    "mp materials":                   "MP Materials",
    "super micro computer":           "Super Micro Computer",
    "check point research":           "Check Point Research",
    "evercore isi":                   "Evercore ISI",
    "gerber kawasaki wealth":         "Gerber Kawasaki Wealth",
    "b. riley securities":            "B. Riley Securities",
    "truist securities":              "Truist Securities",
    "solidarity wealth":              "Solidarity Wealth",
    "geode capital management":       "Geode Capital Management",
    "adams diversified equity fund":  "Adams Diversified Equity Fund",
    "thiel macro":                    "Thiel Macro",
    "davis rea":                      "Davis Rea",
    "edgerock capital":               "Edgerock Capital",
    "anebulo pharmaceuticals":        "Anebulo Pharmaceuticals",
    "department of government efficiency": "DOGE",
    "department of defense":          "Department of Defense",
    "securities commission malaysia": "Securities Commission Malaysia",
    "isoenergy":                      "IsoEnergy",
    "zenatech":                       "ZenaTech",
    "truth social":                   "Truth Social",
    # Noise phrases
    "jensen huang delivers products": None,
    "newsweek elon musk":             None,
    "rtx spark":                      None,
    "panw in focus":                  None,
    "lucid in focus":                 None,
    "ai op":                          None,
    "vera ai platform":               None,
    "iol bitget":                     None,
    "bloombergrussia":                None,
    "macrohard":                      None,
    "futurum":                        None,
    "magnet ex":                      None,
    "simp":                           None,
    "global x u. s. elec":           None,
    "x u. s":                         None,
    "ms ci world":                    None,
    "##ly wall st":                   None,
    "ondo perps":                     None,
    "ondo finance":                   "Ondo Finance",
    "ondo":                           "Ondo Finance",
    "uncer":                          None,
    "data center & communications":   None,
    "hardware engineering":           None,
    "everything exchange":            None,
    "universal exchange":             "Universal Exchange",
    "wf limited":                     None,
    "wff":                            None,
    "tti":                            None,
    "vera":                           None,
}

# ── Known people → canonical display name ──────────────────────────────────────
# Partial name variants map to the same canonical person.
_PEOPLE: dict[str, str] = {
    "elon musk":         "Elon Musk",
    "musk":              "Elon Musk",
    "peter thiel":       "Peter Thiel",
    "thiel":             "Peter Thiel",
    "warren buffett":    "Warren Buffett",
    "tim cook":          "Tim Cook",
    "satya nadella":     "Satya Nadella",
    "jensen huang":      "Jensen Huang",
    "sam altman":        "Sam Altman",
    "mark zuckerberg":   "Mark Zuckerberg",
    "sundar pichai":     "Sundar Pichai",
    "jeff bezos":        "Jeff Bezos",
    "bill gates":        "Bill Gates",
    "jerome powell":     "Jerome Powell",
    "janet yellen":      "Janet Yellen",
    "larry fink":        "Larry Fink",
    "cathie wood":       "Cathie Wood",
    "ray dalio":         "Ray Dalio",
    "michael burry":     "Michael Burry",
    "bill ackman":       "Bill Ackman",
    "trump":             "Donald Trump",
    "donald trump":      "Donald Trump",
    "xi":                "Xi Jinping",
    "xi jinping":        "Xi Jinping",
}

# ── Terms that are never entities ──────────────────────────────────────────────
_NOISE_TERMS: frozenset[str] = frozenset({
    "ai", "etf", "tech", "hardware", "stock", "future", "deal", "move",
    "more", "streak", "foundation", "wwdc", "fed", "elec", "we", "us",
    "big tech", "in", "el", "et", "zap", "fed minutes", "gmo", "col",
    "ma", "me", "mi", "fi", "aa", "mp", "sp", "us", "zar", "osir", "prud",
    "gmc", "gmoc", "tti", "ttm", "voo", "btc", "bitcoin",
    "sec", "free", "freedom", "move", "more", "deal", "streak",
    "data center & communications", "hardware engineering",
    "uncer", "sp fund", "& p", "elec", "uex",
})

# ── Regex helpers ───────────────────────────────────────────────────────────────
_SUBWORD      = re.compile(r'^##')
_ONLY_NONALPHA = re.compile(r'^[^a-zA-Z]+$')
_LEGAL_SUFFIX  = re.compile(
    r'\s+(inc\.?|corp\.?|corporation|ltd\.?|limited|llc|plc|group|holdings?|co\.?|company)$',
    re.IGNORECASE,
)


def classify(raw: str) -> tuple[str, EntityType]:
    """
    Return (canonical_name, entity_type).
    entity_type is 'company', 'person', or 'noise'.
    """
    s = raw.strip()

    # BERT subword artifact
    if _SUBWORD.match(s):
        return s, "noise"

    # Empty, single char, or all non-alphabetic
    if not s or len(s) <= 1 or _ONLY_NONALPHA.match(s):
        return s, "noise"

    lower = s.lower()

    # Known noise terms (exact match)
    if lower in _NOISE_TERMS:
        return s, "noise"

    # Person lookup (includes partial names like "Musk")
    if lower in _PEOPLE:
        return _PEOPLE[lower], "person"

    # Alias table (company variants and noise phrases)
    if lower in _ALIAS:
        canonical = _ALIAS[lower]
        return (canonical, "company") if canonical else (s, "noise")

    # Ticker symbol
    if lower in _TICKER:
        return _TICKER[lower], "company"

    # Strip legal suffix and retry
    clean = _LEGAL_SUFFIX.sub("", s).strip()
    lower_clean = clean.lower()
    if lower_clean != lower:
        if lower_clean in _ALIAS:
            canonical = _ALIAS[lower_clean]
            return (canonical, "company") if canonical else (s, "noise")
        if lower_clean in _TICKER:
            return _TICKER[lower_clean], "company"

    # Very short leftover (2–3 chars not matched above) → noise
    if len(clean) <= 2:
        return clean, "noise"

    return clean, "company"
