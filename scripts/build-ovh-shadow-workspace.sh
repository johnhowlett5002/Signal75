#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOST="${SIGNAL75_OVH_HOST:-signal75-vps}"
REMOTE_APP="${SIGNAL75_OVH_ROOT:-/srv/signal75/app}"
REMOTE_SHADOW_ROOT="${SIGNAL75_OVH_SHADOW_ROOT:-/srv/signal75/shadow-runs}"
DATE_VALUE="${SIGNAL75_SHADOW_DATE:-$(date +%F)}"
CANDIDATE_ID="${1:?usage: build-ovh-shadow-workspace.sh CANDIDATE_ID [SHADOW_ID]}"
SHADOW_ID="${2:-shadow-$DATE_VALUE-$(date -u +%H%M%S)}"
CANDIDATE="/srv/signal75/candidates/$CANDIDATE_ID"
STAGE="$REMOTE_SHADOW_ROOT/.$SHADOW_ID.stage"
RELEASE="$REMOTE_SHADOW_ROOT/$SHADOW_ID"
LOCK_DIR="${SIGNAL75_OVH_SHADOW_LOCK:-/tmp/signal75-ovh-shadow-build.lock}"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "OVH shadow workspace build is already running; skipping duplicate."
  exit 0
fi
cleanup() { rmdir "$LOCK_DIR" 2>/dev/null || true; }
trap cleanup EXIT

ssh "$REMOTE_HOST" "set -eu
  test -f '$CANDIDATE/candidate-manifest.json'
  test ! -e '$RELEASE'
  install -d -m 0750 '$STAGE'
  rsync -a --exclude '.git/' --exclude '.env*' --exclude '*.sqlite' --exclude '*.sqlite-*' \
    --exclude '__pycache__/' --exclude '.pytest_cache/' --exclude 'test-output/' \
    '$REMOTE_APP/' '$STAGE/'
  sudo rsync -a /var/www/signal75-preview-current/ '$STAGE/dashboard/'
  sudo chown -R debian:debian '$STAGE/dashboard'
"

# Use the Mac's complete current script set inside the isolated workspace so
# imported helpers match the primary machine. This never updates the OVH app.
rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  "$BASE_DIR/scripts/" "$REMOTE_HOST:$STAGE/scripts/"

runtime_files=(
  "picks.json"
  "performance.json"
  "data/today_runners.json"
  "data/roi_tables.json"
  "data/consensus_overlay_$DATE_VALUE.json"
  "data/script_tipster_overlay_$DATE_VALUE.json"
  "data/tipster_intelligence/tipster_intelligence_$DATE_VALUE.json"
  "data/tipster_intelligence/tipster_intelligence_$DATE_VALUE.csv"
  "data/bookmaker_price_overrides.json"
  "data/settlement_price_audit.json"
  "data/$DATE_VALUE.json"
  "data/race_comparison_$DATE_VALUE.json"
  "data/field_relative_daily_$DATE_VALUE.json"
  "data/field_relative_archive_$DATE_VALUE.json"
  "data/pipeline_health_$DATE_VALUE.json"
  "data/integrity_check_$DATE_VALUE.json"
  "data/challenger_lab/challenger_$DATE_VALUE.json"
  "data/horse_intelligence/field_graph_$DATE_VALUE.json"
)
existing_files=()
for relative in "${runtime_files[@]}"; do
  if [ -f "$BASE_DIR/$relative" ]; then
    existing_files+=("./$relative")
  fi
done
while IFS= read -r result_file; do
  existing_files+=("./${result_file#$BASE_DIR/}")
done < <(find "$BASE_DIR/data" -maxdepth 1 -type f -name '????-??-??.json' -print | sort)

if [ ${#existing_files[@]} -gt 0 ]; then
  (
    cd "$BASE_DIR"
    rsync -aR "${existing_files[@]}" "$REMOTE_HOST:$STAGE/"
  )
fi

ssh "$REMOTE_HOST" "set -eu
  install -d -m 0750 '$STAGE/data/horse_intelligence' '$STAGE/data/combined_learning'
  ln -sfn '$CANDIDATE/data/horse_intelligence/form_history.sqlite' \
    '$STAGE/data/horse_intelligence/form_history.sqlite'
  ln -sfn '$CANDIDATE/data/horse_intelligence/signal75_history.sqlite' \
    '$STAGE/data/horse_intelligence/signal75_history.sqlite'
  ln -sfn '$CANDIDATE/data/combined_learning/signal75_learning.sqlite' \
    '$STAGE/data/combined_learning/signal75_learning.sqlite'
  for filename in head_to_head_master.jsonl head_to_head_profiles.json historic_rival_profiles.json field_relationship_profiles.json historic_rival_master.jsonl race_result_notes_master.jsonl race_result_note_profiles.json result_notes_seed.json; do
    source='$CANDIDATE/data/horse_intelligence/'\"\$filename\"
    test -L \"\$source\"
    ln -sfn \"\$(readlink \"\$source\")\" '$STAGE/data/horse_intelligence/'\"\$filename\"
  done
  install -d -m 0750 '$STAGE/engine'
  source='$CANDIDATE/engine/betfair_uk_races_full_v2.csv'
  test -L \"\$source\"
  ln -sfn \"\$(readlink \"\$source\")\" '$STAGE/engine/betfair_uk_races_full_v2.csv'
  printf '%s\n' '$CANDIDATE_ID' > '$STAGE/OVH_SHADOW_CANDIDATE'
  printf '%s\n' '$DATE_VALUE' > '$STAGE/OVH_SHADOW_DATE'
  /srv/signal75/venv/bin/python '$STAGE/scripts/publish_dashboard_data.py' --date '$DATE_VALUE'
  mv '$STAGE' '$RELEASE'
"

echo "OVH isolated shadow workspace built without activation: $RELEASE"
