"""
config/settings.py
Centralised settings — loaded once at startup from .env
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths (file-based storage layers) ────────────────────────────────────────
BASE_DIR          = Path(os.getenv("STORAGE_BASE_DIR",  "./data"))
RAW_STORE_DIR     = Path(os.getenv("RAW_STORE_DIR",     "./data/raw"))
NLP_STORE_DIR     = Path(os.getenv("NLP_STORE_DIR",     "./data/nlp_processed"))
EVENTS_STORE_DIR  = Path(os.getenv("EVENTS_STORE_DIR",  "./data/events"))
VECTOR_STORE_DIR  = Path(os.getenv("VECTOR_STORE_DIR",  "./data/vectors"))

# Ensure all dirs exist at import time
for _d in (RAW_STORE_DIR, NLP_STORE_DIR, EVENTS_STORE_DIR, VECTOR_STORE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── PostgreSQL ─────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://nlp_user:nlp_password@localhost:5432/nlp_pipeline",
)

# ── API Keys ──────────────────────────────────────────────────────────────────
ALPHA_VANTAGE_API_KEY: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
FINNHUB_API_KEY:       str = os.getenv("FINNHUB_API_KEY",       "")

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_HOST:           str = os.getenv("REDIS_HOST",           "localhost")
REDIS_PORT:           int = int(os.getenv("REDIS_PORT",       "6379"))
REDIS_DB:             int = int(os.getenv("REDIS_DB",         "0"))
REDIS_STREAM_NAME:    str = os.getenv("REDIS_STREAM_NAME",    "news_articles")
REDIS_CONSUMER_GROUP: str = os.getenv("REDIS_CONSUMER_GROUP", "nlp_workers")

# ── NLP Models ────────────────────────────────────────────────────────────────
NER_MODEL:       str = os.getenv("NER_MODEL",       "dslim/bert-base-NER")
SENTIMENT_MODEL: str = os.getenv("SENTIMENT_MODEL", "ProsusAI/finbert")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
TORCH_DEVICE:    str = os.getenv("TORCH_DEVICE",    "cpu")

# ── Pipeline Tuning ───────────────────────────────────────────────────────────
DEDUP_SIMILARITY_THRESHOLD: float = float(os.getenv("DEDUP_SIMILARITY_THRESHOLD", "0.92"))
SENTIMENT_WINDOW_SIZE:      int   = int(os.getenv("SENTIMENT_WINDOW_SIZE",        "2"))
MIN_CLUSTER_SIZE:           int   = int(os.getenv("MIN_CLUSTER_SIZE",             "3"))
BATCH_SIZE:                 int   = int(os.getenv("BATCH_SIZE",                   "32"))
MAX_ARTICLES_PER_SOURCE:    int   = int(os.getenv("MAX_ARTICLES_PER_SOURCE",      "50"))
