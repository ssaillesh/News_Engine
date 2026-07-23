"""Tests for the FinBERT enrichment pass.

The model itself is not exercised here — downloading 400 MB of weights would make
the suite slow and network-dependent. What matters and is tested is everything
around it: label mapping, the derived numbers, which rows a run selects, and that
re-runs are incremental. A ``FakeScorer`` stands in for the network-bound part.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from archiver.analysis.pipeline import score_statuses
from archiver.analysis.sentiment import FinBertScorer, SentimentReading
from archiver.storage.models import StatusSentiment
from archiver.storage.repositories import AccountRepository, StatusRepository

ACCOUNT = {"id": "news:acct", "username": "TrumpNews"}


class FakeScorer(FinBertScorer):
    """Deterministic stand-in: sentiment keyed off a marker in the text."""

    def __init__(self) -> None:
        super().__init__("fake/finbert")
        self.calls: list[list[str]] = []

    def score(self, texts):  # type: ignore[override]
        self.calls.append(list(texts))
        out = []
        for text in texts:
            if "GOOD" in text:
                probs = (0.8, 0.1, 0.1)
            elif "BAD" in text:
                probs = (0.1, 0.7, 0.2)
            else:
                probs = (0.2, 0.2, 0.6)
            pos, neg, neu = probs
            label = max(
                (("positive", pos), ("negative", neg), ("neutral", neu)),
                key=lambda pair: pair[1],
            )[0]
            out.append(
                SentimentReading(
                    label=label,
                    score=max(probs),
                    positive=pos,
                    negative=neg,
                    neutral=neu,
                    model=self.model_name,
                )
            )
        return out


async def _add_status(db, status_id: str, text: str, *, source: str = "news") -> None:
    async with db.session() as session, session.begin():
        await AccountRepository(session, db.dialect).upsert(dict(ACCOUNT))
        await StatusRepository(session, db.dialect).upsert(
            {
                "id": status_id,
                "account_id": ACCOUNT["id"],
                "created_at": datetime.now(UTC),
                "content_text": text,
                "content_hash": f"hash-of-{text}",
                "source": source,
            }
        )


async def _sentiment(db, status_id: str) -> StatusSentiment | None:
    async with db.session() as session:
        return await session.get(StatusSentiment, status_id)


# ── the reading itself ────────────────────────────────────────────────────────
def test_compound_is_positive_minus_negative():
    reading = SentimentReading("positive", 0.8, 0.8, 0.1, 0.1, "m")
    assert reading.compound == pytest.approx(0.7)


def test_compound_is_near_zero_for_balanced_readings():
    # Confidently neutral and evenly torn both mean "no direction".
    assert SentimentReading("neutral", 0.9, 0.05, 0.05, 0.9, "m").compound == pytest.approx(0.0)
    assert SentimentReading("positive", 0.5, 0.5, 0.5, 0.0, "m").compound == pytest.approx(0.0)


def test_as_row_carries_the_scored_hash():
    row = SentimentReading("negative", 0.7, 0.1, 0.7, 0.2, "m").as_row("s1", content_hash="abc")
    assert row["status_id"] == "s1"
    assert row["scored_content_hash"] == "abc"
    assert row["compound"] == pytest.approx(-0.6)


# ── the pass ──────────────────────────────────────────────────────────────────
async def test_scores_and_persists(db):
    await _add_status(db, "news:1", "A GOOD day for markets")
    await _add_status(db, "news:2", "A BAD day for markets")

    report = await score_statuses(db, scorer=FakeScorer())

    assert report.scored == 2
    assert report.label_counts == {"positive": 1, "negative": 1}
    assert (await _sentiment(db, "news:1")).label == "positive"
    assert (await _sentiment(db, "news:2")).label == "negative"


async def test_only_scores_requested_sources(db):
    await _add_status(db, "news:1", "GOOD news")
    await _add_status(db, "fr:1", "GOOD proclamation", source="federal_register")

    report = await score_statuses(db, sources=("news",), scorer=FakeScorer())

    assert report.scored == 1
    assert await _sentiment(db, "fr:1") is None


async def test_rerun_is_incremental(db):
    await _add_status(db, "news:1", "GOOD news")
    scorer = FakeScorer()
    assert (await score_statuses(db, scorer=scorer)).scored == 1

    second = await score_statuses(db, scorer=scorer)

    assert second.scored == 0
    assert len(scorer.calls) == 1, "an already-scored, unchanged item must not be re-sent"


async def test_edited_text_is_rescored(db):
    await _add_status(db, "news:1", "GOOD news")
    await score_statuses(db, scorer=FakeScorer())

    # Same id, new text → new content_hash → stale reading must be refreshed.
    await _add_status(db, "news:1", "BAD news")
    report = await score_statuses(db, scorer=FakeScorer())

    assert report.scored == 1
    assert (await _sentiment(db, "news:1")).label == "negative"


async def test_rescore_flag_redoes_everything(db):
    await _add_status(db, "news:1", "GOOD news")
    await score_statuses(db, scorer=FakeScorer())

    report = await score_statuses(db, rescore=True, scorer=FakeScorer())

    assert report.scored == 1


async def test_switching_model_rescores(db):
    await _add_status(db, "news:1", "GOOD news")
    await score_statuses(db, scorer=FakeScorer())

    other = FakeScorer()
    other.model_name = "other/model"
    report = await score_statuses(db, model_name="other/model", scorer=other)

    assert report.scored == 1
    assert (await _sentiment(db, "news:1")).model == "other/model"


async def test_empty_text_is_skipped_not_scored(db):
    await _add_status(db, "news:1", "   ")

    report = await score_statuses(db, scorer=FakeScorer())

    assert report.scored == 0
    assert report.skipped_empty == 1


async def test_batches_respect_batch_size(db):
    for i in range(5):
        await _add_status(db, f"news:{i}", f"GOOD item {i}")
    scorer = FakeScorer()

    await score_statuses(db, batch_size=2, scorer=scorer)

    assert [len(call) for call in scorer.calls] == [2, 2, 1]


async def test_only_the_headline_is_scored(db):
    await _add_status(db, "news:1", "GOOD headline\n\nBAD body text that follows")
    scorer = FakeScorer()

    await score_statuses(db, scorer=scorer)

    assert scorer.calls == [["GOOD headline"]]
