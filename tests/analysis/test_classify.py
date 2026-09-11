"""Tests for the deterministic classification pass.

Nothing here is network- or model-bound, so unlike the sentiment tests there is
no stand-in to build: the lexicons and scorers are exercised directly. The cases
that earn their place are the *precision* ones — the false positives these
curated lists exist to prevent — and the two pieces of pass behavior that are
easy to get subtly wrong: renormalizing around not-yet-measured components, and
not clobbering a component another pass owns.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from archiver.analysis.classify import classify_statuses
from archiver.analysis.signals import (
    WEIGHTS_VERSION,
    actionability_score,
    authority_score,
    combine,
    market_sensitivity_score,
    tier_for,
)
from archiver.reference.entities import find_entities
from archiver.reference.topics import find_topics, topic_weight
from archiver.storage.models import StatusImpact, StatusTopic
from archiver.storage.repositories import (
    AccountRepository,
    StatusImpactRepository,
    StatusRepository,
)

ACCOUNT = {"id": "news:acct", "username": "TrumpNews"}


async def _add_status(
    db, status_id: str, text: str, *, source: str = "news", raw: dict | None = None
) -> None:
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
                "raw": raw,
            }
        )


async def _impact(db, status_id: str) -> StatusImpact | None:
    async with db.session() as session:
        return await session.get(StatusImpact, status_id)


# ── topic matching: precision is the whole point ──────────────────────────────
def test_matches_trade_terms():
    assert find_topics("Section 232 tariffs on steel") == {"tariffs_trade": "Section 232"}


def test_bare_trade_does_not_fire_on_trade_show():
    # "trade war"/"trade deal" are listed; bare "trade" deliberately is not.
    assert find_topics("A trade show in Ohio drew record crowds") == {}


def test_supply_chain_is_not_a_trade_term():
    # It was tried, matched more than any other term, and was nearly all defense
    # documents. Regression guard so it does not get helpfully re-added.
    assert find_topics("Securing America's Defense Supply Chains") == {}


def test_topic_weight_takes_the_heaviest_not_the_sum():
    both = find_topics("Supreme Court weighs tariff case")
    assert set(both) == {"legal_judicial", "tariffs_trade"}
    # Sum would let a scattershot item outrank a focused one.
    assert topic_weight(list(both)) == pytest.approx(1.0)


def test_topic_weight_of_nothing_is_zero():
    assert topic_weight([]) == 0.0


# ── entity matching ───────────────────────────────────────────────────────────
def test_finds_countries_by_adjective():
    found = find_entities("tariffs on Chinese steel and Mexican parts")
    assert set(found) == {"CN", "MX"}


def test_new_mexico_is_not_mexico():
    assert find_entities("Wildfire spreads across New Mexico") == {}


def test_thanksgiving_turkey_is_not_a_country():
    # Turkey is omitted from the list precisely because of the annual pardon.
    assert find_entities("The National Thanksgiving Turkey was pardoned") == {}


# ── authority ─────────────────────────────────────────────────────────────────
def test_executive_order_outranks_proclamation():
    eo, eo_label = authority_score("federal_register", {"subtype": "Executive Order"})
    proc, _ = authority_score("federal_register", {"subtype": "Proclamation"})
    assert eo > proc
    assert eo_label == "Executive Order"


def test_news_is_lower_authority_than_official_documents():
    news, label = authority_score("news", None)
    official, _ = authority_score("presidential_documents", None)
    assert news < official
    assert label == "news coverage"


def test_unknown_source_does_not_crash():
    score, label = authority_score(None, None)
    assert 0.0 <= score <= 1.0
    assert label == "unknown"


# ── actionability ─────────────────────────────────────────────────────────────
def test_committed_language_scores_above_speculation():
    committed = actionability_score("Trump signed an order imposing a 50% tariff")
    speculative = actionability_score("Trump may be weighing tariffs, sources say")
    assert committed > speculative


def test_bare_official_title_stays_neutral():
    # An executed action with no cue words must not be punished for that;
    # authority already covers what kind of document it is.
    assert actionability_score("Modifying the Grand Staircase-Escalante Monument") == 0.5


def test_empty_text_is_neutral():
    assert actionability_score("") == 0.5


def test_scores_stay_inside_the_unit_interval():
    shouty = "signed signs imposed imposes ordered announced issued 50% effective January"
    assert 0.0 <= actionability_score(shouty) <= 1.0


# ── combination ───────────────────────────────────────────────────────────────
def test_missing_components_are_excluded_not_zeroed():
    everything_known = combine(
        {"authority": 1.0, "topic": 1.0, "actionability": 1.0,
         "corroboration": None, "market_sensitivity": None}
    )
    # Treating the unmeasured components as 0.0 would drag this to ~0.65.
    assert everything_known == pytest.approx(1.0)


def test_combine_with_nothing_measured_is_zero():
    assert combine({"authority": None}) == 0.0


def test_tiers_ascend_with_score():
    assert tier_for(0.9) == "critical"
    assert tier_for(0.6) == "high"
    assert tier_for(0.45) == "notable"
    assert tier_for(0.1) == "routine"


# ── the pass ──────────────────────────────────────────────────────────────────
async def test_classifies_and_persists(db):
    await _add_status(
        db, "fr:1", "Imposing Tariffs on Imported Steel",
        source="federal_register", raw={"subtype": "Executive Order"},
    )
    report = await classify_statuses(db)

    assert report.scanned == 1
    row = await _impact(db, "fr:1")
    assert row is not None
    assert row.tier == "critical"
    assert row.authority_label == "Executive Order"
    assert row.weights_version == WEIGHTS_VERSION


async def test_official_document_outranks_speculation_about_it(db):
    await _add_status(
        db, "fr:1", "Imposing Tariffs on Imported Steel",
        source="federal_register", raw={"subtype": "Executive Order"},
    )
    await _add_status(db, "news:1", "Trump may be weighing steel tariffs, sources say")

    await classify_statuses(db)

    official = await _impact(db, "fr:1")
    coverage = await _impact(db, "news:1")
    assert official.impact_score > coverage.impact_score


async def test_is_incremental_by_default(db):
    await _add_status(db, "news:1", "Tariffs on steel")
    assert (await classify_statuses(db)).scanned == 1
    # Nothing changed, so a second run visits nothing.
    assert (await classify_statuses(db)).scanned == 0
    assert (await classify_statuses(db, reclassify=True)).scanned == 1


async def test_rerun_preserves_components_owned_by_later_passes(db):
    """A clustering score must survive a re-run of the deterministic pass."""
    await _add_status(db, "news:1", "Tariffs on steel")
    await classify_statuses(db)

    async with db.session() as session, session.begin():
        await StatusImpactRepository(session, db.dialect).upsert(
            {
                "status_id": "news:1",
                "authority": 0.35,
                "topic": 1.0,
                "actionability": 0.5,
                "corroboration": 0.9,
                "impact_score": 0.5,
                "tier": "notable",
                "weights_version": WEIGHTS_VERSION,
                "scored_content_hash": "stale",
            }
        )

    await classify_statuses(db)
    assert (await _impact(db, "news:1")).corroboration == pytest.approx(0.9)


async def test_removed_topics_do_not_linger(db):
    await _add_status(db, "news:1", "Tariffs on steel")
    await classify_statuses(db)

    async with db.session() as session, session.begin():
        await StatusRepository(session, db.dialect).upsert(
            {
                "id": "news:1",
                "account_id": ACCOUNT["id"],
                "created_at": datetime.now(UTC),
                "content_text": "A quiet day in Florida",
                "content_hash": "changed",
                "source": "news",
            }
        )
    await classify_statuses(db)

    async with db.session() as session:
        rows = (await session.scalars(
            StatusTopic.__table__.select().with_only_columns(StatusTopic.topic)
        )).all()
    assert list(rows) == []


async def test_only_classifies_requested_sources(db):
    await _add_status(db, "news:1", "Tariffs on steel")
    await _add_status(db, "fr:1", "Tariffs on steel", source="federal_register")

    report = await classify_statuses(db, sources=["federal_register"])

    assert report.scanned == 1
    assert await _impact(db, "news:1") is None
    assert await _impact(db, "fr:1") is not None


# ── regression: news publishers are not document subtypes ─────────────────────
def test_publisher_is_not_read_as_a_document_subtype():
    """News rows carry the publisher in raw["kind"], the same slot GovInfo uses.

    Reading it as a subtype labelled every CNBC article a document of type
    "CNBC" and printed the publisher twice on the card.
    """
    score, label = authority_score("news", {"kind": "CNBC", "publisher": "CNBC"})
    assert label == "news coverage"
    assert score == pytest.approx(0.35)


def test_official_subtypes_are_still_read():
    _, label = authority_score("presidential_documents", {"kind": "Proclamation"})
    assert label == "Proclamation"


# ── market sensitivity ────────────────────────────────────────────────────────
def test_no_company_named_scores_zero():
    """Zero is a measurement here, not a gap — the caller passes None for that."""
    assert market_sensitivity_score(0) == 0.0
    assert market_sensitivity_score(0, 0.9) == 0.0


def test_a_named_company_carries_a_base_score():
    assert market_sensitivity_score(1) == pytest.approx(0.60)


def test_charged_language_raises_it_in_either_direction():
    neutral = market_sensitivity_score(1, 0.0)
    bullish = market_sensitivity_score(1, 0.8)
    bearish = market_sensitivity_score(1, -0.8)
    assert bullish > neutral and bearish > neutral
    assert bullish == pytest.approx(bearish)
    assert market_sensitivity_score(3, 1.0) <= 1.0


async def test_market_component_stays_unmeasured_until_stocks_are_detected(db):
    """With no stock_mentions rows at all, nobody has looked — so it is None,
    and `combine` renormalizes around it instead of scoring every item as 0."""
    await _add_status(db, "news:1", "Tariffs on steel")
    await classify_statuses(db)
    assert (await _impact(db, "news:1")).market_sensitivity is None
