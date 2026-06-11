# NLP News Intelligence Pipeline

Entity-level sentiment analysis on financial news using `dslim/bert-base-NER` + `ProsusAI/finbert`.

---

## Architecture

```
AlphaVantage ─┐
FinnHub       ├──► Merge & Dedup ──► Redis Stream ──► NLP Worker
yfinance      ┘                            │
                                           ▼
                              ┌────────────────────────┐
                              │     NLP Core           │
                              │  BERT-NER (ORG only)   │
                              │  FinBERT (±2 sentence) │
                              └────────────────────────┘
                                           │
                        ┌──────────────────┼──────────────────┐
                        ▼                  ▼                  ▼
                   Raw Store         NLP Store          Vector Store
                  (immutable)     (entities+sent)    (FAISS embeddings)
                                           │
                                    Event Clustering
                                   (HDBSCAN + scoring)
                                           │
                                     Event Store
                                   (hot topics + agg)
                                           │
                                      FastAPI
```

---

## Storage Layers

| Layer | What's stored | Format |
|-------|--------------|--------|
| **Raw** (`data/raw/`) | Original API responses, immutable | JSON per article |
| **NLP Processed** (`data/nlp_processed/`) | NER entities + FinBERT per-company sentiment | JSON + SQLite |
| **Events** (`data/events/`) | Clustered events, aggregated sentiment, hot scores | JSON + SQLite |
| **Vectors** (`data/vectors/`) | FAISS index + metadata sidecar | `.faiss` + JSON |

---

## Quick Start

### 1. Install
```bash
cd nlp_pipeline
cp .env.example .env
# Fill in ALPHA_VANTAGE_API_KEY and FINNHUB_API_KEY

pip install -r requirements.txt
```

### 2. Run batch pipeline
```bash
python main.py batch --tickers AAPL MSFT TSLA NVDA AMZN
```

### 3. Start API server
```bash
python main.py serve
# → http://localhost:8000/docs
```

### 4. Query results
```bash
# Top hot events
python main.py events --limit 10

# Company sentiment trend
python main.py sentiment --company Apple

# Via API
curl http://localhost:8000/events
curl http://localhost:8000/company/Apple/sentiment
```

---

## Docker

```bash
# Batch mode (no Redis needed)
docker-compose up api

# Streaming mode (Redis + worker)
docker-compose --profile streaming up
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/run/batch` | Trigger pipeline for tickers |
| `GET`  | `/events` | Top events by hot_score |
| `GET`  | `/events/{id}` | Full event detail |
| `GET`  | `/company/{name}/sentiment` | Company sentiment trend |
| `GET`  | `/articles/{id}` | Processed article detail |

---

## NLP Pipeline Detail

### NER
- Model: `dslim/bert-base-NER`
- Filters: `ORG` entities only
- Dedup: per-sentence, normalised company name

### Sentiment
- Model: `ProsusAI/finbert`
- Context: ±2 sentences around entity mention
- Output per entity: `positive`, `negative`, `neutral` + confidence scores

### Aggregation
```
EntityMention → company rollup (per article)
             → article-level sentiment (mention-weighted)
             → event-level sentiment (HDBSCAN cluster)
```

### Hot Score Formula
```
hot_score = 0.30 × mention_volume_normalised
          + 0.25 × velocity_normalised        (articles/hr)
          + 0.20 × sentiment_strength         (|weighted_score|)
          + 0.15 × source_diversity           (unique sources / 3)
          + 0.10 × novelty_score              (recency)
```

---

## Running Tests
```bash
pytest tests/ -v
```

Tests cover: normalisation, sentence splitting, context windows, sentiment rollup, model validation.
All tests run **without API keys** (mock data only).

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ALPHA_VANTAGE_API_KEY` | Yes | AlphaVantage API key |
| `FINNHUB_API_KEY` | Yes | FinnHub API key |
| `TORCH_DEVICE` | No | `cpu` or `cuda` (default: cpu) |
| `SENTIMENT_WINDOW_SIZE` | No | ±N sentences for FinBERT context (default: 2) |
| `MIN_CLUSTER_SIZE` | No | HDBSCAN min cluster size (default: 3) |
| `REDIS_HOST` | No | Redis host (default: localhost) |

See `.env.example` for full list.
