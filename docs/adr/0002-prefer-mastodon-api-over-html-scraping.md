# ADR-0002: Prefer the Mastodon-compatible API over HTML scraping

- **Status:** Accepted
- **Date:** 2026-07-22
- **Deciders:** Archival Systems

## Context

Truth Social runs on a Soapbox/Mastodon-derived backend and its web client is a
single-page app that consumes a Mastodon-compatible REST/ActivityPub API
(`/api/v1/accounts/*`, `/api/v1/statuses/*`). Two collection strategies are
therefore available: (a) consume the structured JSON API the SPA already uses, or
(b) render pages in a headless browser and parse the resulting HTML/DOM.

Structured JSON gives stable snowflake IDs, `created_at`/`edited_at`, reblog
pointers, media metadata, mentions, tags, and edit history — which directly enable
the hardest archival requirements (deduplication, edit/deletion detection,
normalization). HTML is brittle: layout changes silently break selectors, and much
metadata is absent or lossy after rendering.

Both strategies are subject to the same compliance constraints (see ADR-0003); this
ADR is only about the *technical* preference **given** that collection is permitted.

## Decision

The **primary** collection path will consume the Mastodon-compatible JSON API.
Headless-browser HTML scraping is retained only as an **isolated, config-gated,
last-resort fallback** for surfaces the API cannot provide or when the API is
unreachable, and it is **off by default** (`ENABLE_HTML_FALLBACK=false`).

## Alternatives Considered

- **HTML scraping as primary** — maximal fragility, lossy metadata, higher render
  cost, and easier to trip bot mitigation. Rejected as primary.
- **API-only, no fallback at all** — simplest, but leaves us with no path if the API
  shape/gate changes. Rejected in favor of a gated fallback.

## Consequences

- The parser targets a JSON schema via a version-tolerant anti-corruption layer
  (DESIGN.md §1.6, §8); most upstream drift is absorbed without touching core logic.
- Raw payloads are captured before parsing, enabling re-derivation after parser fixes.
- The fragile HTML path is quarantined behind a flag so its brittleness cannot infect
  the main pipeline.
- Playwright/browser dependencies are optional and excluded from the default image.
