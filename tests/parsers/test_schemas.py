"""Schema validation and version-tolerance tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from archiver.parsing import parse_account, parse_context, parse_status

_MINIMAL = {
    "id": "1",
    "created_at": "2024-01-01T00:00:00.000Z",
    "account": {"id": "1", "username": "x"},
}


def test_parse_simple_status(load_fixture):
    status = parse_status(load_fixture("status_simple.json"))
    assert status.id == "111111111111111111"
    assert status.account.username == "archivist"
    assert status.created_at.tzinfo is not None  # timezone-aware
    assert status.content.startswith("<p>Hello")


def test_unknown_fields_are_ignored(load_fixture):
    raw = load_fixture("status_simple.json")
    assert "some_future_field" in raw  # present in the payload
    status = parse_status(raw)
    assert not hasattr(status, "some_future_field")  # tolerated, not exposed


def test_missing_optional_fields_default():
    status = parse_status(_MINIMAL)
    assert status.content == ""
    assert status.sensitive is False
    assert status.media_attachments == []
    assert status.reblog is None


def test_missing_required_id_raises():
    bad = {k: v for k, v in _MINIMAL.items() if k != "id"}
    with pytest.raises(ValidationError):
        parse_status(bad)


def test_missing_account_raises():
    bad = {k: v for k, v in _MINIMAL.items() if k != "account"}
    with pytest.raises(ValidationError):
        parse_status(bad)


def test_reblog_is_recursive(load_fixture):
    status = parse_status(load_fixture("status_reblog.json"))
    assert status.reblog is not None
    assert status.reblog.id == "999999999999999999"
    assert status.reblog.account.acct == "author@other.example"


def test_edited_status_has_edited_at(load_fixture):
    status = parse_status(load_fixture("status_edited.json"))
    assert status.edited_at is not None
    assert status.edited_at > status.created_at


def test_parse_context():
    ctx = parse_context({"ancestors": [], "descendants": [_MINIMAL]})
    assert ctx.descendants[0].id == "1"
    assert ctx.ancestors == []


def test_parse_account(load_fixture):
    account = parse_account(load_fixture("status_simple.json")["account"])
    assert account.followers_count == 100
