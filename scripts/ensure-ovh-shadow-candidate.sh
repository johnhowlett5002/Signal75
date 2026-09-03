#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATE_VALUE="${SIGNAL75_SHADOW_DATE:-$(date +%F)}"
DATE_STAMP="${DATE_VALUE//-/}"
STATE_DIR="$BASE_DIR/data/deployment_state"
CURRENT_FILE="$STATE_DIR/current-shadow-candidate.txt"
REMOTE_HOST="${SIGNAL75_OVH_HOST:-signal75-vps}"

candidate_id=""
if [ -f "$CURRENT_FILE" ]; then
  candidate_id="$(tr -d '[:space:]' < "$CURRENT_FILE")"
fi

if [ "${SIGNAL75_FORCE_NEW_SHADOW_CANDIDATE:-0}" != "1" ] \
  && [[ "$candidate_id" =~ ^candidate-shadow-${DATE_STAMP}-[0-9]{6}$ ]] \
  && ssh "$REMOTE_HOST" "test -r '/srv/signal75/candidates/$candidate_id/candidate-manifest.json'"; then
  echo "Reusing verified OVH shadow candidate: $candidate_id"
  exit 0
fi

"$BASE_DIR/scripts/prepare-ovh-shadow-candidate.sh"
