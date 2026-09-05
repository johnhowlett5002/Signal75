#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOST="${SIGNAL75_OVH_HOST:-signal75-vps}"
REMOTE_ROOT="${SIGNAL75_OVH_PRELIVE_ROOT:-/srv/signal75/prelive}"
CANDIDATE_ID="${1:-$(cat "$BASE_DIR/data/deployment_state/current-shadow-candidate.txt")}" 
STAMP="${2:-$(date -u +%Y%m%d-%H%M%S)}"
DATE_VALUE="${SIGNAL75_PRELIVE_DATE:-$(date +%F)}"
RELEASE_ID="prelive-$STAMP"
BUILD_ID="shadow-prelive-$STAMP"
BUILD_ROOT="/srv/signal75/shadow-runs/$BUILD_ID"
STAGE="$REMOTE_ROOT/releases/.$RELEASE_ID.stage"
RELEASE="$REMOTE_ROOT/releases/$RELEASE_ID"

case "$CANDIDATE_ID" in
  candidate-shadow-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]) ;;
  *) echo "Refusing unsafe candidate id: $CANDIDATE_ID" >&2; exit 2 ;;
esac

SIGNAL75_OVH_SHADOW_ROOT=/srv/signal75/shadow-runs \
  "$BASE_DIR/scripts/build-ovh-shadow-workspace.sh" "$CANDIDATE_ID" "$BUILD_ID"

ssh "$REMOTE_HOST" "set -eu
  test -f '/srv/signal75/candidates/$CANDIDATE_ID/candidate-manifest.json'
  test -d '$BUILD_ROOT'
  test ! -e '$RELEASE'
  install -d -m 0750 '$REMOTE_ROOT/releases' '$REMOTE_ROOT/state'
  rm -rf '$STAGE'
  install -d -m 0750 '$STAGE'
  cp -aL '$BUILD_ROOT/.' '$STAGE/'
  find '$STAGE' -type l -print -quit | grep -q . && {
    echo 'Pre-live release still contains symlinks after snapshot copy.' >&2
    exit 1
  } || true
  chmod u+rw \
    '$STAGE/data/horse_intelligence/form_history.sqlite' \
    '$STAGE/data/horse_intelligence/signal75_history.sqlite' \
    '$STAGE/data/combined_learning/signal75_learning.sqlite' \
    '$STAGE/data/horse_intelligence/head_to_head_master.jsonl' \
    '$STAGE/data/horse_intelligence/head_to_head_profiles.json' \
    '$STAGE/data/horse_intelligence/historic_rival_profiles.json' \
    '$STAGE/data/horse_intelligence/field_relationship_profiles.json'
  find '$STAGE/data' -type f \( -name '*.sqlite-wal' -o -name '*.sqlite-shm' \) -delete
  printf '%s\n' '$CANDIDATE_ID' > '$STAGE/OVH_PRELIVE_CANDIDATE'
  printf '%s\n' '$RELEASE_ID' > '$STAGE/OVH_PRELIVE_RELEASE'
"

# Overlay the current application code while preserving the copied writable data.
rsync -a --delete --exclude '__pycache__/' --exclude '.pytest_cache/' \
  "$BASE_DIR/scripts/" "$REMOTE_HOST:$STAGE/scripts/"
rsync -a --delete --exclude '__pycache__/' --exclude '.pytest_cache/' \
  "$BASE_DIR/tests/" "$REMOTE_HOST:$STAGE/tests/"
rsync -a "$BASE_DIR/deploy/" "$REMOTE_HOST:$STAGE/deploy/"
rsync -a "$BASE_DIR/docs/" "$REMOTE_HOST:$STAGE/docs/"
rsync -a "$BASE_DIR/assets/" "$REMOTE_HOST:$STAGE/assets/"

root_files=(
  app.js index.html about.html faq.html privacy.html responsible-gambling.html
  terms.html contact.html picks.json performance.json pytest.ini requirements.txt
)
for filename in "${root_files[@]}"; do
  if [ -f "$BASE_DIR/$filename" ]; then
    rsync -a "$BASE_DIR/$filename" "$REMOTE_HOST:$STAGE/$filename"
  fi
done

ssh "$REMOTE_HOST" "set -eu
  cd '$STAGE'
  /srv/signal75/venv/bin/python scripts/publish_dashboard_data.py --date '$DATE_VALUE'
  /srv/signal75/venv/bin/python -m pytest -q
  for stage in morning results learning; do
    /srv/signal75/venv/bin/python scripts/run-ovh-live-stage.py \"\$stage\" --dry-run
  done
  mv '$STAGE' '$RELEASE'
  previous=none
  if [ -L '$REMOTE_ROOT/current' ]; then previous=\$(readlink '$REMOTE_ROOT/current'); fi
  printf '%s\n' \"\$previous\" > '$REMOTE_ROOT/state/previous-release.txt'
  ln -sfn 'releases/$RELEASE_ID' '$REMOTE_ROOT/.current.new'
  mv -Tf '$REMOTE_ROOT/.current.new' '$REMOTE_ROOT/current'
  printf '%s\n' '$RELEASE_ID' > '$REMOTE_ROOT/state/current-release.txt'
  rm -rf '$BUILD_ROOT'
"

ssh "$REMOTE_HOST" "/srv/signal75/venv/bin/python '$REMOTE_ROOT/current/scripts/check-ovh-cutover-readiness.py' --root '$REMOTE_ROOT/current' --output '$REMOTE_ROOT/state/readiness-latest.json'"
echo "OVH pre-live release staged without activation: $RELEASE"
