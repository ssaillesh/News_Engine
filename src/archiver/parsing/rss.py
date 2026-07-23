"""Generic RSS item parsing, shared by every feed-backed source.

Publishers vary in which optional elements they populate — some carry the whole
article in ``content:encoded``, some only a ``description`` blurb, some use Dublin
Core for the byline — so this returns a superset dict and lets each adapter pick
what it needs. Standard library only; no feed library dependency.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
DC_NS = "http://purl.org/dc/elements/1.1/"


def parse_rss(xml_text: str) -> list[dict[str, Any]]:
    """Parse an RSS 2.0 feed into a list of item dicts.

    Also understands Atom ``<entry>`` documents, which a few outlets serve from
    URLs that otherwise look like RSS.
    """
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        # Atom: entries hang off the root rather than a <channel>.
        entries = root.findall("{http://www.w3.org/2005/Atom}entry")
        return [_atom_entry(entry) for entry in entries]
    return [_rss_item(item) for item in channel.findall("item")]


def _rss_item(item: ET.Element) -> dict[str, Any]:
    return {
        "guid": item.findtext("guid"),
        "title": (item.findtext("title") or "").strip(),
        "link": item.findtext("link"),
        "pub_date": item.findtext("pubDate"),
        "categories": [c.text for c in item.findall("category") if c.text],
        "creator": item.findtext(f"{{{DC_NS}}}creator"),
        "description": item.findtext("description"),
        "content": item.findtext(f"{{{CONTENT_NS}}}encoded"),
    }


def _atom_entry(entry: ET.Element) -> dict[str, Any]:
    ns = "{http://www.w3.org/2005/Atom}"
    link_el = entry.find(f"{ns}link")
    return {
        "guid": entry.findtext(f"{ns}id"),
        "title": (entry.findtext(f"{ns}title") or "").strip(),
        "link": link_el.get("href") if link_el is not None else None,
        "pub_date": entry.findtext(f"{ns}published") or entry.findtext(f"{ns}updated"),
        "categories": [c.get("term") for c in entry.findall(f"{ns}category") if c.get("term")],
        "creator": entry.findtext(f"{ns}author/{ns}name"),
        "description": entry.findtext(f"{ns}summary"),
        "content": entry.findtext(f"{ns}content"),
    }
