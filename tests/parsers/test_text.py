"""Tests for HTML → plaintext derivation."""

from __future__ import annotations

from archiver.parsing.text import html_to_text


def test_empty_input():
    assert html_to_text(None) == ""
    assert html_to_text("") == ""


def test_strips_tags_and_decodes_entities():
    assert html_to_text("<p>Hello <strong>world</strong> &amp; more</p>") == "Hello world & more"


def test_paragraphs_become_blank_line_separated():
    assert html_to_text("<p>a</p><p>b</p>") == "a\n\nb"


def test_collapses_stray_tabs_and_spaces():
    # trailing tabs (as seen in some feed titles) and internal runs are normalized
    assert html_to_text("<p>Liberation of Guam\t\t\t</p>") == "Liberation of Guam"
    assert html_to_text("<p>Hello    world</p>") == "Hello world"


def test_caps_consecutive_blank_lines():
    assert html_to_text("<p>a</p><br><br><br><p>b</p>") == "a\n\nb"
