# ADR-0001: Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-07-22
- **Deciders:** Archival Systems

## Context

This is a long-lived archival system intended to run for years and evolve across
many phases (DESIGN.md §16). Decisions made early — data model, API-vs-scraping,
compliance posture — will be questioned later, possibly by people who weren't
present. Without a durable record of *why*, we risk re-litigating settled
questions or silently reversing deliberate constraints.

## Decision

We will capture architecturally significant decisions as ADRs in `docs/adr/`,
using the Nygard format (`0000-template.md`). An ADR is immutable once Accepted;
reversing it means writing a new ADR that marks the prior one *Superseded*.

## Alternatives Considered

- **A wiki / external doc** — drifts from the code, not versioned with it. Rejected.
- **Comments in code only** — invisible at the system level and easily lost. Rejected.
- **No formal record** — cheapest now, most expensive later. Rejected.

## Consequences

- A small per-decision writing cost, repaid whenever "why is it this way?" arises.
- ADRs live and version alongside the code and are reviewed in the same PRs.
- The index in `README.md` must be kept current when ADRs are added.
