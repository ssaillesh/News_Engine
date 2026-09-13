"""Write briefings with an open-source model served by Ollama.

Free to run — it is meant for the scheduled GitHub Actions job, on a CPU runner,
with no API key. The trade-offs are deliberate and worth knowing:

* It runs ahead of time on the newest stories, not when a reader clicks.
* It only sees text we hand it; there is no web search or fetch.
* A small model is less reliable than a frontier one, so the prompt keeps it
  close to the source and ``source_quality`` is set by us, not by the model.

Output is constrained to the :class:`Briefing` JSON schema through Ollama's
structured outputs, then validated with Pydantic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
from pydantic import ValidationError

from archiver.briefings.generator import (
    Briefing,
    BriefingFailed,
    BriefingResult,
    BriefingUnavailable,
)

if TYPE_CHECKING:
    from archiver.storage.models import Status

DEFAULT_LOCAL_MODEL = "qwen3:4b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

# A 4B model on four CPU cores: keep the prompt to roughly 10k tokens so one
# story takes minutes, not an hour. The prompt says when text was cut.
_MAX_TEXT_CHARS = 40_000

LOCAL_SYSTEM_PROMPT = """You are a markets analyst. You are given one news story or government document about the Trump administration. Explain, using only facts stated in the text, how it affects the economy and markets.

Fill every field of the JSON object:
- bottom_line: two sentences an investor should read first.
- what_happened: the concrete action or event.
- why_it_matters: why it is economically significant.
- how_it_impacts: the chain from this action to prices, costs, demand, jobs or company earnings.
- whats_being_done: actions, deadlines and next steps named in the text.
- trump_position: what Trump said or did about it, and whether he framed it positively or negatively. Say "Not stated in the text." if it is not there.
- economic_effects and sectors: each item has area, direction (positive, negative, mixed or uncertain) and a one-sentence explanation.
- companies: only companies named in the text. Use a ticker only if you are certain; otherwise null.
- key_dates: dates from the text as "YYYY-MM-DD: what happens".
- open_questions: what the text leaves unclear.
- source_quality: "full_text".

Do not invent numbers, companies, quotes or dates. Use empty lists when the text has nothing for a field. Write plainly."""


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve ``$defs`` references so the schema is one self-contained object."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    resolved: dict[str, Any] = walk(schema)
    return resolved


BRIEFING_SCHEMA = _inline_refs(Briefing.model_json_schema())


def local_prompt(status: Status, text: str) -> tuple[str, bool]:
    """Return ``(user message, was_truncated)``."""
    raw = status.raw or {}
    title = str(raw.get("title") or text.split("\n", 1)[0] or status.id).strip()
    outlet = raw.get("publisher") or status.kind or status.source
    published = status.created_at.date().isoformat() if status.created_at else "unknown"
    truncated = len(text) > _MAX_TEXT_CHARS
    body = text[:_MAX_TEXT_CHARS]
    note = (
        f"\nNote: only the first {_MAX_TEXT_CHARS:,} of {len(text):,} characters are included.\n"
        if truncated
        else ""
    )
    return (
        f"Headline: {title}\nSource: {outlet}\nPublished: {published}\n{note}\n"
        f"<text>\n{body}\n</text>",
        truncated,
    )


class LocalBriefingGenerator:
    """Talks to a local Ollama server. ``transport`` is injectable for tests."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_LOCAL_MODEL,
        base_url: str = DEFAULT_OLLAMA_URL,
        timeout_s: float = 1800.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._transport = transport

    @property
    def label(self) -> str:
        return f"ollama/{self.model}"

    async def generate(self, status: Status, text: str) -> BriefingResult:
        prompt, truncated = local_prompt(status, text)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": LOCAL_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "format": BRIEFING_SCHEMA,
            "stream": False,
            "think": False,  # thinking roughly doubles CPU time for little gain here
            "options": {"temperature": 0.2, "num_ctx": 16384},
            "keep_alive": "30m",
        }
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout_s, transport=self._transport
        ) as client:
            last_error = ""
            for _ in range(2):  # one retry if the model's JSON fails validation
                try:
                    resp = await client.post("/api/chat", json=payload)
                except httpx.TimeoutException as exc:
                    raise BriefingFailed(
                        f"The model took longer than {self.timeout_s:.0f}s.", retryable=True
                    ) from exc
                except httpx.HTTPError as exc:
                    # Nothing else in the run can succeed without the server.
                    raise BriefingUnavailable(
                        f"Couldn't reach Ollama at {self.base_url}: {exc}"
                    ) from exc
                if resp.status_code != 200:
                    raise BriefingFailed(
                        f"Ollama returned {resp.status_code}: {resp.text[:200]}",
                        retryable=resp.status_code >= 500,
                    )
                data = resp.json()
                if data.get("done_reason") == "length":
                    last_error = "the answer was cut off"
                    continue
                try:
                    briefing = Briefing.model_validate_json(data["message"]["content"])
                except (ValidationError, KeyError, TypeError) as exc:
                    last_error = str(exc)[:200]
                    continue
                # What the model read is a fact we know; don't let it guess.
                briefing.source_quality = "partial" if truncated else "full_text"
                return BriefingResult(
                    briefing=briefing,
                    model=self.label,
                    input_tokens=int(data.get("prompt_eval_count") or 0),
                    output_tokens=int(data.get("eval_count") or 0),
                )
        raise BriefingFailed(f"The model's answer was unusable: {last_error}", retryable=True)
