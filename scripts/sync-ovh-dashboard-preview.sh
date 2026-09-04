#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DASHBOARD_DIR="$BASE_DIR/dashboard"
REMOTE_HOST="${SIGNAL75_OVH_HOST:-signal75-vps}"
REMOTE_STATE="${SIGNAL75_OVH_STATE:-/srv/signal75/state}"
REMOTE_RELEASES="${SIGNAL75_OVH_PREVIEW_RELEASES:-/var/www/signal75-preview-releases}"
REMOTE_CURRENT="${SIGNAL75_OVH_PREVIEW_CURRENT:-/var/www/signal75-preview-current}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
REMOTE_STAGE="$REMOTE_STATE/preview-upload-$STAMP-$$"
REMOTE_RELEASE="$REMOTE_RELEASES/$STAMP"
LOCK_DIR="${SIGNAL75_OVH_PREVIEW_LOCK:-/tmp/signal75-ovh-preview-sync.lock}"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "OVH dashboard preview refresh is already running; skipping duplicate."
  exit 0
fi
cleanup() { rmdir "$LOCK_DIR" 2>/dev/null || true; }
trap cleanup EXIT

for required in index.html dashboard.js dashboard.css data/dashboard_ready.json; do
  if [ ! -f "$DASHBOARD_DIR/$required" ]; then
    echo "Missing dashboard preview input: dashboard/$required" >&2
    exit 1
  fi
done

ssh "$REMOTE_HOST" "install -d -m 0750 '$REMOTE_STAGE'"
rsync -a --exclude '.DS_Store' "$DASHBOARD_DIR/" "$REMOTE_HOST:$REMOTE_STAGE/"

ssh "$REMOTE_HOST" "set -eu
  sudo install -d -o root -g www-data -m 0750 '$REMOTE_RELEASES'
  sudo mv '$REMOTE_STAGE' '$REMOTE_RELEASE'
  sudo chown -R root:www-data '$REMOTE_RELEASE'
  sudo find '$REMOTE_RELEASE' -type d -exec chmod 0750 {} +
  sudo find '$REMOTE_RELEASE' -type f -exec chmod 0640 {} +
  sudo ln -s '$REMOTE_RELEASE' '$REMOTE_CURRENT.$STAMP'
  sudo mv -Tf '$REMOTE_CURRENT.$STAMP' '$REMOTE_CURRENT'
  printf '%s\n' '$REMOTE_RELEASE' > '$REMOTE_STATE/preview-current.txt'
"

echo "OVH private dashboard preview refreshed: $REMOTE_RELEASE"
