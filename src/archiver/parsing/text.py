"""HTML → plaintext derivation for full-text search and analysis.

RSS feeds and news APIs deliver item bodies as HTML. We derive a clean plaintext
form (``content_text``) using only the standard library, treating ``<br>`` and
``</p>`` as line breaks. Character references are decoded automatically.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_MULTI_NEWLINE = re.compile(r"\n{3,}")
_INLINE_WS = re.compile(r"[ \t\r\f\v]+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("br", "p"):
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "p":
            self._parts.append("\n")

    def text(self) -> str:
        return "".join(self._parts)


def html_to_text(html: str | None) -> str:
    """Convert status HTML to normalized plaintext (empty string for empty input)."""
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    # Collapse tab/space runs and trim each line (source HTML often carries stray
    # tabs/newlines between tags), then cap consecutive blank lines.
    lines = [_INLINE_WS.sub(" ", line).strip() for line in parser.text().split("\n")]
    return _MULTI_NEWLINE.sub("\n\n", "\n".join(lines)).strip()
