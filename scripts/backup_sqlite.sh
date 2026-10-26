#!/usr/bin/env bash
# SQLite backup for Swing Desk personal DB (Phase 7).
# Usage: ./scripts/backup_sqlite.sh [path/to/swing_trader.db]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB="${1:-$ROOT/backend/data/swing_trader.db}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${BACKUP_DIR:-$ROOT/backend/data/backups}"
mkdir -p "$OUT_DIR"

if [ ! -f "$DB" ]; then
  echo "No database at $DB — nothing to back up."
  exit 1
fi

OUT="$OUT_DIR/swing_trader_${STAMP}.db"
# Prefer online backup API when sqlite3 CLI is available
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB" ".backup '$OUT'"
else
  cp -p "$DB" "$OUT"
  if [ -f "${DB}-wal" ]; then
    cp -p "${DB}-wal" "${OUT}-wal" 2>/dev/null || true
  fi
  if [ -f "${DB}-shm" ]; then
    cp -p "${DB}-shm" "${OUT}-shm" 2>/dev/null || true
  fi
fi

echo "Backup written: $OUT"
ls -lh "$OUT"
echo "Restore: stop the API, then cp '$OUT' '$DB' (and matching -wal/-shm if present)."
