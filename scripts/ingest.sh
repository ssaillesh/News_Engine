#!/bin/bash
# Scheduled incremental ingest for the Trump News Archive.
# Invoked by ~/Library/LaunchAgents/com.saillesh.trump-news-ingest.plist
set -u

# The repo this script lives in, wherever it has been moved to.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$PROJECT_DIR/.venv/bin"
LOG="$PROJECT_DIR/logs/ingest.log"
LOCK="$PROJECT_DIR/.ingest.lock"

cd "$PROJECT_DIR" || exit 1

# A run that outlives its slot must not overlap the next one. mkdir is atomic,
# so it doubles as the lock. Clear a lock left behind by a killed run.
if [ -d "$LOCK" ] && [ -z "$(find "$LOCK" -maxdepth 0 -mmin -120 2>/dev/null)" ]; then
  echo "$(date -u +%FT%TZ) clearing stale lock" >>"$LOG"
  rmdir "$LOCK" 2>/dev/null
fi
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date -u +%FT%TZ) skipped — previous run still active" >>"$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

{
  echo "===== $(date -u +%FT%TZ) start ====="
  # RSS sources are self-bounding (feeds only carry recent items).
  # Federal Register needs --incremental or it refetches back to 2017.
  "$BIN/archiver" ingest-news
  "$BIN/archiver" ingest-publishers
  "$BIN/archiver" ingest-presidential-documents
  "$BIN/archiver" ingest-federal-register --incremental
  "$BIN/archiver" ingest-white-house
  # Same enrichment as the GitHub workflow, so new items arrive with their
  # companies, sectors, topics, stance and impact score. All incremental.
  "$BIN/archiver" backfill-federal-register-text --limit 50
  "$BIN/archiver" detect-stocks
  "$BIN/archiver" classify
  echo "===== $(date -u +%FT%TZ) done ====="
} >>"$LOG" 2>&1
