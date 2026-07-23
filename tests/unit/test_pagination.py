"""Unit tests for Mastodon pagination helpers (pure, no network)."""

from __future__ import annotations

import pytest

from archiver.clients.pagination import next_cursor_params, parse_link_header, query_param

_LINK = (
    '<https://m.example/api/v1/accounts/1/statuses?max_id=100>; rel="next", '
    '<https://m.example/api/v1/accounts/1/statuses?min_id=200>; rel="prev"'
)


def test_parse_link_header_extracts_next_and_prev():
    links = parse_link_header(_LINK)
    assert links["next"].endswith("max_id=100")
    assert links["prev"].endswith("min_id=200")


def test_parse_link_header_empty():
    assert parse_link_header(None) == {}
    assert parse_link_header("") == {}


def test_query_param():
    assert query_param("https://m.example/x?max_id=100&limit=40", "max_id") == "100"
    assert query_param("https://m.example/x?limit=40", "max_id") is None


def test_next_cursor_params_backfill_uses_oldest_id():
    # newest-first page → last item is oldest → max_id for the next (older) page
    items = [{"id": "5"}, {"id": "4"}, {"id": "3"}]
    assert next_cursor_params(items, follow="next") == {"max_id": "3"}


def test_next_cursor_params_forward_uses_newest_id():
    items = [{"id": "5"}, {"id": "4"}, {"id": "3"}]
    assert next_cursor_params(items, follow="prev") == {"min_id": "5"}


def test_next_cursor_params_empty():
    assert next_cursor_params([], follow="next") == {}


def test_next_cursor_params_bad_direction():
    with pytest.raises(ValueError):
        next_cursor_params([{"id": "1"}], follow="sideways")
