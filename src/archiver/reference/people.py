"""Curated dictionary of world leaders and market-moving officials.

Used to link prediction markets to coverage: a market on "Putin out by…?" and a
headline about Putin share a *person*, which is a far more specific link than a
shared topic.

Rules, the same spirit as :mod:`archiver.reference.entities`:

* **Names, never titles.** Offices change hands; "the Fed chair" or "the German
  chancellor" would silently start meaning someone else. A label is just the
  person's name, so a link is true however the job market moves.
* **No bare risky surnames.** ``Johnson``, ``Lee``, ``Kim``, ``Huang``,
  ``Harris`` and ``Roberts`` are common enough to misfire constantly; those
  people are only matched on their full names.
* **Matching is case-sensitive.** These are proper nouns, and headlines keep
  their capitals; it is what lets ``Xi`` and ``Lula`` be safe.
* **Trump is deliberately absent.** Every item in this archive is about him, so
  a shared "Trump" would link every market to every headline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Person:
    key: str
    label: str
    aliases: tuple[str, ...]


_PEOPLE: tuple[Person, ...] = (
    # ── US administration & Congress ─────────────────────────────────────────
    Person("VANCE", "JD Vance", ("JD Vance", "J.D. Vance", "Vance")),
    Person("RUBIO", "Marco Rubio", ("Marco Rubio", "Rubio")),
    Person("BESSENT", "Scott Bessent", ("Scott Bessent", "Bessent")),
    Person("HEGSETH", "Pete Hegseth", ("Pete Hegseth", "Hegseth")),
    Person("LUTNICK", "Howard Lutnick", ("Howard Lutnick", "Lutnick")),
    Person("GREER", "Jamieson Greer", ("Jamieson Greer",)),
    Person("MJOHNSON", "Mike Johnson", ("Mike Johnson",)),
    Person("THUNE", "John Thune", ("John Thune", "Thune")),
    Person("SCHUMER", "Chuck Schumer", ("Chuck Schumer", "Schumer")),
    Person("JEFFRIES", "Hakeem Jeffries", ("Hakeem Jeffries", "Jeffries")),
    Person("NEWSOM", "Gavin Newsom", ("Gavin Newsom", "Newsom")),
    Person("AOC", "Alexandria Ocasio-Cortez", ("Ocasio-Cortez", "AOC")),
    Person("KHARRIS", "Kamala Harris", ("Kamala Harris",)),
    Person("MAMDANI", "Zohran Mamdani", ("Zohran Mamdani", "Mamdani")),
    # ── central bankers ──────────────────────────────────────────────────────
    Person("POWELL", "Jerome Powell", ("Jerome Powell", "Powell")),
    Person("WARSH", "Kevin Warsh", ("Kevin Warsh", "Warsh")),
    Person("HASSETT", "Kevin Hassett", ("Kevin Hassett", "Hassett")),
    Person("WALLER", "Christopher Waller", ("Christopher Waller", "Waller")),
    Person("LAGARDE", "Christine Lagarde", ("Christine Lagarde", "Lagarde")),
    # ── business ─────────────────────────────────────────────────────────────
    Person("MUSK", "Elon Musk", ("Elon Musk", "Musk")),
    Person("JHUANG", "Jensen Huang", ("Jensen Huang",)),
    Person("ALTMAN", "Sam Altman", ("Sam Altman", "Altman")),
    Person("ZUCKERBERG", "Mark Zuckerberg", ("Mark Zuckerberg", "Zuckerberg")),
    Person("BEZOS", "Jeff Bezos", ("Jeff Bezos", "Bezos")),
    Person("DIMON", "Jamie Dimon", ("Jamie Dimon", "Dimon")),
    # ── world leaders ────────────────────────────────────────────────────────
    Person("PUTIN", "Vladimir Putin", ("Vladimir Putin", "Putin")),
    Person(
        "ZELENSKY",
        "Volodymyr Zelensky",
        ("Volodymyr Zelensky", "Zelensky", "Zelenskyy", "Zelenskiy"),
    ),
    Person("XI", "Xi Jinping", ("Xi Jinping", "Xi")),
    Person("NETANYAHU", "Benjamin Netanyahu", ("Benjamin Netanyahu", "Netanyahu")),
    Person("KHAMENEI", "Ali Khamenei", ("Ali Khamenei", "Khamenei")),
    Person("KIMJU", "Kim Jong Un", ("Kim Jong Un", "Kim Jong-un", "Kim Jong-Un")),
    Person("MODI", "Narendra Modi", ("Narendra Modi", "Modi")),
    Person("MACRON", "Emmanuel Macron", ("Emmanuel Macron", "Macron")),
    Person("LEPEN", "Marine Le Pen", ("Marine Le Pen", "Le Pen")),
    Person("BARDELLA", "Jordan Bardella", ("Jordan Bardella", "Bardella")),
    Person("STARMER", "Keir Starmer", ("Keir Starmer", "Starmer")),
    Person("FARAGE", "Nigel Farage", ("Nigel Farage", "Farage")),
    Person("MERZ", "Friedrich Merz", ("Friedrich Merz", "Merz")),
    Person("MELONI", "Giorgia Meloni", ("Giorgia Meloni", "Meloni")),
    Person("VDLEYEN", "Ursula von der Leyen", ("Ursula von der Leyen", "von der Leyen")),
    Person("CARNEY", "Mark Carney", ("Mark Carney", "Carney")),
    Person("SHEINBAUM", "Claudia Sheinbaum", ("Claudia Sheinbaum", "Sheinbaum")),
    Person("LULA", "Lula da Silva", ("Lula da Silva", "Lula")),
    Person("MILEI", "Javier Milei", ("Javier Milei", "Milei")),
    Person("MADURO", "Nicolás Maduro", ("Nicolás Maduro", "Nicolas Maduro", "Maduro")),
    Person("ERDOGAN", "Recep Tayyip Erdoğan", ("Erdoğan", "Erdogan")),
    Person("MBS", "Mohammed bin Salman", ("Mohammed bin Salman", "bin Salman")),
    Person("TAKAICHI", "Sanae Takaichi", ("Sanae Takaichi", "Takaichi")),
    Person("LEEJM", "Lee Jae-myung", ("Lee Jae-myung", "Lee Jae Myung")),
    Person("ALBANESE", "Anthony Albanese", ("Anthony Albanese", "Albanese")),
    Person("ORBAN", "Viktor Orbán", ("Viktor Orbán", "Viktor Orban", "Orbán", "Orban")),
    Person("POPELEO", "Pope Leo XIV", ("Pope Leo",)),
)

PEOPLE: dict[str, Person] = {p.key: p for p in _PEOPLE}

_ALIAS_TO_KEY: dict[str, str] = {a: p.key for p in _PEOPLE for a in p.aliases}
_MATCHER = re.compile(
    r"(?<![\w-])("
    + "|".join(re.escape(a) for a in sorted(_ALIAS_TO_KEY, key=len, reverse=True))
    + r")(?![\w-])"
)


def find_people(text: str) -> dict[str, str]:
    """Return ``{key: matched alias}`` for people named in ``text``."""
    if not text:
        return {}
    found: dict[str, str] = {}
    for match in _MATCHER.finditer(text):
        alias = match.group(1)
        found.setdefault(_ALIAS_TO_KEY[alias], alias)
    return found
