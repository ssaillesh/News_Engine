# ADR-0004: Phase 0 found no anonymous access to Truth Social; build a generic Mastodon client instead

- **Status:** Accepted
- **Date:** 2026-07-22
- **Deciders:** Archival Systems (operator decision on record)

## Context

Phase 0 (DESIGN.md §16) is the feasibility/compliance spike that gates any
network-touching code. It was run against `truthsocial.com` with these results:

| Probe | Result |
|-------|--------|
| `GET /robots.txt` | HTTP 200, **empty (0 bytes)** — no machine-readable directives |
| `GET /` (homepage) | **HTTP 403**, `server: cloudflare`, `cf-ray`, sets `__cf_bm` |
| `GET /api/v1/accounts/lookup?acct=realDonaldTrump` | **HTTP 403**, ~4.5 KB **HTML challenge page** (not JSON) |

Both browser-style and bot-style User-Agents received the 403 challenge. The
Mastodon-compatible API does **not** answer anonymous HTTP clients; Cloudflare
bot-management blocks them at the edge.

Interpretation: Truth Social has a deliberate **technical access-control barrier**
in front of all content. Getting past it requires either (a) circumventing the
anti-bot measure (headless-challenge-solving, TLS-fingerprint impersonation) or
(b) authenticating with a logged-in session — which means the content is not
"publicly accessible" in this project's scope and is ToS-restricted.

## Decision

1. **No-go for anonymous scraping of Truth Social.** We will not build tooling
   whose purpose is to circumvent the anti-bot barrier. This honors the
   conservative posture of ADR-0003 and the project's non-goals (DESIGN.md
   Appendix C): *no detection-evasion; if blocked, stop and surface.*

2. **Build Phase 3 as a provider-agnostic Mastodon-compatible client.** The fetch
   layer speaks the standard Mastodon REST API and is pointed at
   ``api_base_url`` — any instance the operator is authorized to access. It is
   validated against respx mocks and a permitted public instance
   (mastodon.social). It contains **no** evasion.

3. **Detect-and-halt on blocks.** The client recognizes a Cloudflare-style 403/503
   HTML challenge and raises a terminal ``BlockedError`` (no retry, no
   circumvention), so the system can enter a DEGRADED state and alert.

4. **Escalation remains an explicit operator decision.** If the operator has
   authorized access (a token/permitted path within ToS), they configure
   ``ENABLE_AUTH`` + ``AUTH_TOKEN`` and ``api_base_url`` themselves. Compliant
   alternatives (existing public research datasets, licensed access) are preferred
   and recorded in DESIGN.md §1.8.

## Alternatives Considered

- **Headless-browser / TLS-impersonation to defeat Cloudflare** — this is
  circumvention of an access control; out of scope and rejected (ADR-0003,
  non-goals).
- **Authenticate and scrape via the API** — crosses the public/private boundary
  and is ToS-restricted; only viable if the operator independently holds
  authorized access, which is their decision, not a default of this software.
- **Ingest an existing public dataset** — fully compliant and may moot collection
  entirely; remains the recommended path for this specific account and can be
  built as a separate ingester over the same schema.

## Consequences

- The shipped client is genuinely useful (works against any Mastodon instance) and
  cannot, by itself, breach Truth Social's barrier.
- Pointing it at `truthsocial.com` anonymously will simply raise ``BlockedError``
  and stop — the correct, honest behavior.
- The compliance decision and its evidence are recorded here, with accountability
  resting on the operator for any authorized-access configuration.
