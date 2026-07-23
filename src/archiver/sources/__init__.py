"""First-party data sources the archiver can ingest compliantly.

Each source is an adapter that maps an external, *authorized* API into the
storage schema (via the same row-dict contract the parser produces). The first
source is the Federal Register — Trump's official presidential documents, a free,
open, machine-readable government API (public-domain works, no anti-bot barrier).
"""
