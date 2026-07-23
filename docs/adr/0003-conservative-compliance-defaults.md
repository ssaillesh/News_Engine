# ADR-0003: Conservative-by-default compliance posture

- **Status:** Accepted
- **Date:** 2026-07-22
- **Deciders:** Archival Systems

## Context

Automated collection from Truth Social touches several constraints simultaneously:
the site's Terms of Service (which restrict automated access), `robots.txt` and
machine-readable directives, an authentication boundary that separates "public" from
"private" content, and applicable law (computer-misuse statutes, contract/ToS,
copyright in posts and media, data-protection regimes). These vary by jurisdiction
and over time, and are ultimately the operator's responsibility to evaluate — not
something software can decide. See DESIGN.md §1.8.

The engineering risk is that convenience defaults quietly push the system past what
the operator actually intends or is permitted to do.

## Decision

The system ships with the **most conservative posture by default**, and every
escalation is an explicit, logged, config-gated operator decision:

| Switch | Default | Meaning of default |
|--------|---------|--------------------|
| `RESPECT_ROBOTS` | `true` | Honor robots.txt on any HTML surface. |
| `ENABLE_AUTH` | `false` | Public-only; no credentialed access (auth carries ToS implications). |
| `ENABLE_HTML_FALLBACK` | `false` | No headless-browser scraping. |
| `DOWNLOAD_MEDIA` | `false` | Store media references, not binaries. |
| `ARCHIVE_FOREIGN_REPLIES` | `false` | Do not collect third parties' replies. |
| `RATE_LIMIT_RPS` | `0.5` | Low, single-tenant request rate. |

Additional guardrails enforced in code:

- `ENABLE_HTML_FALLBACK=true` **with** `RESPECT_ROBOTS=false` is rejected at
  configuration load — robots enforcement cannot be silently disabled via config.
- The collector is strictly read-only (`GET`-only); it can never post, edit, or
  delete on the target.
- Server rate signals (`Retry-After`, rate-limit headers) always override local
  limits; on a hard block the target enters a DEGRADED state and alerts, rather than
  attempting evasion.
- Scope is **public content of a single account** for personal research; private,
  follower-only, or DM content is never fetched, and redistribution is out of scope.

## Alternatives Considered

- **Permissive defaults with opt-out** — faster to demo, but makes the risky path the
  path of least resistance. Rejected.
- **Hard-code the conservative behavior with no switches** — safe but useless if the
  operator has a legitimate, ToS-compatible reason to change one knob. Rejected in
  favor of explicit, logged escalation.

## Consequences

- The default build cannot do anything a cautious reviewer would object to.
- Enabling a riskier capability requires an intentional configuration change that is
  recorded in logs, creating an audit trail of operator intent.
- Compliance responsibility sits explicitly with the operator, where it belongs; the
  software makes the safe choice easy and the risky choice deliberate.
- Phase 0 (DESIGN.md §16) remains a real go/no-go gate that can halt the project.
