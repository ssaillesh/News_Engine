"""Unit tests for the Federal Register adapter (pure, no network)."""

from __future__ import annotations

from datetime import datetime

from archiver.sources.federal_register import TRUMP_ACCOUNT, normalize_document


def test_normalize_document_maps_fields(load_fixture):
    doc = load_fixture("fr_document.json")
    account, status = normalize_document(doc)

    assert account["id"] == TRUMP_ACCOUNT["id"]
    assert account["username"] == "realDonaldTrump"

    assert status["id"] == "fr:2026-14654"  # namespaced to avoid cross-source collisions
    assert status["account_id"] == "fr:donald-trump"
    assert status["source"] == "federal_register"
    assert status["url"].endswith("modifying-the-bears-ears-national-monument")
    assert status["content_hash"]
    assert status["raw"] is doc  # raw preserved for re-derivation


def test_normalize_document_content_text_includes_subtype_and_title(load_fixture):
    doc = load_fixture("fr_document.json")
    _account, status = normalize_document(doc)
    assert "[Proclamation]" in status["content_text"]
    assert "Bears Ears National Monument" in status["content_text"]
    assert "modifying the boundaries" in status["content_text"].lower()


def test_normalize_document_created_at_from_publication_date(load_fixture):
    doc = load_fixture("fr_document.json")
    _account, status = normalize_document(doc)
    created = status["created_at"]
    assert isinstance(created, datetime)
    assert created.tzinfo is not None
    assert (created.year, created.month, created.day) == (2026, 7, 17)


def test_normalize_document_survives_sparse_input():
    # Only the required document_number present; everything else missing.
    _account, status = normalize_document({"document_number": "2026-0001"})
    assert status["id"] == "fr:2026-0001"
    assert status["content_hash"]
    assert status["created_at"] is not None  # falls back to now()
