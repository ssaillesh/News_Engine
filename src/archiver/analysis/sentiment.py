"""FinBERT sentiment scoring.

``ProsusAI/finbert`` is BERT fine-tuned on financial news for three-way sentiment
(positive / negative / neutral). We run it over archived headlines and read the
full softmax distribution rather than just the winning label, because on news
prose the interesting signal is usually *how* mixed an item is, not which bucket
it lands in.

Two deliberate constraints:

* **torch/transformers are an optional extra.** The archiver's ingest path must
  stay installable without a ~500 MB ML stack, so the imports happen inside
  :meth:`FinBertScorer.load` and a missing dependency raises a
  :class:`ModelUnavailableError` that says how to fix it.
* **Label order is read from the model, never hardcoded.** ``id2label`` is
  ``{0: positive, 1: negative, 2: neutral}`` for this checkpoint — which is *not*
  the alphabetical order a reader would assume — so we map by name at load time.
  A different fine-tune with a different order then still scores correctly.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

FINBERT_MODEL = "ProsusAI/finbert"
LABELS = ("positive", "negative", "neutral")

# BERT's hard limit is 512 wordpieces; headlines are far shorter, but truncation
# keeps a long body text from raising instead of scoring.
MAX_TOKENS = 512
DEFAULT_BATCH_SIZE = 16


class ModelUnavailableError(RuntimeError):
    """Raised when the optional ML dependencies aren't installed."""


@dataclass(frozen=True, slots=True)
class SentimentReading:
    """One model reading: the full distribution plus the derived summaries."""

    label: str
    score: float
    positive: float
    negative: float
    neutral: float
    model: str

    @property
    def compound(self) -> float:
        """Signed polarity in [-1, 1] — positive minus negative.

        Collapses the distribution to one sortable number. Neutral items land
        near 0 whether the model is confident or torn, which is the intent: it
        measures *direction*, and ``score`` measures confidence.
        """
        return self.positive - self.negative

    def as_row(self, status_id: str, *, content_hash: str | None) -> dict[str, Any]:
        """Shape this reading as a ``status_sentiment`` row dict."""
        return {
            "status_id": status_id,
            "model": self.model,
            "label": self.label,
            "score": self.score,
            "positive": self.positive,
            "negative": self.negative,
            "neutral": self.neutral,
            "compound": self.compound,
            "scored_content_hash": content_hash,
        }


class FinBertScorer:
    """Lazily-loaded FinBERT classifier over batches of text.

    The model is loaded once on first use and reused, so scoring an archive costs
    a single load. Runs on CPU by default; pass ``device="mps"`` or ``"cuda"`` to
    use an accelerator.
    """

    def __init__(
        self,
        model_name: str = FINBERT_MODEL,
        *,
        device: str | None = None,
        max_tokens: int = MAX_TOKENS,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.max_tokens = max_tokens
        self._torch: Any = None
        self._tokenizer: Any = None
        self._model: Any = None
        self._label_index: dict[str, int] = {}

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def load(self) -> None:
        """Import the ML stack and materialize the model (idempotent)."""
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise ModelUnavailableError(
                "FinBERT scoring needs torch + transformers, which are an optional "
                'extra. Install them with:  pip install -e ".[sentiment]"'
            ) from exc

        tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        model.eval()
        if self.device:
            model.to(self.device)

        # Map label name → logit column, so we never depend on positional order.
        id2label = {int(k): str(v).lower() for k, v in model.config.id2label.items()}
        index = {name: idx for idx, name in id2label.items()}
        missing = [name for name in LABELS if name not in index]
        if missing:
            raise ModelUnavailableError(
                f"Model {self.model_name!r} does not expose the expected FinBERT "
                f"labels {LABELS}; missing {missing}. Its labels are {sorted(index)}."
            )

        self._torch = torch
        self._tokenizer = tokenizer
        self._model = model
        self._label_index = index

    # ── scoring ───────────────────────────────────────────────────────────────
    def score(self, texts: Sequence[str]) -> list[SentimentReading]:
        """Score one batch of texts, preserving input order."""
        if not texts:
            return []
        self.load()
        torch = self._torch

        encoded = self._tokenizer(
            list(texts),
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self.max_tokens,
        )
        if self.device:
            encoded = {k: v.to(self.device) for k, v in encoded.items()}

        with torch.no_grad():
            logits = self._model(**encoded).logits
            probs = torch.softmax(logits, dim=-1).cpu().tolist()

        return [self._reading(row) for row in probs]

    def score_batched(
        self, texts: Sequence[str], *, batch_size: int = DEFAULT_BATCH_SIZE
    ) -> Iterable[SentimentReading]:
        """Score a long sequence in fixed-size batches, yielding as it goes."""
        for start in range(0, len(texts), batch_size):
            yield from self.score(texts[start : start + batch_size])

    def _reading(self, probs: Sequence[float]) -> SentimentReading:
        by_label = {name: float(probs[self._label_index[name]]) for name in LABELS}
        label = max(by_label, key=lambda name: by_label[name])
        return SentimentReading(
            label=label,
            score=by_label[label],
            positive=by_label["positive"],
            negative=by_label["negative"],
            neutral=by_label["neutral"],
            model=self.model_name,
        )
