# Architecture Decision Records

This directory records significant architectural decisions using
[Michael Nygard's ADR format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
Each ADR is immutable once accepted; a later decision that changes it gets a new
number and marks the old one *Superseded*.

| # | Title | Status |
|---|-------|--------|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-prefer-mastodon-api-over-html-scraping.md) | Prefer the Mastodon-compatible API over HTML scraping | Accepted |
| [0003](0003-conservative-compliance-defaults.md) | Conservative-by-default compliance posture | Accepted |
| [0004](0004-phase0-cloudflare-no-anonymous-access.md) | Phase 0: no anonymous access to Truth Social; build a generic Mastodon client | Accepted |

Start a new ADR by copying [`0000-template.md`](0000-template.md).
