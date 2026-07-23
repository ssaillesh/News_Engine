"""Tests for the abstractive summarization pass.

As with sentiment, the model is stubbed — what's under test is the selection
logic, incrementality, and the short-article guard.
"""

from __future__ import annotations

from datetime import UTC, datetime

from archiver.analysis.pipeline import summarize_statuses
from archiver.analysis.summarize import Summarizer
from archiver.storage.models import StatusSummary
from archiver.storage.repositories import AccountRepository, StatusRepository

ACCOUNT = {"id": "news:acct", "username": "TrumpNews"}
LONG_BODY = "The order raises duties on a wide range of imports. " * 20


class FakeSummarizer(Summarizer):
    def __init__(self, model_name: str = "fake/bart") -> None:
        super().__init__(model_name)
        self.calls: list[list[str]] = []

    def summarize(self, texts):  # type: ignore[override]
        self.calls.append(list(texts))
        return [f"SUMMARY[{t[:20].strip()}]" for t in texts]


async def _add(db, status_id: str, text: str, *, source: str = "news") -> None:
    async with db.session() as session, session.begin():
        await AccountRepository(session, db.dialect).upsert(dict(ACCOUNT))
        await StatusRepository(session, db.dialect).upsert(
            {
                "id": status_id,
                "account_id": ACCOUNT["id"],
                "created_at": datetime.now(UTC),
                "content_text": text,
                "content_hash": f"hash-{hash(text)}",
                "source": source,
            }
        )


async def _summary(db, status_id: str) -> StatusSummary | None:
    async with db.session() as session:
        return await session.get(StatusSummary, status_id)


async def test_summarizes_and_persists(db):
    await _add(db, "news:1", f"Headline here\n\n{LONG_BODY}")

    report = await summarize_statuses(db, summarizer=FakeSummarizer())

    assert report.summarized == 1
    assert (await _summary(db, "news:1")).summary.startswith("SUMMARY[")


async def test_headline_is_excluded_from_the_input(db):
    await _add(db, "news:1", f"Headline here\n\n{LONG_BODY}")
    summarizer = FakeSummarizer()

    await summarize_statuses(db, summarizer=summarizer)

    sent = summarizer.calls[0][0]
    assert not sent.startswith("Headline here"), "the headline must not be fed back in"
    assert sent.startswith("The order raises duties")


async def test_short_articles_are_skipped(db):
    await _add(db, "news:1", "Headline\n\nToo short to condense.")

    report = await summarize_statuses(db, summarizer=FakeSummarizer())

    assert report.summarized == 0
    assert report.skipped_short == 1
    assert await _summary(db, "news:1") is None


async def test_headline_only_items_are_skipped(db):
    # Google News items have no body at all — nothing to summarize.
    await _add(db, "news:1", "Trump signs order")

    report = await summarize_statuses(db, summarizer=FakeSummarizer())

    assert report.summarized == 0
    assert report.skipped_short == 1


async def test_rerun_is_incremental(db):
    await _add(db, "news:1", f"Headline\n\n{LONG_BODY}")
    summarizer = FakeSummarizer()
    await summarize_statuses(db, summarizer=summarizer)

    second = await summarize_statuses(db, summarizer=summarizer)

    assert second.summarized == 0
    assert len(summarizer.calls) == 1


async def test_edited_article_is_resummarized(db):
    await _add(db, "news:1", f"Headline\n\n{LONG_BODY}")
    await summarize_statuses(db, summarizer=FakeSummarizer())

    await _add(db, "news:1", f"Headline\n\n{LONG_BODY} Now with a correction appended.")
    report = await summarize_statuses(db, summarizer=FakeSummarizer())

    assert report.summarized == 1


async def test_regenerate_flag_redoes_everything(db):
    await _add(db, "news:1", f"Headline\n\n{LONG_BODY}")
    await summarize_statuses(db, summarizer=FakeSummarizer())

    report = await summarize_statuses(db, regenerate=True, summarizer=FakeSummarizer())

    assert report.summarized == 1


async def test_only_requested_sources_are_summarized(db):
    await _add(db, "news:1", f"Headline\n\n{LONG_BODY}")
    await _add(db, "fr:1", f"Proclamation\n\n{LONG_BODY}", source="federal_register")

    report = await summarize_statuses(db, sources=("news",), summarizer=FakeSummarizer())

    assert report.summarized == 1
    assert await _summary(db, "fr:1") is None


async def test_blank_generation_is_not_stored(db):
    class BlankSummarizer(FakeSummarizer):
        def summarize(self, texts):  # type: ignore[override]
            return ["   " for _ in texts]

    await _add(db, "news:1", f"Headline\n\n{LONG_BODY}")

    report = await summarize_statuses(db, summarizer=BlankSummarizer())

    assert report.summarized == 0
    assert await _summary(db, "news:1") is None
