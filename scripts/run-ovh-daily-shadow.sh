#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATE_VALUE="${SIGNAL75_SHADOW_DATE:-$(date +%F)}"
STATE_DIR="$BASE_DIR/data/deployment_state"
CURRENT_FILE="$STATE_DIR/current-shadow-candidate.txt"
STATUS_FILE="$STATE_DIR/daily-shadow-status.json"
LOCK_DIR="${SIGNAL75_OVH_DAILY_SHADOW_LOCK:-/tmp/signal75-ovh-daily-shadow.lock}"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "OVH daily shadow is already running; refusing a duplicate." >&2
  exit 75
fi
cleanup() { rmdir "$LOCK_DIR" 2>/dev/null || true; }
trap cleanup EXIT

mkdir -p "$STATE_DIR"

if python3 - "$STATUS_FILE" "$DATE_VALUE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected = sys.argv[2]
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(1)
if payload.get("date") == expected and payload.get("status") in {"match", "different"}:
    raise SystemExit(0)
raise SystemExit(1)
PY
then
  echo "OVH comparable shadow already completed for $DATE_VALUE; skipping retry."
  exit 0
fi

python3 - "$BASE_DIR/picks.json" "$DATE_VALUE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected = sys.argv[2]
if not path.is_file():
    raise SystemExit(f"Mac picks file is missing: {path}")
payload = json.loads(path.read_text(encoding="utf-8"))
if payload.get("date") != expected:
    raise SystemExit(
        f"Mac picks are not ready for {expected}; found {payload.get('date')!r}. "
        "The shadow run will not compare against stale picks."
    )
PY

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
status=failed
message="OVH shadow did not complete"

write_status() {
  python3 - "$STATUS_FILE" "$DATE_VALUE" "$started_at" "$status" "$message" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "date": sys.argv[2],
    "startedAt": sys.argv[3],
    "finishedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "status": sys.argv[4],
    "message": sys.argv[5],
    "livePublishing": "disabled",
    "macRemainsPrimary": True,
}
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
temporary.replace(path)
PY
}
trap 'write_status; cleanup' EXIT

"$BASE_DIR/scripts/ensure-ovh-shadow-candidate.sh"
candidate_id="$(tr -d '[:space:]' < "$CURRENT_FILE")"
if [[ ! "$candidate_id" =~ ^candidate-shadow-[0-9]{8}-[0-9]{6}$ ]]; then
  message="Invalid OVH candidate id: $candidate_id"
  exit 1
fi

SIGNAL75_OVH_CANDIDATE="$candidate_id" \
SIGNAL75_SHADOW_DATE="$DATE_VALUE" \
  "$BASE_DIR/scripts/run-ovh-real-feed-shadow.sh"

comparison="$STATE_DIR/real_feed_trials/mac-vs-ovh-current.json"
status="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$comparison")"
message="OVH real-feed shadow comparison completed: $status"
write_status
trap cleanup EXIT

echo "$message"
