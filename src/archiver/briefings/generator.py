"""Ask Claude for a structured, market-focused breakdown of one story.

Two input paths, chosen by what we already hold:

* **Full text on file** (Federal Register bodies, White House releases): the
  text goes straight into the prompt. No fetching, fastest and cheapest.
* **Headline only** (almost every news item): Claude gets the link plus the
  server-side ``web_fetch`` and ``web_search`` tools. Fetching happens on
  Anthropic's side and honours robots.txt; it cannot render JavaScript, and
  Google News redirect links are often longer than the fetch tool accepts, so
  search is there to locate the same article by headline and outlet. When
  neither works the model says so through ``source_quality`` rather than
  inventing detail from a headline.

The output is a validated :class:`Briefing` via structured outputs, so the UI
renders fields, never free-form prose it has to parse.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from archiver.storage.models import Status

DEFAULT_MODEL = "claude-opus-5"

# Below this many characters the stored text is a headline plus a feed blurb,
# not an article worth analysing directly.
_FULL_TEXT_MIN_CHARS = 1500
# Long executive orders run to hundreds of thousands of characters. Beyond this
# the prompt says explicitly that the document was cut, so the model never
# presents a partial reading as the whole.
_MAX_DOCUMENT_CHARS = 400_000

_MAX_TURNS = 4  # server tools can pause a long turn; resume a bounded number of times

Direction = Literal["positive", "negative", "mixed", "uncertain"]


class Effect(BaseModel):
    area: str = Field(description="What is affected, e.g. 'Steel importers' or 'Consumer prices'.")
    direction: Direction
    explanation: str = Field(description="One or two sentences on the mechanism.")


class CompanyImpact(BaseModel):
    name: str
    ticker: str | None = Field(description="US ticker if publicly traded, else null.")
    direction: Direction
    explanation: str


class Briefing(BaseModel):
    bottom_line: str = Field(description="Two sentences a busy investor needs first.")
    what_happened: str
    why_it_matters: str
    how_it_impacts: str = Field(
        description="The chain from this action to prices, costs, demand or earnings."
    )
    whats_being_done: str = Field(description="Concrete actions, deadlines, and what happens next.")
    trump_position: str = Field(
        description="What Trump said or did about it, and whether he framed it positively or negatively."
    )
    economic_effects: list[Effect]
    sectors: list[Effect]
    companies: list[CompanyImpact]
    key_dates: list[str] = Field(
        description="Effective dates and deadlines as 'YYYY-MM-DD: what happens'."
    )
    open_questions: str = Field(description="What is still unknown or disputed.")
    source_quality: Literal["full_text", "partial", "headline_only"] = Field(
        description="full_text if you read the whole article or document; partial if only part; headline_only if you could not read it."
    )


SYSTEM_PROMPT = """You are the markets desk of a news service that tracks the Trump administration's actions and statements.

For the story you are given, write a detailed, specific breakdown for readers who want to know how it affects the economy and markets: what happened, why it matters, how it transmits into prices, costs, demand and earnings, which sectors and companies are exposed and in which direction, what is being done and when, and what Trump himself said or did about it.

Ground every claim in the source. Use numbers, dates, product categories, countries and named companies from the text wherever they appear. Separate what the source states from your own inference, and put genuine unknowns in open_questions rather than guessing. If you could not read the article itself, set source_quality to headline_only and keep the analysis to what the headline and excerpt support. Do not include tickers you are not confident exist. Write plainly, without hype."""


class BriefingUnavailable(Exception):
    """Analysis is not configured on this deployment (no SDK or no credentials)."""


class BriefingFailed(Exception):
    """A generation attempt failed; ``retryable`` says whether trying again can help."""

    def __init__(self, message: str, *, retryable: bool, limit_reached: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.limit_reached = limit_reached


@dataclass
class BriefingResult:
    briefing: Briefing
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    used_tools: list[str] = field(default_factory=list)


def build_prompt(status: Status) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(user message, server tools)`` for a status."""
    raw = status.raw or {}
    text = (status.content_text or "").strip()
    title = str(raw.get("title") or text.split("\n", 1)[0] or status.id).strip()
    outlet = raw.get("publisher") or status.kind or status.source
    published = status.created_at.date().isoformat() if status.created_at else "unknown"
    header = f"Headline: {title}\nSource: {outlet}\nPublished: {published}\n"

    if len(text) >= _FULL_TEXT_MIN_CHARS:
        body = text
        note = ""
        if len(body) > _MAX_DOCUMENT_CHARS:
            body = body[:_MAX_DOCUMENT_CHARS]
            note = (
                f"\nNote: the document is {len(text):,} characters; only the first "
                f"{_MAX_DOCUMENT_CHARS:,} are included. Say so if it limits the analysis.\n"
            )
        return (
            f"{header}{note}\nFull text:\n<document>\n{body}\n</document>\n\n"
            "Write the breakdown from this text.",
            [],
        )

    excerpt = text.split("\n", 1)[1].strip() if "\n" in text else ""
    link = status.url or ""
    return (
        f"{header}Link: {link}\n"
        + (f"Feed excerpt: {excerpt}\n" if excerpt else "")
        + "\nRead the full article at the link above. If it cannot be fetched, search for this "
        "same article by its headline and outlet and read that copy instead. Then write the breakdown.",
        [
            {
                "type": "web_fetch_20260209",
                "name": "web_fetch",
                "max_uses": 3,
                "max_content_tokens": 20000,
            },
            {"type": "web_search_20260209", "name": "web_search", "max_uses": 2},
        ],
    )


def _echo_content(content: list[Any]) -> list[dict[str, Any]]:
    """Assistant content to send back when resuming a paused turn.

    Parsed text blocks carry a client-side ``parsed_output`` field the API does
    not accept, so it is dropped; everything else is returned unchanged.
    """
    blocks = []
    for block in content:
        data = block.to_dict() if hasattr(block, "to_dict") else dict(block)
        data.pop("parsed_output", None)
        blocks.append(data)
    return blocks


class BriefingGenerator:
    """Wraps the Claude call. ``client`` is injectable so tests need no network."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        effort: str = "medium",
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self._client = client

    def available(self) -> bool:
        if self._client is not None:
            return True
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def _get_client(self) -> Any:
        if self._client is None:
            if not self.available():
                raise BriefingUnavailable(
                    "Detailed analysis needs ANTHROPIC_API_KEY set on the server."
                )
            import anthropic

            # One retry on top of the SDK's own handling; the web path fetches
            # pages server-side, so allow a generous per-request timeout.
            self._client = anthropic.AsyncAnthropic(timeout=150.0, max_retries=1)
        return self._client

    async def generate(self, status: Status) -> BriefingResult:
        client = self._get_client()
        import anthropic

        prompt, tools = build_prompt(status)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools

        result = BriefingResult(briefing=None, model=self.model)  # type: ignore[arg-type]
        for _ in range(_MAX_TURNS):
            try:
                response = await client.beta.messages.parse(
                    model=self.model,
                    max_tokens=16000,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    output_format=Briefing,
                    output_config={"effort": self.effort},
                    # Re-run a classifier decline on Anthropic's recommended
                    # fallback model instead of failing the reader's request.
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                    **kwargs,
                )
            except anthropic.AuthenticationError as exc:
                raise BriefingUnavailable("The Anthropic API key was rejected.") from exc
            except anthropic.RateLimitError as exc:
                raise BriefingFailed(
                    "Analysis is busy right now. Try again in a minute.", retryable=True
                ) from exc
            except anthropic.BadRequestError as exc:
                raise BriefingFailed(
                    f"The analysis request was rejected: {exc.message}", retryable=False
                ) from exc
            except anthropic.APIStatusError as exc:
                raise BriefingFailed(
                    "The analysis service had an error. Try again.",
                    retryable=exc.status_code >= 500,
                ) from exc
            except anthropic.APIConnectionError as exc:
                raise BriefingFailed(
                    "Couldn't reach the analysis service. Try again.", retryable=True
                ) from exc

            usage = getattr(response, "usage", None)
            if usage is not None:
                result.input_tokens += getattr(usage, "input_tokens", 0) or 0
                result.output_tokens += getattr(usage, "output_tokens", 0) or 0
            for block in response.content:
                if getattr(block, "type", "") == "server_tool_use":
                    result.used_tools.append(getattr(block, "name", ""))
            result.model = getattr(response, "model", self.model) or self.model

            if response.stop_reason == "pause_turn":
                messages = [
                    *messages,
                    {"role": "assistant", "content": _echo_content(response.content)},
                ]
                continue
            if response.stop_reason == "refusal":
                raise BriefingFailed("The model declined to analyse this story.", retryable=False)
            if response.stop_reason == "max_tokens":
                raise BriefingFailed("The analysis ran too long and was cut off.", retryable=True)
            if response.parsed_output is None:
                raise BriefingFailed(
                    "The analysis came back in an unexpected shape.", retryable=True
                )
            result.briefing = response.parsed_output
            return result

        raise BriefingFailed("Reading the article took too many steps. Try again.", retryable=True)
