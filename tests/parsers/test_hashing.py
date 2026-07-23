"""Content-hash and payload-hash tests (dedup / edit detection)."""

from __future__ import annotations

from archiver.domain.hashing import content_hash, payload_hash, sha256_hex


def test_content_hash_deterministic():
    assert content_hash(content="hello") == content_hash(content="hello")


def test_content_hash_changes_when_content_changes():
    assert content_hash(content="hello") != content_hash(content="hello (edited)")


def test_content_hash_media_order_independent():
    a = content_hash(content="x", media_ids=["1", "2", "3"])
    b = content_hash(content="x", media_ids=["3", "1", "2"])
    assert a == b


def test_content_hash_reacts_to_media_set():
    assert content_hash(content="x") != content_hash(content="x", media_ids=["1"])


def test_content_hash_reacts_to_spoiler_and_sensitive():
    base = content_hash(content="x")
    assert base != content_hash(content="x", spoiler_text="cw")
    assert base != content_hash(content="x", sensitive=True)


def test_content_hash_poll_order_is_significant():
    a = content_hash(content="x", poll_options=["a", "b"])
    b = content_hash(content="x", poll_options=["b", "a"])
    assert a != b


def test_payload_hash_is_key_order_independent():
    assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})


def test_payload_hash_changes_with_value():
    assert payload_hash({"a": 1}) != payload_hash({"a": 2})


def test_sha256_hex_matches_known_value():
    # sha256(b"") well-known digest
    assert sha256_hex(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
