"""Curated country/agency dictionary + a disambiguating matcher.

Companies already have a home in :mod:`archiver.reference.tickers`; this covers
the other two entity kinds that carry impact signal — the *country* a measure
lands on and the *agency* that issues it.

Country names are a minefield on this corpus, so the same rule as the ticker
list applies: **no bare risky tokens.** These are deliberately absent —

* ``Turkey`` — the National Thanksgiving Turkey pardon is an annual presidential
  document, so this would misfire every November on the one corpus that matters.
* ``Georgia`` — the US state dominates political coverage.
* ``Jordan``, ``Chad``, ``Mali``, ``Guinea``, ``Niger`` — common given names or
  ordinary words.

``Mexico`` is kept but guarded: ``New Mexico`` must not count as Mexico. A missed
country is recoverable on the next pass; a wrong one is noise in a ranking whose
entire value is that you can trust the top of it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

COUNTRY = "country"
AGENCY = "agency"
BLOC = "bloc"


@dataclass(frozen=True, slots=True)
class Entity:
    key: str
    label: str
    kind: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    # Strings that must NOT immediately precede an alias for it to count —
    # "New " before "Mexico". Compared case-insensitively against the text to
    # the left of the match.
    not_preceded_by: tuple[str, ...] = field(default_factory=tuple)


_ENTITIES: tuple[Entity, ...] = (
    # ── countries ────────────────────────────────────────────────────────────
    Entity("CN", "China", COUNTRY, ("China", "Chinese")),
    Entity("MX", "Mexico", COUNTRY, ("Mexico", "Mexican"), not_preceded_by=("New ",)),
    Entity("CA", "Canada", COUNTRY, ("Canada", "Canadian")),
    Entity("JP", "Japan", COUNTRY, ("Japan", "Japanese")),
    Entity("DE", "Germany", COUNTRY, ("Germany", "German")),
    Entity("IN", "India", COUNTRY, ("India", "Indian")),
    Entity("RU", "Russia", COUNTRY, ("Russia", "Russian")),
    Entity("UA", "Ukraine", COUNTRY, ("Ukraine", "Ukrainian")),
    Entity("IR", "Iran", COUNTRY, ("Iran", "Iranian")),
    Entity("IL", "Israel", COUNTRY, ("Israel", "Israeli")),
    Entity("KP", "North Korea", COUNTRY, ("North Korea", "North Korean")),
    Entity("KR", "South Korea", COUNTRY, ("South Korea", "South Korean")),
    Entity("TW", "Taiwan", COUNTRY, ("Taiwan", "Taiwanese")),
    Entity("BR", "Brazil", COUNTRY, ("Brazil", "Brazilian")),
    Entity("VN", "Vietnam", COUNTRY, ("Vietnam", "Vietnamese")),
    Entity("GB", "United Kingdom", COUNTRY, ("United Kingdom", "Britain", "British")),
    Entity("FR", "France", COUNTRY, ("France", "French")),
    Entity("IT", "Italy", COUNTRY, ("Italy", "Italian")),
    Entity("ES", "Spain", COUNTRY, ("Spain", "Spanish")),
    Entity("SA", "Saudi Arabia", COUNTRY, ("Saudi Arabia", "Saudi")),
    Entity("VE", "Venezuela", COUNTRY, ("Venezuela", "Venezuelan")),
    Entity("CU", "Cuba", COUNTRY, ("Cuba", "Cuban")),
    Entity("SY", "Syria", COUNTRY, ("Syria", "Syrian")),
    Entity("AF", "Afghanistan", COUNTRY, ("Afghanistan", "Afghan")),
    Entity("IQ", "Iraq", COUNTRY, ("Iraq", "Iraqi")),
    Entity("PK", "Pakistan", COUNTRY, ("Pakistan", "Pakistani")),
    Entity("EG", "Egypt", COUNTRY, ("Egypt", "Egyptian")),
    Entity("CO", "Colombia", COUNTRY, ("Colombia", "Colombian")),
    Entity("CH", "Switzerland", COUNTRY, ("Switzerland", "Swiss")),
    Entity("NL", "Netherlands", COUNTRY, ("Netherlands", "Dutch")),
    Entity("AU", "Australia", COUNTRY, ("Australia", "Australian")),
    Entity("PH", "Philippines", COUNTRY, ("Philippines", "Filipino")),
    Entity("TH", "Thailand", COUNTRY, ("Thailand", "Thai")),
    Entity("ID", "Indonesia", COUNTRY, ("Indonesia", "Indonesian")),
    Entity("PA", "Panama", COUNTRY, ("Panama", "Panamanian")),
    Entity("GL", "Greenland", COUNTRY, ("Greenland",)),

    # ── blocs & multilateral bodies ──────────────────────────────────────────
    Entity("EU", "European Union", BLOC, ("European Union", "EU")),
    Entity("NATO", "NATO", BLOC, ("NATO",)),
    Entity("UN", "United Nations", BLOC, ("United Nations",)),
    Entity("WTO", "World Trade Organization", BLOC, ("World Trade Organization", "WTO")),
    Entity("OPEC", "OPEC", BLOC, ("OPEC",)),
    Entity("G7", "G7", BLOC, ("G7", "G-7")),
    Entity("G20", "G20", BLOC, ("G20", "G-20")),
    Entity("BRICS", "BRICS", BLOC, ("BRICS",)),
    Entity("WHO_ORG", "World Health Organization", BLOC, ("World Health Organization",)),

    # ── US agencies ──────────────────────────────────────────────────────────
    Entity("FED", "Federal Reserve", AGENCY, ("Federal Reserve", "the Fed")),
    Entity("TREAS", "Treasury Department", AGENCY, ("Treasury Department", "Treasury Secretary")),
    Entity("STATE", "State Department", AGENCY, ("State Department", "Secretary of State")),
    Entity("DOD", "Department of Defense", AGENCY, ("Department of Defense", "Pentagon")),
    Entity(
        "DOJ", "Justice Department", AGENCY,
        ("Justice Department", "Department of Justice", "DOJ"),
    ),
    Entity(
        "DHS", "Homeland Security", AGENCY,
        ("Department of Homeland Security", "Homeland Security"),
    ),
    Entity("USTR", "US Trade Representative", AGENCY, ("Trade Representative", "USTR")),
    Entity(
        "COMMERCE", "Commerce Department", AGENCY,
        ("Commerce Department", "Department of Commerce"),
    ),
    Entity("EPA", "EPA", AGENCY, ("Environmental Protection Agency", "EPA")),
    Entity("FDA", "FDA", AGENCY, ("Food and Drug Administration", "FDA")),
    Entity("SECGOV", "SEC", AGENCY, ("Securities and Exchange Commission",)),
    Entity("FTC", "FTC", AGENCY, ("Federal Trade Commission", "FTC")),
    Entity("FBI", "FBI", AGENCY, ("FBI", "Federal Bureau of Investigation")),
    Entity("CIA", "CIA", AGENCY, ("CIA", "Central Intelligence Agency")),
    Entity("IRS", "IRS", AGENCY, ("IRS", "Internal Revenue Service")),
    Entity("ICEGOV", "ICE", AGENCY, ("Immigration and Customs Enforcement",)),
    Entity("CBP", "Customs and Border Protection", AGENCY, ("Customs and Border Protection",)),
    Entity("CONGRESS", "Congress", AGENCY, ("Congress", "Senate", "House of Representatives")),
    Entity("SCOTUS", "Supreme Court", AGENCY, ("Supreme Court",)),
)

ENTITIES: dict[str, Entity] = {e.key: e for e in _ENTITIES}

_ALIAS_TO_KEY: dict[str, str] = {}
_GUARDS: dict[str, tuple[str, ...]] = {}
for _e in _ENTITIES:
    for _alias in _e.aliases:
        _ALIAS_TO_KEY[_alias.lower()] = _e.key
        if _e.not_preceded_by:
            _GUARDS[_alias.lower()] = _e.not_preceded_by

_SORTED_ALIASES = sorted(_ALIAS_TO_KEY, key=len, reverse=True)

_MATCHER = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(a) for a in _SORTED_ALIASES) + r")(?![A-Za-z])",
    re.IGNORECASE,
)


def find_entities(text: str) -> dict[str, tuple[str, str]]:
    """Return ``{key: (kind, matched alias)}`` for entities named in text.

    One entry per entity however often it is named. Guarded aliases ("Mexico"
    inside "New Mexico") are rejected by inspecting the text to their left.
    """
    if not text:
        return {}
    found: dict[str, tuple[str, str]] = {}
    for match in _MATCHER.finditer(text):
        alias = match.group(1)
        lowered = alias.lower()
        guards = _GUARDS.get(lowered)
        if guards:
            preceding = text[: match.start()].lower()
            if any(preceding.endswith(g.lower()) for g in guards):
                continue
        key = _ALIAS_TO_KEY[lowered]
        found.setdefault(key, (ENTITIES[key].kind, alias))
    return found
