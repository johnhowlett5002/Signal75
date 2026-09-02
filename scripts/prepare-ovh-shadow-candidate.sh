#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="${1:-$(date -u +%Y%m%d-%H%M%S)}"
SNAPSHOT_ID="shadow-input-$STAMP"
RUNTIME_SNAPSHOT_ID="runtime-input-$STAMP"
CANDIDATE_ID="candidate-shadow-$STAMP"
STATE_DIR="$BASE_DIR/data/deployment_state"
CURRENT_FILE="$STATE_DIR/current-shadow-candidate.txt"
LOCK_DIR="${SIGNAL75_OVH_CANDIDATE_LOCK:-/tmp/signal75-ovh-candidate.lock}"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "OVH candidate preparation is already running; refusing a duplicate." >&2
  exit 75
fi
cleanup() { rmdir "$LOCK_DIR" 2>/dev/null || true; }
trap cleanup EXIT

mkdir -p "$STATE_DIR"

python3 "$BASE_DIR/scripts/sync-ovh-sqlite-snapshots.py" \
  --snapshot-id "$SNAPSHOT_ID" \
  --database combined_learning \
  --database form_history \
  --database signal75_history

python3 "$BASE_DIR/scripts/sync-ovh-runtime-snapshot.py" \
  --snapshot-id "$RUNTIME_SNAPSHOT_ID"

python3 "$BASE_DIR/scripts/build-ovh-database-candidate.py" \
  --combined-learning "$SNAPSHOT_ID" \
  --form-history "$SNAPSHOT_ID" \
  --signal75-history "$SNAPSHOT_ID" \
  --runtime-snapshot "$RUNTIME_SNAPSHOT_ID" \
  --candidate-id "$CANDIDATE_ID"

temporary="$CURRENT_FILE.tmp"
printf '%s\n' "$CANDIDATE_ID" > "$temporary"
mv "$temporary" "$CURRENT_FILE"

if ! python3 "$BASE_DIR/scripts/prune-ovh-shadow-artifacts.py"; then
  echo "Warning: OVH shadow retention cleanup failed; candidate remains valid." >&2
fi

echo "OVH shadow candidate ready: $CANDIDATE_ID"
