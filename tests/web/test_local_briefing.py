"""Tests for the free analysis path: an open model served by Ollama.

Ollama and publisher websites are both faked with httpx mock transports, so no
model is downloaded and nothing touches the network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from archiver.briefings.articles import extract_article_text, fetch_article_text
from archiver.briefings.generator import BriefingFailed
from archiver.briefings.local import BRIEFING_SCHEMA, LocalBriefingGenerator
from archiver.briefings.offline import write_analyses
from archiver.storage.models import Status, StatusAnalysis
from archiver.storage.repositories import (
    AccountRepository,
    StatusImpactRepository,
    StatusRepository,
)

ACCOUNT = {"id": "acct", "username": "x"}

VALID = {
    "bottom_line": "Duties rise.",
    "what_happened": "An order.",
    "why_it_matters": "Costs.",
    "how_it_impacts": "Prices.",
    "whats_being_done": "Oct 1.",
    "trump_position": "Not stated in the text.",
    "economic_effects": [],
    "sectors": [{"area": "Materials", "direction": "mixed", "explanation": "Split."}],
    "companies": [],
    "key_dates": [],
    "open_questions": "Exemptions.",
    "source_quality": "headline_only",  # the model's guess — must be overridden
}


def ollama(replies, seen=None):
    replies = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        content = replies.pop(0)
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": content},
                "done_reason": "stop",
                "prompt_eval_count": 900,
                "eval_count": 300,
            },
        )

    return httpx.MockTransport(handler)


def status(text="Imposing Tariffs\n\nbody", source="federal_register", url=None):
    return Status(
        id="s1",
        content_text=text,
        source=source,
        url=url,
        raw={"title": text.split("\n")[0]},
        created_at=datetime.now(UTC),
    )


# ── schema and request shape ──────────────────────────────────────────────────
def test_schema_is_self_contained():
    dumped = json.dumps(BRIEFING_SCHEMA)
    assert "$ref" not in dumped and "$defs" not in dumped


async def test_request_constrains_output_and_disables_thinking():
    seen = []
    gen = LocalBriefingGenerator(transport=ollama([json.dumps(VALID)], seen))
    result = await gen.generate(status(), "Imposing Tariffs\n\nSteel duties apply.")
    req = seen[0]
    assert req["format"] == BRIEFING_SCHEMA
    assert req["think"] is False and req["stream"] is False
    assert result.model == "ollama/qwen3:4b"
    assert result.briefing.source_quality == "full_text"  # set by us, not the model


async def test_long_text_is_cut_with_a_note_and_marked_partial():
    seen = []
    gen = LocalBriefingGenerator(transport=ollama([json.dumps(VALID)], seen))
    result = await gen.generate(status(), "T\n\n" + "x" * 60_000)
    assert "only the first" in seen[0]["messages"][1]["content"]
    assert result.briefing.source_quality == "partial"


async def test_retries_once_on_invalid_json():
    gen = LocalBriefingGenerator(transport=ollama(["{not json", json.dumps(VALID)]))
    result = await gen.generate(status(), "text")
    assert result.briefing.bottom_line == "Duties rise."


async def test_gives_up_after_two_invalid_answers():
    gen = LocalBriefingGenerator(transport=ollama(["{}", "{}"]))
    with pytest.raises(BriefingFailed):
        await gen.generate(status(), "text")


async def test_unreachable_ollama_stops_the_whole_run(db):
    """One connection failure means every other story would fail the same way."""

    def boom(request):
        raise httpx.ConnectError("refused")

    long_body = "Order\n\n" + "Section text about duties on steel imports. " * 60
    for i in range(3):
        await _add(db, f"fr{i}", long_body, source="federal_register")
    calls = []

    def counting(request):
        calls.append(1)
        return boom(request)

    gen = LocalBriefingGenerator(transport=httpx.MockTransport(counting))
    report = await write_analyses(db, gen, limit=3, max_minutes=10, days=7, user_agent="ua")
    assert report.unavailable and report.written == 0 and report.failed == 0
    assert len(calls) == 1


# ── article text ──────────────────────────────────────────────────────────────
ARTICLE = """<html><head><script>var x='<p>not this</p>'</script></head><body>
<nav><p>Home News Sports Business Opinion Subscribe today</p></nav>
<article>
<p>The administration raised tariffs on imported steel to 50 percent on Monday, officials said.</p>
<p>Automakers warned that the higher input costs would be passed on to buyers within months.</p>
<p>The automakers warned that the higher input costs would be passed on to buyers within months.</p>
<p>Short.</p>
</article>
<footer><p>Copyright 2026 Example News Corporation all rights reserved</p></footer>
</body></html>"""


def test_extraction_keeps_body_paragraphs_only():
    text = extract_article_text(ARTICLE)
    assert "50 percent" in text and "Automakers warned" in text
    assert "Subscribe" not in text and "Copyright" not in text and "not this" not in text
    assert "Short." not in text


def sites(pages, robots="User-agent: *\nAllow: /"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        body = pages.get(str(request.url))
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


LONG_ARTICLE = (
    "<article>"
    + "".join(
        f"<p>Paragraph {i} about tariffs, steel prices, automakers and consumer costs.</p>"
        for i in range(20)
    )
    + "</article>"
)


async def test_google_news_links_are_never_fetched():
    async with sites({}) as client:
        assert (
            await fetch_article_text(
                "https://news.google.com/rss/articles/CBMi", client=client, user_agent="ua"
            )
            is None
        )


async def test_robots_disallow_is_respected():
    url = "https://pub.example/a"
    async with sites({url: LONG_ARTICLE}, robots="User-agent: *\nDisallow: /") as client:
        assert await fetch_article_text(url, client=client, user_agent="ua") is None
    async with sites({url: LONG_ARTICLE}, robots="User-agent: *\nDisallow: /") as client:
        assert await fetch_article_text(url, client=client, user_agent="ua", respect_robots=False)


async def test_thin_pages_are_rejected():
    url = "https://pub.example/a"
    async with sites(
        {url: "<p>Just a teaser paragraph with barely any content in it.</p>"}
    ) as client:
        assert await fetch_article_text(url, client=client, user_agent="ua") is None


# ── the scheduled pass ────────────────────────────────────────────────────────
async def _add(db, sid, text, *, source, url=None, score=0.5, days_old=0):
    async with db.session() as session, session.begin():
        await AccountRepository(session, db.dialect).upsert(dict(ACCOUNT))
        await StatusRepository(session, db.dialect).upsert(
            {
                "id": sid,
                "account_id": "acct",
                "created_at": datetime.now(UTC) - timedelta(days=days_old),
                "content_text": text,
                "content_hash": f"h-{sid}",
                "source": source,
                "url": url,
                "raw": {"title": text.split("\n")[0]},
            }
        )
        await StatusImpactRepository(session, db.dialect).upsert(
            {
                "status_id": sid,
                "authority": 0.5,
                "topic": 0.5,
                "actionability": 0.5,
                "impact_score": score,
                "tier": "high",
                "weights_version": "v2",
            }
        )


async def test_pass_writes_best_candidates_and_skips_unreadable_ones(db):
    long_body = "Order\n\n" + "Section text about duties on steel imports. " * 60
    await _add(db, "fr", long_body, source="federal_register", score=0.9)
    await _add(
        db,
        "gn",
        "Headline only",
        source="news",
        url="https://news.google.com/rss/articles/X",
        score=0.95,
    )
    await _add(db, "pub", "Publisher story", source="news", url="https://pub.example/a", score=0.8)
    await _add(
        db, "thin", "Thin story", source="news", url="https://pub.example/missing", score=0.7
    )
    await _add(db, "old", long_body, source="federal_register", score=0.99, days_old=30)

    gen = LocalBriefingGenerator(transport=ollama([json.dumps(VALID)] * 5))
    async with sites({"https://pub.example/a": LONG_ARTICLE}) as client:
        report = await write_analyses(
            db, gen, limit=5, max_minutes=10, days=7, user_agent="ua", http_client=client
        )

    assert report.written == 2
    assert report.skipped_google_news == 1 and report.skipped_no_text == 1
    async with db.session() as session:
        stored = set((await session.scalars(select(StatusAnalysis.status_id))).all())
    assert stored == {"fr", "pub"}  # "old" is outside the 7-day window


async def test_pass_respects_limit_and_never_redoes_a_story(db):
    long_body = "Order\n\n" + "Section text about duties on steel imports. " * 60
    for i in range(3):
        await _add(db, f"fr{i}", long_body, source="federal_register", score=0.9 - i / 10)
    seen = []
    gen = LocalBriefingGenerator(transport=ollama([json.dumps(VALID)] * 6, seen))
    first = await write_analyses(db, gen, limit=2, max_minutes=10, days=7, user_agent="ua")
    second = await write_analyses(db, gen, limit=2, max_minutes=10, days=7, user_agent="ua")
    assert first.written == 2 and second.written == 1
    assert len(seen) == 3
