#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$BASE_DIR/data/deployment_state"
HISTORY_DIR="$STATE_DIR/history"
COMPARISON_DIR="$STATE_DIR/comparisons"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
REMOTE_HOST="${SIGNAL75_OVH_HOST:-signal75-vps}"
REMOTE_ROOT="${SIGNAL75_OVH_ROOT:-/srv/signal75/app}"
REMOTE_STATE="${SIGNAL75_OVH_STATE:-/srv/signal75/state}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOCK_DIR="${SIGNAL75_OVH_AUDIT_LOCK:-/tmp/signal75-ovh-state-audit.lock}"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "OVH deployment-state comparison is already running; skipping duplicate."
  exit 0
fi
cleanup() { rmdir "$LOCK_DIR" 2>/dev/null || true; }
trap cleanup EXIT

mkdir -p "$HISTORY_DIR" "$COMPARISON_DIR"

"$PYTHON_BIN" "$BASE_DIR/scripts/deployment-state.py" capture \
  --root "$BASE_DIR" \
  --role mac-primary \
  --output "$STATE_DIR/mac-current.json" \
  --history-dir "$HISTORY_DIR"

ssh "$REMOTE_HOST" "install -d -m 0750 '$REMOTE_STATE/history'"
ssh "$REMOTE_HOST" \
  "'$REMOTE_ROOT/../venv/bin/python' '$REMOTE_ROOT/scripts/deployment-state.py' capture \
    --root '$REMOTE_ROOT' \
    --role ovh-read-only-test \
    --output '$REMOTE_STATE/ovh-current.json' \
    --history-dir '$REMOTE_STATE/history'"

scp -q "$REMOTE_HOST:$REMOTE_STATE/ovh-current.json" "$STATE_DIR/ovh-current.json"

"$PYTHON_BIN" "$BASE_DIR/scripts/deployment-state.py" compare \
  "$STATE_DIR/mac-current.json" \
  "$STATE_DIR/ovh-current.json" \
  --output "$COMPARISON_DIR/$STAMP.json" \
  | tee "$COMPARISON_DIR/$STAMP.txt"

echo "Comparison saved: $COMPARISON_DIR/$STAMP.json"
