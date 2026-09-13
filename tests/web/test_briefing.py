"""Tests for on-demand story analysis.

A fake client stands in for Claude, so nothing here touches the network or costs
money. What is covered is everything around the model call: which input path a
story takes, generate-once storage, the daily cap, refusals, paused server-tool
turns, and how each failure reaches the page.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from httpx import ASGITransport

from archiver.briefings.generator import Briefing, BriefingGenerator, build_prompt
from archiver.storage.models import Status
from archiver.storage.repositories import AccountRepository, StatusRepository
from archiver.web import create_app

ACCOUNT = {"id": "news:acct", "username": "TrumpNews"}

BRIEFING = Briefing(
    bottom_line="Steel tariffs rise to 50%.",
    what_happened="An order raises duties.",
    why_it_matters="Input costs climb for manufacturers.",
    how_it_impacts="Higher import prices pass through to goods.",
    whats_being_done="Takes effect October 1.",
    trump_position="Framed as protecting jobs.",
    economic_effects=[
        {"area": "Consumer prices", "direction": "negative", "explanation": "Costs pass through."}
    ],
    sectors=[
        {
            "area": "Materials",
            "direction": "mixed",
            "explanation": "Domestic mills gain, importers lose.",
        }
    ],
    companies=[
        {"name": "Ford", "ticker": "F", "direction": "negative", "explanation": "Steel-heavy."}
    ],
    key_dates=["2026-10-01: duties take effect"],
    open_questions="Exemptions unclear.",
    source_quality="full_text",
)


class Block(SimpleNamespace):
    def to_dict(self):
        return dict(vars(self))


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def done(parsed=BRIEFING, stop="end_turn", content=None):
    return SimpleNamespace(
        stop_reason=stop,
        parsed_output=parsed,
        content=content or [],
        usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
        model="claude-opus-5",
    )


def fake_client(*responses):
    messages = FakeMessages(responses)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


async def _add(db, sid, text, *, source="news", url="https://example.com/a", days_old=0):
    async with db.session() as session, session.begin():
        await AccountRepository(session, db.dialect).upsert(dict(ACCOUNT))
        await StatusRepository(session, db.dialect).upsert(
            {
                "id": sid,
                "account_id": ACCOUNT["id"],
                "created_at": datetime.now(UTC) - timedelta(days=days_old),
                "content_text": text,
                "content_hash": f"h-{sid}",
                "source": source,
                "url": url,
                "raw": {"title": text.split("\n")[0], "publisher": "BBC"},
            }
        )


@pytest.fixture
async def make_client(db) -> AsyncIterator:
    clients = []

    async def _make(briefer):
        transport = ASGITransport(app=create_app(db, briefer=briefer))
        c = httpx.AsyncClient(transport=transport, base_url="http://test")
        clients.append(c)
        return c

    yield _make
    for c in clients:
        await c.aclose()


# ── input path ────────────────────────────────────────────────────────────────
def test_headline_only_story_gets_the_link_and_web_tools():
    status = Status(
        id="n1",
        content_text="Trump raises steel tariffs",
        source="news",
        url="https://example.com/steel",
        raw={"title": "Trump raises steel tariffs"},
        created_at=datetime.now(UTC),
    )
    prompt, tools = build_prompt(status)
    assert "https://example.com/steel" in prompt  # web fetch only reads URLs in the user turn
    assert {t["name"] for t in tools} == {"web_fetch", "web_search"}


def test_story_with_full_text_on_file_is_analysed_without_fetching():
    body = "Imposing Tariffs\n\n" + "Section 1. Duties apply to imported steel. " * 60
    status = Status(
        id="fr1",
        content_text=body,
        source="federal_register",
        raw={"title": "Imposing Tariffs"},
        created_at=datetime.now(UTC),
    )
    prompt, tools = build_prompt(status)
    assert tools == []
    assert "<document>" in prompt and "Duties apply" in prompt


def test_oversized_document_is_cut_with_an_explicit_note():
    body = "T\n\n" + "x" * 500_000
    status = Status(
        id="fr2", content_text=body, source="federal_register", raw={}, created_at=datetime.now(UTC)
    )
    prompt, _ = build_prompt(status)
    assert "only the first" in prompt  # never a silent truncation


# ── generate once, then serve from storage ────────────────────────────────────
async def test_generates_once_then_serves_stored_copy(db, make_client):
    await _add(db, "n1", "Trump raises steel tariffs")
    client, messages = fake_client(done())
    api = await make_client(BriefingGenerator(client=client))

    first = await api.post("/api/analysis", params={"id": "n1"})
    second = await api.post("/api/analysis", params={"id": "n1"})
    got = await api.get("/api/analysis", params={"id": "n1"})

    assert first.status_code == 200 and first.json()["analysis"]["bottom_line"].startswith("Steel")
    assert second.json()["analysis"] == first.json()["analysis"]
    assert got.json()["status"] == "ready"
    assert len(messages.calls) == 1  # the second open cost nothing


async def test_request_uses_structured_output_effort_and_fallbacks(db, make_client):
    await _add(db, "n1", "Trump raises steel tariffs")
    client, messages = fake_client(done())
    api = await make_client(BriefingGenerator(client=client, effort="medium"))
    await api.post("/api/analysis", params={"id": "n1"})
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["output_format"] is Briefing
    assert call["output_config"] == {"effort": "medium"}
    assert call["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in call["betas"]


async def test_missing_reports_whether_it_will_auto_generate(db, make_client):
    await _add(db, "fresh", "Fresh story", days_old=1)
    await _add(db, "old", "Old story", days_old=40)
    client, _ = fake_client()
    api = await make_client(BriefingGenerator(client=client))
    fresh = (await api.get("/api/analysis", params={"id": "fresh"})).json()
    old = (await api.get("/api/analysis", params={"id": "old"})).json()
    assert fresh == {"status": "missing", "available": True, "auto": True}
    assert old["auto"] is False


# ── failures reach the page as something a reader can act on ──────────────────
async def test_no_credentials_is_a_clear_503(db, make_client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    await _add(db, "n1", "Story")
    api = await make_client(BriefingGenerator())
    assert (await api.get("/api/analysis", params={"id": "n1"})).json()["available"] is False
    resp = await api.post("/api/analysis", params={"id": "n1"})
    assert resp.status_code == 503 and "ANTHROPIC_API_KEY" in resp.json()["detail"]


async def test_refusal_is_not_stored(db, make_client):
    await _add(db, "n1", "Story")
    client, _ = fake_client(done(parsed=None, stop="refusal"))
    api = await make_client(BriefingGenerator(client=client))
    resp = await api.post("/api/analysis", params={"id": "n1"})
    assert resp.status_code == 422 and resp.json()["detail"]["retryable"] is False
    assert (await api.get("/api/analysis", params={"id": "n1"})).json()["status"] == "missing"


async def test_paused_server_tool_turn_is_resumed(db, make_client):
    await _add(db, "n1", "Story")
    paused = done(
        parsed=None,
        stop="pause_turn",
        content=[
            Block(type="server_tool_use", name="web_fetch", id="s1", input={}),
            Block(type="text", text="reading", parsed_output=None),
        ],
    )
    client, messages = fake_client(paused, done())
    api = await make_client(BriefingGenerator(client=client))
    resp = await api.post("/api/analysis", params={"id": "n1"})
    assert resp.status_code == 200
    echoed = messages.calls[1]["messages"][-1]
    assert echoed["role"] == "assistant"
    assert all("parsed_output" not in b for b in echoed["content"])  # API rejects that field


async def test_daily_limit_blocks_new_generations_only(db, make_client, monkeypatch):
    from archiver.config import settings as settings_mod

    monkeypatch.setenv("ANALYSIS_DAILY_LIMIT", "1")
    settings_mod.get_settings.cache_clear()
    await _add(db, "a", "Story A")
    await _add(db, "b", "Story B")
    client, _ = fake_client(done(), done())
    api = await make_client(BriefingGenerator(client=client))
    assert (await api.post("/api/analysis", params={"id": "a"})).status_code == 200
    blocked = await api.post("/api/analysis", params={"id": "b"})
    assert blocked.status_code == 429
    assert (
        await api.post("/api/analysis", params={"id": "a"})
    ).status_code == 200  # stored still loads


async def test_unknown_story_is_404(db, make_client):
    client, _ = fake_client()
    api = await make_client(BriefingGenerator(client=client))
    assert (await api.get("/api/analysis", params={"id": "nope"})).status_code == 404
    assert (await api.post("/api/analysis", params={"id": "nope"})).status_code == 404
