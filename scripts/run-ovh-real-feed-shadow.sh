#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOST="${SIGNAL75_OVH_HOST:-signal75-vps}"
CANDIDATE_ID="${SIGNAL75_OVH_CANDIDATE:-candidate-20260831-verified}"
DATE_VALUE="${SIGNAL75_SHADOW_DATE:-$(date +%F)}"
STAMP="$(date -u +%H%M%S)"
SHADOW_ID="shadow-$DATE_VALUE-real-feed-$STAMP"
REMOTE_ROOT="/srv/signal75/shadow-runs/$SHADOW_ID"
LOCAL_TRIAL_DIR="$BASE_DIR/data/deployment_state/real_feed_trials"

SIGNAL75_SHADOW_DATE="$DATE_VALUE" \
  "$BASE_DIR/scripts/build-ovh-shadow-workspace.sh" "$CANDIDATE_ID" "$SHADOW_ID"
ssh "$REMOTE_HOST" "printf '%s\n' '$REMOTE_ROOT' > /srv/signal75/state/real-feed-shadow-current.txt"

ssh "$REMOTE_HOST" "python3 -c \"import json; from pathlib import Path; p=Path('$REMOTE_ROOT/data/api_cost_control.json'); d=json.loads(p.read_text()) if p.exists() else {}; d.update({'anthropic_enabled': False, 'max_anthropic_calls_per_day': 0}); p.write_text(json.dumps(d, indent=2)+'\\n')\""

{
  security find-generic-password -a signal75 -s betfair-username -w
  security find-generic-password -a signal75 -s betfair-password -w
  security find-generic-password -a signal75 -s betfair-app-key -w
} | ssh "$REMOTE_HOST" "set -eu
  IFS= read -r BETFAIR_USERNAME
  IFS= read -r BETFAIR_PASSWORD
  IFS= read -r BETFAIR_APP_KEY
  export BETFAIR_USERNAME BETFAIR_PASSWORD BETFAIR_APP_KEY
  export SIGNAL75_TEST_MODE=1
  export SIGNAL75_ENABLE_AI_EXPLANATIONS=0
  export SIGNAL75_ENABLE_ANTHROPIC_FALLBACK=0
  export SIGNAL75_DIRECT_CONSENSUS_LIMIT=6
  export SIGNAL75_DIRECT_CONSENSUS_MAX_WEB_USES=1
  export SIGNAL75_DIRECT_CONSENSUS_ONLY=1
  export SIGNAL75_RACE_CONSENSUS_LIMIT=0
  export SIGNAL75_DISABLE_RACE_CONSENSUS=1
  unset ANTHROPIC_API_KEY
  cd '$REMOTE_ROOT'
  test ! -e .env
  mkdir -p logs
  before_picks=\$(sha256sum picks.json | cut -d' ' -f1)
  before_performance=\$(sha256sum performance.json | cut -d' ' -f1)
  set +e
  /srv/signal75/venv/bin/python scripts/generate-picks-betfair.py > logs/real_feed_trial.log 2>&1
  generator_exit=\$?
  set -e
  unset BETFAIR_USERNAME BETFAIR_PASSWORD BETFAIR_APP_KEY
  /srv/signal75/venv/bin/python scripts/write-ovh-real-feed-report.py \
    --date '$DATE_VALUE' \
    --generator-exit \"\$generator_exit\" \
    --before-picks-sha \"\$before_picks\" \
    --before-performance-sha \"\$before_performance\"
"

mkdir -p "$LOCAL_TRIAL_DIR"
REMOTE_REPORT="$(ssh "$REMOTE_HOST" "find '$REMOTE_ROOT/data/deployment_state/real_feed_trials' -type f -name 'trial_*.json' | sort | tail -1")"
scp -q "$REMOTE_HOST:$REMOTE_REPORT" "$LOCAL_TRIAL_DIR/ovh-current-report.json"
scp -q "$REMOTE_HOST:$REMOTE_ROOT/data/picks_test.json" "$LOCAL_TRIAL_DIR/ovh-current-picks.json"
printf '%s\n' "$REMOTE_ROOT" > "$LOCAL_TRIAL_DIR/ovh-current-workspace.txt"
python3 "$BASE_DIR/scripts/compare-ovh-shadow-picks.py" \
  --mac-picks "$BASE_DIR/picks.json" \
  --ovh-picks "$LOCAL_TRIAL_DIR/ovh-current-picks.json" \
  --ovh-report "$LOCAL_TRIAL_DIR/ovh-current-report.json" \
  --output "$LOCAL_TRIAL_DIR/mac-vs-ovh-current.json"

echo "OVH real-feed shadow workspace: $REMOTE_ROOT"
