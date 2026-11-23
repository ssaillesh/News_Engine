"""Prediction markets set against the archive's coverage.

Polymarket prices are read live (nothing is stored) and each *event* — "Fed
decision in December?", "Russia x Ukraine ceasefire by…?" — is linked to the
archived headlines that name the same specific things: a person, a company, a
country or bloc, an agency. Every link carries the keys it was made on, so the
page can say *why* a headline sits next to a market.

Linking is lexical and deliberately conservative. A shared *topic* alone
("foreign policy") is never enough; it only tips over a link that already shares
something specific. A wrong link is worse than a missing one here, because the
page invites the reader to see cause in what is listed together.

The daily series and statistics are descriptive. ``pearson`` is reported with
its sample size and withheld below :data:`MIN_DAYS`; the page says plainly that
co-movement is not causation.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from archiver.hub.returns import ET
from archiver.reference.entities import ENTITIES, find_entities
from archiver.reference.people import PEOPLE, find_people
from archiver.reference.tickers import TICKERS, find_tickers
from archiver.reference.topics import TOPICS, find_topics

# ── what to fetch and how to group it ────────────────────────────────────────
# Polymarket tag → page theme. An event's *own* tags decide its themes, so one
# fetched under "trump" that is really about the Fed still lands in ECONOMY.
# "trump" is fetched but not themed: Polymarket tags half its catalogue with it.
TAG_THEME: dict[str, str] = {
    "economy": "economy",
    "fed-rates": "economy",
    "fed": "economy",
    "tariffs": "trade",
    "trade": "trade",
    "geopolitics": "conflict",
    "ukraine": "conflict",
    "middle-east": "conflict",
    "china": "conflict",
    "politics": "politics",
    "elections": "politics",
    "finance": "companies",
}
FETCH_TAGS: tuple[str, ...] = (
    "economy", "fed-rates", "tariffs", "geopolitics", "ukraine",
    "middle-east", "china", "politics", "finance", "trump",
)  # fmt: skip
THEMES: tuple[tuple[str, str], ...] = (
    ("economy", "ECONOMY & FED"),
    ("trade", "TRADE"),
    ("conflict", "GEOPOLITICS"),
    ("leaders", "WORLD LEADERS"),
    ("politics", "POLITICS"),
    ("companies", "COMPANIES"),
)
# Tags that imply a topic even when the question's wording does not say it
# ("Will the U.S. invade Iran?" names no topic term).
TAG_TOPIC: dict[str, str] = {
    "economy": "economy_fiscal",
    "fed-rates": "economy_fiscal",
    "fed": "economy_fiscal",
    "tariffs": "tariffs_trade",
    "trade": "tariffs_trade",
    "geopolitics": "foreign_policy",
    "ukraine": "foreign_policy",
    "middle-east": "foreign_policy",
    "china": "foreign_policy",
}

# An outcome priced outside this band is all but decided and says nothing.
MIN_P, MAX_P = 0.01, 0.99
# Outcomes that shape an event's signature: at least this likely (percent),
# and at most this many of the likeliest.
SIGNATURE_MIN_PCT = 2.0
SIGNATURE_MAX = 8

# ── link scoring ──────────────────────────────────────────────────────────────
WEIGHTS: dict[str, int] = {
    "person": 3,
    "company": 3,
    "country": 2,
    "bloc": 2,
    "agency": 2,
    "named": 3,
    "topic": 1,
}
# Per-key overrides: "the Fed" is as specific as a person on this corpus;
# "Congress" names half of all political coverage.
KEY_WEIGHT: dict[str, int] = {"agency:FED": 3, "agency:CONGRESS": 1}
LINK_MIN = 3

# Market questions say "Fed" and "FOMC" bare; the entity lexicon wants "the Fed".
_EXTRA_AGENCY = re.compile(r"(?<![\w-])(Fed|FOMC)(?![\w-])")

# Subjects prediction markets trade on that no other lexicon covers: private
# companies, armed groups, and places narrower than a country. Case-sensitive
# proper nouns, each specific enough to stand alone.
_NAMED: dict[str, tuple[str, ...]] = {
    "OpenAI": ("OpenAI",),
    "Anthropic": ("Anthropic",),
    "SpaceX": ("SpaceX",),
    "xAI": ("xAI",),
    "Strait of Hormuz": ("Strait of Hormuz", "Hormuz"),
    "Gaza": ("Gaza",),
    "West Bank": ("West Bank",),
    "Hamas": ("Hamas",),
    "Hezbollah": ("Hezbollah",),
    "Houthis": ("Houthis", "Houthi"),
    "Crimea": ("Crimea",),
    "Donbas": ("Donbas", "Donbass"),
    "Bitcoin": ("Bitcoin",),
    "Government shutdown": ("government shutdown", "Government Shutdown", "Shutdown"),
}
_NAMED_ALIAS = {a: label for label, aliases in _NAMED.items() for a in aliases}
_NAMED_MATCHER = re.compile(
    r"(?<![\w-])("
    + "|".join(re.escape(a) for a in sorted(_NAMED_ALIAS, key=len, reverse=True))
    + r")(?![\w-])"
)


@dataclass(frozen=True, slots=True)
class Key:
    kind: str
    key: str
    label: str

    @property
    def id(self) -> str:
        return f"{self.kind}:{self.key}"

    @property
    def weight(self) -> int:
        return KEY_WEIGHT.get(self.id, WEIGHTS[self.kind])

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "key": self.key, "label": self.label}


def signature(text: str, *, topics: Iterable[str] = ()) -> dict[str, Key]:
    """Everything specific ``text`` names, keyed by :attr:`Key.id`."""
    out: dict[str, Key] = {}

    def add(k: Key) -> None:
        out.setdefault(k.id, k)

    for key in find_people(text):
        add(Key("person", key, PEOPLE[key].label))
    for ticker in find_tickers(text):
        add(Key("company", ticker, TICKERS[ticker].name if ticker in TICKERS else ticker))
    for key, (kind, _alias) in find_entities(text).items():
        add(Key(kind, key, ENTITIES[key].label))
    if _EXTRA_AGENCY.search(text):
        add(Key("agency", "FED", ENTITIES["FED"].label))
    for match in _NAMED_MATCHER.finditer(text):
        label = _NAMED_ALIAS[match.group(1)]
        add(Key("named", label.upper().replace(" ", "_"), label))
    for key in [*find_topics(text), *topics]:
        if key in TOPICS:
            add(Key("topic", key, TOPICS[key].label))
    return out


def link_threshold(market: dict[str, Key]) -> int:
    """How much a headline must share with ``market`` to link.

    :data:`LINK_MIN`, unless the market's specific keys cannot reach it: a
    market whose only subject is Iran links on Iran, where one naming China and
    Taiwan needs both (or one plus a matching topic).
    """
    specific = sum(k.weight for k in market.values() if k.kind != "topic")
    return max(1, min(LINK_MIN, specific))


def link(
    market: dict[str, Key], headline: dict[str, Key], *, need: int | None = None
) -> list[Key] | None:
    """The keys a headline shares with a market, strongest first, or None.

    Linked at ``need`` (default :func:`link_threshold`) or more *and* with at
    least one shared key that is not a topic: a topic tips a link over the line,
    never makes one on its own.
    """
    shared = [market[k] for k in market.keys() & headline.keys()]
    if not shared or all(k.kind == "topic" for k in shared):
        return None
    if sum(k.weight for k in shared) < (need if need is not None else link_threshold(market)):
        return None
    return sorted(shared, key=lambda k: (-k.weight, k.label))


# ── events ────────────────────────────────────────────────────────────────────
def _float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value) if isinstance(value, str) else None
    except ValueError:
        return []
    return parsed if isinstance(parsed, list) else []


def parse_outcome(market: dict[str, Any]) -> dict[str, Any] | None:
    """One open yes/no market → an outcome row (probabilities in percent).

    The YES side is found by name, not position, so a market listing its
    outcomes the other way round still reads correctly.
    """
    if market.get("closed") or market.get("active") is False or market.get("archived"):
        return None
    names = [str(n).strip().lower() for n in _json_list(market.get("outcomes"))]
    if "yes" not in names:
        return None
    yes = names.index("yes")
    prices = _json_list(market.get("outcomePrices"))
    tokens = _json_list(market.get("clobTokenIds"))
    p = _float(prices[yes]) if yes < len(prices) else None
    if p is None or not 0.0 <= p <= 1.0:
        return None

    def pts(v: Any) -> float | None:
        f = _float(v)
        # The day/week changes are quoted for the YES side, in price units.
        return round(f * 100, 1) if f is not None else None

    return {
        "id": str(market.get("id") or ""),
        "label": str(market.get("groupItemTitle") or market.get("question") or "").strip(),
        "question": str(market.get("question") or "").strip(),
        "probability": round(p * 100, 1),
        "change_1d": pts(market.get("oneDayPriceChange")),
        "change_1w": pts(market.get("oneWeekPriceChange")),
        "volume_24h": _float(market.get("volume24hr")) or 0.0,
        "end_date": market.get("endDateIso") or market.get("endDate"),
        "token": str(tokens[yes]) if yes < len(tokens) else None,
    }


@dataclass
class Event:
    id: str
    slug: str
    title: str
    volume_24h: float
    liquidity: float
    end_date: str | None
    tags: list[str]
    outcomes: list[dict[str, Any]]
    keys: dict[str, Key] = field(default_factory=dict)

    @property
    def url(self) -> str | None:
        return f"https://polymarket.com/event/{self.slug}" if self.slug else None

    @property
    def themes(self) -> list[str]:
        out = sorted({TAG_THEME[t] for t in self.tags if t in TAG_THEME})
        if any(k.kind == "person" for k in self.keys.values()):
            out.append("leaders")
        return out

    @property
    def lead(self) -> dict[str, Any]:
        """The outcome to chart first: the busiest one still in play."""
        live = [o for o in self.outcomes if MIN_P * 100 < o["probability"] < MAX_P * 100]
        return max(live or self.outcomes, key=lambda o: (o["volume_24h"], o["probability"]))


def parse_event(raw: dict[str, Any]) -> Event | None:
    """A Gamma event → :class:`Event`, or None when nothing in it is still open
    and undecided."""
    outcomes = [o for o in (parse_outcome(m) for m in raw.get("markets") or []) if o]
    if not any(MIN_P * 100 < o["probability"] < MAX_P * 100 for o in outcomes):
        return None
    outcomes.sort(key=lambda o: o["probability"], reverse=True)
    tags = [str(t.get("slug") or "").lower() for t in raw.get("tags") or [] if isinstance(t, dict)]
    title = str(raw.get("title") or "").strip()
    # Signature over the title and the outcomes still in play: a nominee
    # market's leading candidates are what its coverage will name, but a 0.3%
    # long shot (a celebrity on a ballot list) would link it to their news.
    in_play = [o for o in outcomes if o["probability"] >= SIGNATURE_MIN_PCT][:SIGNATURE_MAX]
    text = "\n".join([title, *(o["question"] for o in (in_play or outcomes[:1]))])
    return Event(
        id=str(raw.get("id") or ""),
        slug=str(raw.get("slug") or ""),
        title=title,
        volume_24h=_float(raw.get("volume24hr")) or sum(o["volume_24h"] for o in outcomes),
        liquidity=_float(raw.get("liquidity")) or 0.0,
        end_date=raw.get("endDate"),
        tags=tags,
        outcomes=outcomes,
        keys=signature(text, topics=[TAG_TOPIC[t] for t in tags if t in TAG_TOPIC]),
    )


def collect_events(batches: Iterable[Iterable[dict[str, Any]]]) -> list[Event]:
    """Parse and de-duplicate events fetched under several tags, busiest first."""
    seen: dict[str, Event] = {}
    for batch in batches:
        for raw in batch:
            ev = parse_event(raw)
            if ev and ev.id and ev.id not in seen:
                seen[ev.id] = ev
    return sorted(seen.values(), key=lambda e: e.volume_24h, reverse=True)


# ── coverage ──────────────────────────────────────────────────────────────────
@dataclass
class Headline:
    id: str
    created_at: datetime  # aware, UTC
    source: str
    title: str
    publisher: str | None
    url: str | None
    compound: float | None
    impact: float | None
    keys: dict[str, Key]

    @property
    def day(self) -> date:
        return self.created_at.astimezone(ET).date()

    def as_dict(self, why: Sequence[Key] = ()) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "source": self.source,
            "title": self.title,
            "publisher": self.publisher,
            "url": self.url,
            "sentiment": round(self.compound, 4) if self.compound is not None else None,
            "impact": round(self.impact, 4) if self.impact is not None else None,
            "why": [k.as_dict() for k in why],
        }


class CoverageIndex:
    """Headlines indexed by key, so linking an event visits only candidates."""

    def __init__(self, headlines: Sequence[Headline]) -> None:
        self.headlines = list(headlines)
        self._by_key: dict[str, list[int]] = {}
        for i, h in enumerate(self.headlines):
            for k in h.keys:
                self._by_key.setdefault(k, []).append(i)

    def linked(self, keys: dict[str, Key]) -> list[tuple[Headline, list[Key]]]:
        """Headlines linked to ``keys``, newest first, each with its shared keys."""
        candidates: set[int] = set()
        for k, key in keys.items():
            if key.kind != "topic":  # a topic alone never links, so never seeds
                candidates.update(self._by_key.get(k, ()))
        need = link_threshold(keys)
        out = []
        for i in candidates:
            h = self.headlines[i]
            why = link(keys, h.keys, need=need)
            if why:
                out.append((h, why))
        out.sort(key=lambda hw: hw[0].created_at, reverse=True)
        return out


def coverage_summary(
    linked: Sequence[tuple[Headline, list[Key]]], *, now: datetime
) -> dict[str, Any]:
    """Counts and tone of an event's coverage over 7 and 30 days."""
    week = [h for h, _ in linked if h.created_at >= now - timedelta(days=7)]
    scored = [h.compound for h in week if h.compound is not None]
    latest = linked[0][0] if linked else None
    return {
        "count_7d": len(week),
        "count_30d": len(linked),
        "scored_7d": len(scored),
        "avg_sentiment_7d": round(sum(scored) / len(scored), 4) if scored else None,
        "latest": latest.as_dict(linked[0][1]) if latest else None,
    }


# ── daily series & statistics ─────────────────────────────────────────────────
WINDOW_DAYS = 30  # days of odds and coverage set side by side
MIN_DAYS = 8  # fewer paired days than this and a correlation is not reported
BIG_MOVE_PTS = 3.0


def daily_closes(history: Sequence[tuple[datetime, float]]) -> dict[date, float]:
    """Last price of each ET calendar day, in percent."""
    out: dict[date, float] = {}
    for at, p in sorted(history, key=lambda r: r[0]):
        out[(at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(ET).date()] = p * 100
    return out


def build_days(
    closes: dict[date, float],
    linked: Sequence[tuple[Headline, list[Key]]],
    *,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """One row per ET day from ``start`` to ``end``: closing probability, its
    change from the previous close (points), and that day's linked coverage."""
    by_day: dict[date, list[Headline]] = {}
    for h, _ in linked:
        by_day.setdefault(h.day, []).append(h)
    prior = [d for d in closes if d < start]
    prev = closes[max(prior)] if prior else None
    rows = []
    d = start
    while d <= end:
        p = closes.get(d)
        hs = by_day.get(d, [])
        scored = [h.compound for h in hs if h.compound is not None]
        rows.append(
            {
                "date": d.isoformat(),
                "probability": round(p, 2) if p is not None else None,
                "change": round(p - prev, 2) if p is not None and prev is not None else None,
                "news_count": len(hs),
                "scored": len(scored),
                "sentiment": round(sum(scored) / len(scored), 4) if scored else None,
            }
        )
        if p is not None:
            prev = p
        d += timedelta(days=1)
    return rows


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Pearson's r, or None when undefined (fewer than 3 points, or flat)."""
    n = len(xs)
    if n != len(ys) or n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    return sxy / math.sqrt(sxx * syy)


def strength(r: float | None) -> str:
    if r is None:
        return "insufficient"
    a = abs(r)
    return "none" if a < 0.2 else "weak" if a < 0.4 else "moderate" if a < 0.6 else "strong"


def _stat(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    n = len(pairs)
    r = pearson([a for a, _ in pairs], [b for _, b in pairs]) if n >= MIN_DAYS else None
    return {"r": round(r, 2) if r is not None else None, "n": n, "strength": strength(r)}


def correlation_stats(days: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Two descriptive readings over the window.

    * ``co_movement``: the day's change in odds against the day's average
      sentiment of linked coverage — only days that have both.
    * ``attention``: the size of the day's move against how many linked
      headlines ran that day — every day with a price change, quiet days too.
    """
    co = [
        (d["change"], d["sentiment"])
        for d in days
        if d["change"] is not None and d["sentiment"] is not None
    ]
    att = [(abs(d["change"]), float(d["news_count"])) for d in days if d["change"] is not None]
    return {"co_movement": _stat(co), "attention": _stat(att), "min_days": MIN_DAYS}


def big_moves(
    days: Sequence[dict[str, Any]],
    linked: Sequence[tuple[Headline, list[Key]]],
    *,
    threshold: float = BIG_MOVE_PTS,
    limit: int = 6,
    per_day: int = 4,
) -> list[dict[str, Any]]:
    """The days the odds moved most (at least ``threshold`` points), each with
    the linked headlines that ran that same ET day, highest impact first."""
    by_day: dict[str, list[tuple[Headline, list[Key]]]] = {}
    for h, why in linked:
        by_day.setdefault(h.day.isoformat(), []).append((h, why))
    moved = [d for d in days if d["change"] is not None and abs(d["change"]) >= threshold]
    moved.sort(key=lambda d: abs(d["change"]), reverse=True)
    out = []
    for d in moved[:limit]:
        hs = sorted(by_day.get(d["date"], []), key=lambda hw: hw[0].impact or 0.0, reverse=True)
        out.append(
            {
                "date": d["date"],
                "change": d["change"],
                "probability": d["probability"],
                "headlines": [h.as_dict(why) for h, why in hs[:per_day]],
                "news_count": len(hs),
            }
        )
    return out


def event_dict(
    ev: Event, coverage: dict[str, Any] | None = None, *, outcomes: int = 8
) -> dict[str, Any]:
    keys = sorted(ev.keys.values(), key=lambda k: (-k.weight, k.label))
    return {
        "id": ev.id,
        "slug": ev.slug,
        "title": ev.title,
        "url": ev.url,
        "end_date": ev.end_date,
        "volume_24h": round(ev.volume_24h, 2),
        "liquidity": round(ev.liquidity, 2),
        "themes": ev.themes,
        "keys": [k.as_dict() for k in keys if k.kind != "topic"],
        "topics": [k.as_dict() for k in keys if k.kind == "topic"],
        "lead": {k: v for k, v in ev.lead.items() if k != "token"},
        "outcome_count": len(ev.outcomes),
        "outcomes": [{k: v for k, v in o.items() if k != "token"} for o in ev.outcomes[:outcomes]],
        "coverage": coverage,
    }


# ── loading coverage from the archive ─────────────────────────────────────────
COVERAGE_SOURCES = (
    "news",
    "market_news",
    "whitehouse",
    "presidential_documents",
    "federal_register",
)
_TYPE_PREFIX = re.compile(r"^\[[^\]]{1,40}\]\s*")


async def load_coverage(db: Any, *, since: datetime) -> CoverageIndex:
    """Headlines since ``since`` with their sentiment and impact, indexed.

    Only each item's first line is matched — the headline is what the reader
    sees beside the market, so it is what a link must be justified by; a
    country named in passing deep in a body would make links nobody can audit.
    """
    from sqlalchemy import func, select

    from archiver.storage.models import Status, StatusImpact, StatusSentiment

    stmt = (
        select(
            Status.id,
            Status.created_at,
            Status.source,
            Status.kind,
            Status.url,
            func.substr(Status.content_text, 1, 400),
            StatusSentiment.compound,
            StatusImpact.impact_score,
        )
        .outerjoin(StatusSentiment, StatusSentiment.status_id == Status.id)
        .outerjoin(StatusImpact, StatusImpact.status_id == Status.id)
        .where(
            Status.created_at >= since,
            Status.is_deleted.is_(False),
            Status.source.in_(COVERAGE_SOURCES),
        )
    )
    async with db.session() as session:
        rows = (await session.execute(stmt)).all()

    out = []
    for sid, created, source, kind, url, text, compound, impact in rows:
        title = _TYPE_PREFIX.sub("", (text or "").split("\n", 1)[0]).strip()
        if not title or created is None:
            continue
        out.append(
            Headline(
                id=sid,
                created_at=created if created.tzinfo else created.replace(tzinfo=UTC),
                source=source,
                title=title,
                publisher=kind if source == "news" else None,
                url=url,
                compound=compound,
                impact=impact,
                keys=signature(title),
            )
        )
    return CoverageIndex(out)
