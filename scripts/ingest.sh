#!/bin/bash
# Scheduled incremental ingest for the Trump News Archive.
# Invoked by ~/Library/LaunchAgents/com.saillesh.trump-news-ingest.plist
set -u

PROJECT_DIR="/Users/saillesh/Desktop/trump_news"
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
  echo "===== $(date -u +%FT%TZ) done ====="
} >>"$LOG" 2>&1
