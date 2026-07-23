"""Tests for the read-only web UI (ASGI, no live server)."""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport

from archiver.sources.federal_register import normalize_document
from archiver.storage.db import Database
from archiver.storage.repositories import AccountRepository, StatusRepository
from archiver.web import create_app, find_free_port


@pytest.fixture
async def client(db: Database, load_fixture) -> AsyncIterator[httpx.AsyncClient]:
    doc = load_fixture("fr_document.json")
    account, status = normalize_document(doc)
    async with db.session() as session, session.begin():
        await AccountRepository(session, db.dialect).upsert(account)
        await StatusRepository(session, db.dialect).upsert(status)

    transport = ASGITransport(app=create_app(db))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_index_serves_dashboard(client: httpx.AsyncClient):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Trump News Archive" in resp.text


async def test_stats_endpoint(client: httpx.AsyncClient):
    resp = await client.get("/api/stats")
    data = resp.json()
    assert data["total"] == 1
    assert data["by_source"]["federal_register"] == 1


async def test_statuses_endpoint_returns_items(client: httpx.AsyncClient):
    resp = await client.get("/api/statuses")
    data = resp.json()
    assert data["count"] == 1
    item = data["items"][0]
    assert item["kind"] == "Proclamation"
    assert item["source"] == "federal_register"
    assert "Bears Ears" in item["title"]


async def test_facets_endpoint(client: httpx.AsyncClient):
    data = (await client.get("/api/facets")).json()
    assert data["total"] == 1
    assert data["sources"][0]["key"] == "federal_register"
    assert any(k["key"] == "Proclamation" for k in data["kinds"])


async def test_statuses_kind_filter(client: httpx.AsyncClient):
    hit = (await client.get("/api/statuses", params={"kind": "Proclamation"})).json()
    assert hit["count"] == 1
    miss = (await client.get("/api/statuses", params={"kind": "Executive Order"})).json()
    assert miss["count"] == 0


async def test_statuses_search_filter(client: httpx.AsyncClient):
    hit = (await client.get("/api/statuses", params={"q": "bears ears"})).json()
    assert hit["count"] == 1
    miss = (await client.get("/api/statuses", params={"q": "zzz-no-match"})).json()
    assert miss["count"] == 0


async def test_statuses_source_filter(client: httpx.AsyncClient):
    hit = (await client.get("/api/statuses", params={"source": "federal_register"})).json()
    assert hit["count"] == 1
    miss = (await client.get("/api/statuses", params={"source": "mastodon"})).json()
    assert miss["count"] == 0


async def test_statuses_date_range_filter(client: httpx.AsyncClient):
    # fixture doc is published 2026-07-17
    on_range = (await client.get("/api/statuses", params={"since": "2026-07-01"})).json()
    assert on_range["count"] == 1
    in_window = (
        await client.get("/api/statuses", params={"since": "2026-07-17", "until": "2026-07-17"})
    ).json()
    assert in_window["count"] == 1  # date-only 'until' includes the whole day
    before = (await client.get("/api/statuses", params={"until": "2026-07-16"})).json()
    assert before["count"] == 0
    after = (await client.get("/api/statuses", params={"since": "2026-07-18"})).json()
    assert after["count"] == 0


def test_find_free_port_returns_preferred_when_free():
    # Bind a socket to grab a port, close it, then that port is free again.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
    assert find_free_port("127.0.0.1", free_port) == free_port


def test_find_free_port_skips_busy_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        chosen = find_free_port("127.0.0.1", taken)
        assert chosen != taken
        assert taken < chosen <= taken + 20
