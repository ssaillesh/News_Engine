"""Fetch the body of a news article for offline analysis.

Only direct publisher links are attempted. Google News redirect links resolve
through JavaScript, which a plain HTTP client cannot follow, so they are skipped
rather than guessed at. robots.txt is honoured when ``respect_robots`` is on, and
anything that does not yield a real body returns ``None`` — the caller then
skips the story instead of asking a model to analyse a headline.
"""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

_MIN_PARAGRAPH_CHARS = 40
_MIN_ARTICLE_CHARS = 800
_SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript"}


def is_google_news_link(url: str | None) -> bool:
    if not url:
        return False
    return urlparse(url).netloc.endswith("news.google.com")


class _Paragraphs(HTMLParser):
    """Collect <p> text outside navigation chrome — enough for news bodies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._in_p = False
        self._buf: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "p" and not self._skip:
            self._in_p, self._buf = True, []

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag == "p" and self._in_p:
            text = " ".join("".join(self._buf).split())
            if len(text) >= _MIN_PARAGRAPH_CHARS:
                self.paragraphs.append(text)
            self._in_p = False

    def handle_data(self, data: str) -> None:
        if self._in_p and not self._skip:
            self._buf.append(data)


def extract_article_text(html: str) -> str:
    parser = _Paragraphs()
    parser.feed(html)
    # Keep order, drop repeats (share prompts and captions often duplicate).
    seen: set[str] = set()
    kept: list[str] = []
    for paragraph in parser.paragraphs:
        if paragraph not in seen:
            seen.add(paragraph)
            kept.append(paragraph)
    return "\n\n".join(kept)


async def _allowed(client: httpx.AsyncClient, url: str, user_agent: str) -> bool:
    parts = urlparse(url)
    robots = RobotFileParser()
    try:
        resp = await client.get(f"{parts.scheme}://{parts.netloc}/robots.txt")
    except httpx.HTTPError:
        return True  # unreachable robots.txt is conventionally treated as no rules
    if resp.status_code >= 400:
        return resp.status_code not in (401, 403)
    robots.parse(resp.text.splitlines())
    return robots.can_fetch(user_agent, url)


async def fetch_article_text(
    url: str | None,
    *,
    client: httpx.AsyncClient,
    user_agent: str,
    respect_robots: bool = True,
) -> str | None:
    """Return the article body, or ``None`` if it cannot be read properly."""
    if not url or is_google_news_link(url) or urlparse(url).scheme not in ("http", "https"):
        return None
    try:
        if respect_robots and not await _allowed(client, url, user_agent):
            return None
        resp = await client.get(url)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200 or "html" not in resp.headers.get("content-type", "html"):
        return None
    text = extract_article_text(resp.text)
    return text if len(text) >= _MIN_ARTICLE_CHARS else None
