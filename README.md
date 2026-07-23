# Truth Social Archiver

A continuously running, self-healing archival system for the **publicly accessible**
content of a single Truth Social account, built for long-term personal research and
preservation.

> **Status:** Phases 1–4 + first live source. Config/logging/CLI, storage schema &
> migrations, a provider-agnostic Mastodon API client, the parser/normalizer, and a
> working **Federal Register ingester** that pulls Trump's official presidential
> documents into the archive — a free, public-domain, fully compliant live source.
> Phase 0 confirmed Truth Social blocks anonymous automated access at Cloudflare,
> so the client is pointed at any Mastodon-compatible instance you are authorized
> to access and it **detects-and-halts** on anti-bot blocks rather than
> circumventing them
> ([docs/adr/0004](docs/adr/0004-phase0-cloudflare-no-anonymous-access.md)).
> See [DESIGN.md](DESIGN.md) for the full blueprint and [docs/adr/](docs/adr/) for decisions.

## Read this first — compliance posture

This project is scoped to **public content of a single public-figure account** for
**personal research/archival**. It ships with the most conservative defaults:
robots.txt respected, no authentication, public-only, low request rate, and no
HTML-scraping fallback. Every escalation is an explicit, logged operator decision.
You are responsible for evaluating the target site's Terms of Service and applicable
law for your jurisdiction before enabling any collection. See **DESIGN.md §1.8** and
**docs/adr/0003**.

## Quick start (Phase 1)

```bash
# 1. Create an environment and install (editable + dev tools)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env        # edit as needed

# 3. Explore the scaffold (safe — no network access)
archiver version
archiver config             # prints the resolved config with secrets masked
archiver doctor             # validates configuration loads correctly

# 4. Apply the database schema (SQLite by default; Postgres via DATABASE_URL)
alembic upgrade head

# 5. Dev workflow
make test                   # pytest on SQLite (fast, no Docker)
make lint                   # ruff + mypy

# Verify Postgres portability too (production backend):
make pg-up                  # throwaway Postgres 16 container (needs Docker)
pip install -e ".[postgres]"
make test-postgres          # runs the integration guarantees against Postgres
make pg-down
```

The integration suite is **backend-agnostic**: it runs on SQLite by default and
against Postgres when `TEST_DATABASE_URL` is set. Both are exercised so
Postgres-only issues (e.g. `JSONB` vs `JSON`, `BIGSERIAL` autoincrement) cannot
hide behind SQLite.

## What exists now

| Area | Status |
|------|--------|
| Layered config (defaults → profile YAML → `.env` → env vars) | ✅ |
| Compliance switches wired into config & validated | ✅ |
| Secret-scrubbing structured logging | ✅ |
| Typer CLI (`version`, `config`, `doctor`, `probe`) | ✅ |
| Normalized schema — 16 tables (DESIGN §6), ORM + Alembic | ✅ |
| Async DB layer, portable SQLite ↔ PostgreSQL | ✅ |
| Idempotent-upsert repositories + raw-payload store | ✅ |
| Mastodon API client — pagination, rate-limit, retry/backoff | ✅ |
| Block detection (Cloudflare 403 → halt, no evasion) | ✅ |
| Parser: version-tolerant schemas + normalizer + content hashing | ✅ |
| **Presidential Documents (CPD) ingester — his remarks/statements** | ✅ |
| **Federal Register ingester — live, compliant Trump source** | ✅ |
| **White House RSS ingester — statements/releases/messages** | ✅ |
| **Trump news ingester — Google News RSS, filtered to Trump** | ✅ |
| **Incremental/checkpointed ingest (cheap scheduled runs)** | ✅ |
| **Web UI — dashboard + JSON API (`archiver serve`)** | ✅ |
| Multi-source archive (`source` column: mastodon/federal_register/…) | ✅ |
| Parser tests: fixtures, golden, hypothesis fuzz, parse→store | ✅ |
| Tests: config, storage, client contract, source ingest, web, opt-in live | ✅ |
| Full scheduler daemon / observability stack | ⛔ later phases (see DESIGN.md §16) |

### Get real data now, then browse it

```bash
alembic upgrade head                    # create the schema
archiver ingest-presidential-documents  # his REMARKS, statements, messages (his own words)
archiver ingest-federal-register        # executive orders, proclamations, memoranda
archiver ingest-white-house             # White House statements, releases (RSS)
archiver ingest-news                    # news coverage ABOUT Trump (Google News RSS)
archiver serve                          # → http://127.0.0.1:8137  (browse the archive)
```

Four live, compliant sources feed one archive:

| Command | Source | Content |
|---------|--------|---------|
| `ingest-presidential-documents` | [GovInfo CPD API](https://api.govinfo.gov/docs/) (public domain) | **Trump's remarks, statements, messages** — his own words |
| `ingest-federal-register` | [Federal Register API](https://www.federalregister.gov/developers/documentation/api/v1) (public domain) | Executive orders, proclamations, memoranda |
| `ingest-white-house` | whitehouse.gov RSS (robots-permitted) | Statements, releases, presidential messages |
| `ingest-news` | Google News RSS | **News coverage about Trump**, strictly keyword-filtered to him; publisher shown as the badge |

All are compliant counterparts to the blocked Truth Social social feed
([docs/adr/0004](docs/adr/0004-phase0-cloudflare-no-anonymous-access.md)). The
Federal Register supports `--incremental` (checkpointed). GovInfo CPD needs a free
`GOVINFO_API_KEY` from [api.data.gov](https://api.data.gov/signup/) (`DEMO_KEY`
works but is rate-limited).

**Schedule it** (only fetch what's new) with `--incremental`, e.g. via cron:

```cron
*/30 * * * *  cd /path/to/repo && archiver ingest-federal-register --incremental
```

`archiver serve` starts a read-only dashboard (search, source filter, links to the
originals) plus a JSON API (`/api/statuses`, `/api/stats`). Install the web extra
first: `pip install -e ".[web]"`.

## Roadmap

Implementation is phased in [DESIGN.md §16](DESIGN.md). Phase 0 is a compliance &
feasibility spike that can legitimately halt the project if automated access is
impermissible — that is by design.
