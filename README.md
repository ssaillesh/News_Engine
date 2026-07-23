# Trump News Archive

A continuously running archival system for **publicly accessible** records of Donald
Trump — his official presidential documents, his own remarks, White House releases,
and third-party news coverage about him — built for long-term personal research.
News coverage is scored for sentiment with **FinBERT**.

> **Status:** Four live, compliant sources feed one archive, browsable through a
> local dashboard, with an offline FinBERT sentiment pass over news coverage.
>
> The project originally targeted a single Truth Social account. Phase 0 confirmed
> Truth Social blocks anonymous automated access at Cloudflare
> ([docs/adr/0004](docs/adr/0004-phase0-cloudflare-no-anonymous-access.md)), and
> rather than circumvent that, the archive was rebuilt on public government APIs and
> syndication feeds. The Mastodon/Truth Social client has since been removed as dead
> code; the ADRs remain as the record of why the architecture is what it is.
> See [DESIGN.md](DESIGN.md) for the original blueprint and [docs/adr/](docs/adr/)
> for decisions.

## Read this first — compliance posture

This project is scoped to **public records about a public figure** for **personal
research/archival**. It ships with the most conservative defaults: robots.txt
respected, no authentication, public-only, low request rate, and no HTML scraping.
Three of the four sources are public-domain US government works; the fourth is a
public syndication feed whose items link back to their publishers. Nothing here
circumvents an access control — clients detect blocks and halt. You are responsible
for evaluating each source's Terms of Service and applicable law for your
jurisdiction. See **DESIGN.md §1.8** and **docs/adr/0003**.

## Quick start

```bash
# 1. Create an environment and install (editable + dev tools)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,web]"
pip install -e ".[sentiment]"   # optional: FinBERT scoring (pulls in torch)

# 2. Configure
cp .env.example .env        # edit as needed

# 3. Check the install (safe — no network access)
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

## Deploy to Vercel (Cloud Hosting)

To host your archive live on the web:

```bash
# 1. Get a PostgreSQL database (Neon, Supabase, AWS RDS, etc.)
# 2. Push your code to GitHub
# 3. Go to vercel.com and import this repo
# 4. Add DATABASE_URL environment variable
# 5. Deploy — the API is live at your Vercel domain
```

See **[VERCEL_DEPLOYMENT.md](VERCEL_DEPLOYMENT.md)** for detailed instructions.

---

## What exists now

| Area | Status |
|------|--------|
| Layered config (defaults → profile YAML → `.env` → env vars) | ✅ |
| Compliance switches wired into config & validated | ✅ |
| Secret-scrubbing structured logging | ✅ |
| Typer CLI (`version`, `config`, `doctor`, `ingest-*`, `score-sentiment`, `summarize`, `serve`) | ✅ |
| Normalized schema — 18 tables (DESIGN §6), ORM + Alembic | ✅ |
| Async DB layer, portable SQLite ↔ PostgreSQL | ✅ |
| Idempotent-upsert repositories + raw-payload store | ✅ |
| Shared HTTP client — rate-limit, retry/backoff | ✅ |
| Block detection (Cloudflare 403 → halt, no evasion) | ✅ |
| **Presidential Documents (CPD) ingester — his remarks/statements** | ✅ |
| **Federal Register ingester — live, compliant Trump source** | ✅ |
| **White House RSS ingester — statements/releases/messages** | ✅ |
| **Trump news ingester — Google News RSS, filtered to Trump** | ✅ |
| **Publisher-RSS ingester — coverage with real summaries, de-duped** | ✅ |
| **FinBERT sentiment pass over news coverage** | ✅ |
| **distilbart summarization pass — labeled AI condensation** | ✅ |
| **Incremental/checkpointed ingest (cheap scheduled runs)** | ✅ |
| **Web UI — dashboard + JSON API (`archiver serve`)** | ✅ |
| Multi-source archive (`source` column: news/federal_register/…) | ✅ |
| Tests: config, storage, source ingest, sentiment, web | ✅ |
| Full scheduler daemon / observability stack | ⛔ later phases (see DESIGN.md §16) |

### Get real data now, then browse it

```bash
alembic upgrade head                    # create the schema
archiver ingest-presidential-documents  # his REMARKS, statements, messages (his own words)
archiver ingest-federal-register        # executive orders, proclamations, memoranda
archiver ingest-white-house             # White House statements, releases (RSS)
archiver ingest-news                    # news coverage ABOUT Trump (Google News headlines)
archiver ingest-publishers              # news coverage WITH summaries (publisher RSS)
archiver score-sentiment                # FinBERT sentiment over the news coverage
archiver summarize                      # short AI condensation of longer articles
archiver serve                          # → http://127.0.0.1:8137  (browse the archive)
```

Five live, compliant sources feed one archive:

| Command | Source | Content |
|---------|--------|---------|
| `ingest-presidential-documents` | [GovInfo CPD API](https://api.govinfo.gov/docs/) (public domain) | **Trump's remarks, statements, messages** — his own words |
| `ingest-federal-register` | [Federal Register API](https://www.federalregister.gov/developers/documentation/api/v1) (public domain) | Executive orders, proclamations, memoranda |
| `ingest-white-house` | whitehouse.gov RSS (robots-permitted) | Statements, releases, presidential messages |
| `ingest-news` | Google News RSS | **News coverage about Trump** — broad reach, headline only; publisher shown as the badge |
| `ingest-publishers` | Publishers' own RSS (BBC, NPR, Guardian, Politico, The Hill, …) | **News coverage with real summaries** and direct article links; keyword-filtered to Trump, near-duplicate headlines de-duped against `ingest-news` |

All are compliant counterparts to the blocked Truth Social social feed
([docs/adr/0004](docs/adr/0004-phase0-cloudflare-no-anonymous-access.md)). The
Federal Register supports `--incremental` (checkpointed). GovInfo CPD needs a free
`GOVINFO_API_KEY` from [api.data.gov](https://api.data.gov/signup/) (`DEMO_KEY`
works but is rate-limited).

**Schedule it** (only fetch what's new) with `--incremental`, e.g. via cron:

```cron
*/30 * * * *  cd /path/to/repo && archiver ingest-federal-register --incremental
```

`archiver serve` starts a read-only dashboard (search, source/type/sentiment
filters, links to the originals) plus a JSON API (`/api/statuses`, `/api/stats`,
`/api/facets`). Install the web extra first: `pip install -e ".[web]"`.

## Sentiment (FinBERT)

`archiver score-sentiment` runs [ProsusAI/finbert](https://huggingface.co/ProsusAI/finbert)
over archived headlines and stores one reading per item in `status_sentiment`:
the full `positive` / `negative` / `neutral` distribution, the winning `label`,
its confidence `score`, and `compound` (positive − negative, in `[-1, 1]`) as a
single signed number to sort and average on.

```bash
pip install -e ".[sentiment]"     # torch + transformers (~500 MB, optional)
archiver score-sentiment          # scores source=news by default
archiver score-sentiment --source whitehouse --source news
archiver score-sentiment --rescore --device mps   # redo everything on Apple silicon
```

It is an **offline enrichment pass**: it fetches nothing, never modifies the
captured record, and writes only to its own table — so it is safe to re-run and
fully re-derivable. Runs are incremental. Only items that have never been scored,
whose text changed since scoring, or that were scored with a different model get
sent to the GPU/CPU, which makes it cheap to chain after each ingest:

```cron
*/30 * * * *  cd /path/to/repo && archiver ingest-publishers && archiver score-sentiment && archiver summarize
```

Two caveats worth knowing. FinBERT is fine-tuned on **financial** news, so it
reads market-flavored language most reliably and is applied here to general
political coverage somewhat off-label — treat readings as a rough signal, not
ground truth. And it scores the **headline**, which is the publisher's framing of
an event rather than Trump's own sentiment or the event's. Federal Register and
presidential-document legalese is left unscored by default for the same reason:
it falls outside the model's training distribution and yields mostly
low-confidence neutral.

## Summaries

Each news item shows the **publisher's own summary** where one exists — this comes
from `ingest-publishers` (Google News items are headline-only) and is stored
verbatim in `statuses.content_text`, never paraphrased.

`archiver summarize` additionally runs
[distilbart-cnn](https://huggingface.co/sshleifer/distilbart-cnn-12-6) over the
longer articles to generate a short abstractive condensation, stored separately in
`status_summary` and shown in its own **AI-generated** panel in the dashboard.

```bash
archiver summarize                       # source=news, articles with a real body
archiver summarize --regenerate --device mps
archiver summarize --min-chars 300       # lower the "too short to condense" floor
```

Same offline, incremental, re-derivable contract as the sentiment pass. **Read the
generated summaries as a rough gist, not a citation.** Abstractive summarization
writes *new* sentences, and on political reporting it can drop a qualifier or, in
the worst case, invent a detail — one summary in the current run turned "Lindsey
Graham's seat" into a fictional "Sen. Darline Graham." That is exactly why the
generated text is kept in its own labeled panel, never overwrites the publisher's
words, and links straight to the original. Only articles with a real body (≥ 400
chars by default) are summarized; short blurbs are skipped rather than risk
padding them with invention.

## Roadmap

Implementation is phased in [DESIGN.md §16](DESIGN.md). Phase 0 is a compliance &
feasibility spike that can legitimately halt the project if automated access is
impermissible — that is by design.
