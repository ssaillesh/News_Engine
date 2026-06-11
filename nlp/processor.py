"""
nlp/processor.py
Core NLP layer:
  1. Sentence tokenisation
  2. Named Entity Recognition  — dslim/bert-base-NER  (ORG entities only)
  3. Company name normalisation — basic string cleaning
  4. Sentiment scoring          — ProsusAI/finbert on ±2-sentence context window
  5. Article-level + company-level sentiment rollup
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Dict, List, Tuple

from loguru import logger
from transformers import pipeline, Pipeline

from config.models import EntityMention, ProcessedArticle, RawArticle
from config.settings import (
    NER_MODEL,
    SENTIMENT_MODEL,
    TORCH_DEVICE,
    SENTIMENT_WINDOW_SIZE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Model registry — loaded once, reused across calls
# ─────────────────────────────────────────────────────────────────────────────

_ner_pipeline: Pipeline | None = None
_fin_pipeline: Pipeline | None = None


def _get_ner() -> Pipeline:
    global _ner_pipeline
    if _ner_pipeline is None:
        logger.info(f"Loading NER model: {NER_MODEL}")
        _ner_pipeline = pipeline(
            "ner",
            model=NER_MODEL,
            aggregation_strategy="simple",
            device=0 if TORCH_DEVICE == "cuda" else -1,
        )
    return _ner_pipeline


def _get_finbert() -> Pipeline:
    global _fin_pipeline
    if _fin_pipeline is None:
        logger.info(f"Loading FinBERT model: {SENTIMENT_MODEL}")
        _fin_pipeline = pipeline(
            "text-classification",
            model=SENTIMENT_MODEL,
            top_k=None,          # return all three label scores
            device=0 if TORCH_DEVICE == "cuda" else -1,
        )
    return _fin_pipeline


# ─────────────────────────────────────────────────────────────────────────────
# Sentence tokeniser
# ─────────────────────────────────────────────────────────────────────────────

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"\(])")


def _split_sentences(text: str) -> List[str]:
    raw = _SENT_SPLIT.split(text.strip())
    return [s.strip() for s in raw if s.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# Company normalisation
# ─────────────────────────────────────────────────────────────────────────────

_LEGAL_SUFFIXES = re.compile(
    r"\b(Inc\.?|Corp\.?|Ltd\.?|LLC\.?|L\.L\.C\.?|PLC\.?|Co\.?|"
    r"Group|Holdings?|International|Technologies|Technology|"
    r"Enterprises?|Services?|Solutions?|Ventures?)\b",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s{2,}")


def normalise_company(name: str) -> str:
    """
    Basic normalisation: Unicode NFKC → strip legal suffixes →
    collapse whitespace → title-case.
    """
    name = unicodedata.normalize("NFKC", name)
    name = _LEGAL_SUFFIXES.sub("", name)
    name = _WHITESPACE.sub(" ", name).strip(" .,")
    return name.title() if name else name


# ─────────────────────────────────────────────────────────────────────────────
# Context window builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_context_window(
    sentences: List[str],
    sentence_idx: int,
    window: int = SENTIMENT_WINDOW_SIZE,
) -> str:
    """Return ±window sentences around sentence_idx, joined as one string."""
    start = max(0, sentence_idx - window)
    end   = min(len(sentences), sentence_idx + window + 1)
    return " ".join(sentences[start:end])


# ─────────────────────────────────────────────────────────────────────────────
# FinBERT scorer
# ─────────────────────────────────────────────────────────────────────────────

def _score_sentiment(text: str) -> Tuple[str, float, float, float, float]:
    """Returns (dominant_label, confidence, positive, negative, neutral)."""
    truncated = " ".join(text.split()[:450])   # FinBERT 512-token limit
    try:
        results = _get_finbert()(truncated)[0]
        scores  = {r["label"].lower(): r["score"] for r in results}
        pos = scores.get("positive", 0.0)
        neg = scores.get("negative", 0.0)
        neu = scores.get("neutral",  0.0)
        dominant = max(scores, key=scores.get)
        return dominant, scores[dominant], pos, neg, neu
    except Exception as exc:
        logger.warning(f"FinBERT error: {exc}")
        return "neutral", 1.0, 0.0, 0.0, 1.0


# ─────────────────────────────────────────────────────────────────────────────
# NER extraction
# ─────────────────────────────────────────────────────────────────────────────

def _extract_org_entities(
    text: str,
    sentences: List[str],
) -> List[EntityMention]:
    """
    Run BERT-NER on full text, keep only ORG entities,
    map each back to its sentence index, score with FinBERT.
    """
    results = _get_ner()(text)

    # Build char-offset → sentence-index mapping
    char_to_sent: Dict[int, int] = {}
    pos = 0
    for idx, sent in enumerate(sentences):
        for _ in sent:
            char_to_sent[pos] = idx
            pos += 1
        pos += 1  # space between sentences

    mentions: List[EntityMention] = []
    seen_in_sent: set[tuple[str, int]] = set()

    for ent in results:
        if ent.get("entity_group", "").upper() != "ORG":
            continue

        raw_text     = ent["word"]
        start_char   = int(ent["start"])
        end_char     = int(ent["end"])
        sentence_idx = char_to_sent.get(start_char, 0)

        canonical = normalise_company(raw_text)
        if not canonical:
            continue

        key = (canonical, sentence_idx)
        if key in seen_in_sent:
            continue
        seen_in_sent.add(key)

        context_window = _build_context_window(sentences, sentence_idx)
        label, score, pos_s, neg_s, neu_s = _score_sentiment(context_window)

        mentions.append(EntityMention(
            entity          = canonical,
            raw_text        = raw_text,
            label           = "ORG",
            start_char      = start_char,
            end_char        = end_char,
            sentence_idx    = sentence_idx,
            context_window  = context_window,
            sentiment_label = label,
            sentiment_score = score,
            positive_score  = pos_s,
            negative_score  = neg_s,
            neutral_score   = neu_s,
        ))

    return mentions


# ─────────────────────────────────────────────────────────────────────────────
# Per-article rollups
# ─────────────────────────────────────────────────────────────────────────────

def _rollup_company_sentiments(mentions: List[EntityMention]) -> Dict[str, dict]:
    """Aggregate all mentions of the same company within one article."""
    buckets: Dict[str, list] = defaultdict(list)
    for m in mentions:
        buckets[m.entity].append(m)

    rollup = {}
    for company, ms in buckets.items():
        n   = len(ms)
        pos = sum(m.positive_score for m in ms) / n
        neg = sum(m.negative_score for m in ms) / n
        neu = sum(m.neutral_score  for m in ms) / n

        if pos >= neg and pos >= neu:
            dominant = "positive"
        elif neg >= pos and neg >= neu:
            dominant = "negative"
        else:
            dominant = "neutral"

        rollup[company] = {
            "label":          dominant,
            "score":          max(pos, neg, neu),
            "positive_score": round(pos, 4),
            "negative_score": round(neg, 4),
            "neutral_score":  round(neu, 4),
            "mentions":       n,
        }

    return rollup


def _article_level_sentiment(
    company_sentiments: Dict[str, dict],
) -> Tuple[str, float]:
    """Weighted article-level sentiment across all companies (weight = mentions)."""
    if not company_sentiments:
        return "neutral", 0.0

    total_weight = sum(v["mentions"] for v in company_sentiments.values())
    if total_weight == 0:
        return "neutral", 0.0

    pos = sum(v["positive_score"] * v["mentions"] for v in company_sentiments.values()) / total_weight
    neg = sum(v["negative_score"] * v["mentions"] for v in company_sentiments.values()) / total_weight
    neu = sum(v["neutral_score"]  * v["mentions"] for v in company_sentiments.values()) / total_weight

    if pos >= neg and pos >= neu:
        return "positive", round(pos, 4)
    elif neg >= pos and neg >= neu:
        return "negative", round(neg, 4)
    else:
        return "neutral", round(neu, 4)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def process_article(raw: RawArticle) -> ProcessedArticle:
    """Full NLP pipeline for a single RawArticle."""
    text = " ".join(filter(None, [raw.title, raw.full_text or raw.summary]))

    if not text.strip():
        logger.warning(f"Empty text for article {raw.article_id} — skipping NLP")
        return ProcessedArticle(
            article_id   = raw.article_id,
            source       = raw.source,
            ticker       = raw.ticker,
            title        = raw.title,
            url          = raw.url,
            published_at = raw.published_at,
        )

    sentences           = _split_sentences(text)
    entities            = _extract_org_entities(text, sentences)
    company_sentiments  = _rollup_company_sentiments(entities)
    art_label, art_score = _article_level_sentiment(company_sentiments)

    logger.debug(
        f"Article '{raw.title[:60]}' → "
        f"{len(entities)} ORG mentions, "
        f"{len(company_sentiments)} companies, "
        f"article sentiment={art_label}"
    )

    return ProcessedArticle(
        article_id               = raw.article_id,
        source                   = raw.source,
        ticker                   = raw.ticker,
        title                    = raw.title,
        url                      = raw.url,
        published_at             = raw.published_at,
        sentences                = sentences,
        entities                 = entities,
        company_sentiments       = company_sentiments,
        article_sentiment_label  = art_label,
        article_sentiment_score  = art_score,
    )


def process_batch(raws: List[RawArticle]) -> List[ProcessedArticle]:
    """Process a list of raw articles. Per-article errors are caught and logged."""
    processed = []
    for raw in raws:
        try:
            processed.append(process_article(raw))
        except Exception as exc:
            logger.error(f"NLP failed for article {raw.article_id}: {exc}")
    logger.info(f"NLP batch complete: {len(processed)}/{len(raws)} processed")
    return processed
