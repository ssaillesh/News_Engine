"""Abstractive summarization of archived articles.

``sshleifer/distilbart-cnn-12-6`` is BART distilled on CNN/DailyMail — a news
summarization model, which is the right shape for this corpus. It condenses a
publisher's summary (or article body) into a couple of neutral sentences.

An important limitation, deliberately surfaced rather than hidden: this is
*abstractive*, so the model writes new sentences rather than selecting existing
ones. On political reporting a paraphrase can shift emphasis or drop a
qualifier, so the generated text is stored in its own table, never overwrites
the captured record, and is labelled as generated wherever it is displayed.

Like the sentiment pass, torch/transformers are an optional extra and the import
is deferred so the ingest path stays installable without them.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from archiver.analysis.sentiment import ModelUnavailableError

SUMMARY_MODEL = "sshleifer/distilbart-cnn-12-6"

# BART's encoder tops out at 1024 positions; anything longer is truncated.
MAX_INPUT_TOKENS = 1024
DEFAULT_BATCH_SIZE = 4

# Generation bounds, in tokens. Tuned for "a short paragraph": long enough to
# carry the who/what/where a headline omits, short enough to stay a summary.
DEFAULT_MAX_LENGTH = 120
DEFAULT_MIN_LENGTH = 30

# Below this many characters there is nothing to condense — a two-line blurb
# summarized into two lines just burns compute and risks inventing detail.
MIN_CHARS_TO_SUMMARIZE = 400


class Summarizer:
    """Lazily-loaded abstractive summarizer over batches of text."""

    def __init__(
        self,
        model_name: str = SUMMARY_MODEL,
        *,
        device: str | None = None,
        max_length: int = DEFAULT_MAX_LENGTH,
        min_length: int = DEFAULT_MIN_LENGTH,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        self.min_length = min_length
        self._torch: Any = None
        self._tokenizer: Any = None
        self._model: Any = None

    def load(self) -> None:
        """Import the ML stack and materialize the model (idempotent)."""
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise ModelUnavailableError(
                "Summarization needs torch + transformers, which are an optional "
                'extra. Install them with:  pip install -e ".[sentiment]"'
            ) from exc

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
        model.eval()
        if self.device:
            model.to(self.device)
        self._torch = torch
        self._model = model

    def summarize(self, texts: Sequence[str]) -> list[str]:
        """Summarize one batch, preserving input order."""
        if not texts:
            return []
        self.load()
        torch = self._torch

        encoded = self._tokenizer(
            list(texts),
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=MAX_INPUT_TOKENS,
        )
        if self.device:
            encoded = {k: v.to(self.device) for k, v in encoded.items()}

        with torch.no_grad():
            generated = self._model.generate(
                **encoded,
                max_length=self.max_length,
                min_length=self.min_length,
                num_beams=4,
                length_penalty=2.0,
                no_repeat_ngram_size=3,
                early_stopping=True,
            )
        return [
            self._tokenizer.decode(row, skip_special_tokens=True).strip() for row in generated
        ]

    def summarize_batched(
        self, texts: Sequence[str], *, batch_size: int = DEFAULT_BATCH_SIZE
    ) -> Iterable[str]:
        """Summarize a long sequence in fixed-size batches."""
        for start in range(0, len(texts), batch_size):
            yield from self.summarize(texts[start : start + batch_size])
