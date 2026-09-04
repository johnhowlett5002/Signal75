#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOST="${SIGNAL75_OVH_HOST:-signal75-vps}"
REMOTE_STATE="${SIGNAL75_OVH_STATE:-/srv/signal75/state}"
REMOTE_RELEASES="${SIGNAL75_OVH_PUBLIC_RELEASES:-/var/www/signal75-public-preview-releases}"
REMOTE_CURRENT="${SIGNAL75_OVH_PUBLIC_CURRENT:-/var/www/signal75-public-preview-current}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
REMOTE_STAGE="$REMOTE_STATE/public-preview-upload-$STAMP-$$"
REMOTE_RELEASE="$REMOTE_RELEASES/$STAMP"
LOCK_DIR="${SIGNAL75_OVH_PUBLIC_LOCK:-/tmp/signal75-ovh-public-preview-sync.lock}"
LOCAL_STAGE="$(mktemp -d "${TMPDIR:-/tmp}/signal75-public-preview.XXXXXX")"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "OVH public-site preview refresh is already running; skipping duplicate."
  exit 0
fi
cleanup() {
  rm -rf "$LOCAL_STAGE"
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

for required in index.html app.js picks.json performance.json deploy/nginx/signal75-public-preview.conf; do
  if [ ! -f "$BASE_DIR/$required" ]; then
    echo "Missing public preview input: $required" >&2
    exit 1
  fi
done

rsync -a --prune-empty-dirs \
  --include='/*.html' \
  --include='/app.js' \
  --include='/sw.js' \
  --include='/assets/***' \
  --include='/picks.json' \
  --include='/performance.json' \
  --include='/data/' \
  --include='/data/site_version.json' \
  --include='/data/today_runners.json' \
  --include='/data/race_comparison_*.json' \
  --include='/data/public_scorecards/***' \
  --include='/dashboard/' \
  --include='/dashboard/data/***' \
  --exclude='*' \
  "$BASE_DIR/" "$LOCAL_STAGE/"

ssh "$REMOTE_HOST" "install -d -m 0750 '$REMOTE_STAGE'"
rsync -a --exclude '.DS_Store' "$LOCAL_STAGE/" "$REMOTE_HOST:$REMOTE_STAGE/"
scp "$BASE_DIR/deploy/nginx/signal75-public-preview.conf" "$REMOTE_HOST:$REMOTE_STATE/signal75-public-preview.conf"

ssh "$REMOTE_HOST" "set -eu
  sudo install -d -o root -g www-data -m 0750 '$REMOTE_RELEASES'
  sudo mv '$REMOTE_STAGE' '$REMOTE_RELEASE'
  sudo chown -R root:www-data '$REMOTE_RELEASE'
  sudo find '$REMOTE_RELEASE' -type d -exec chmod 0750 {} +
  sudo find '$REMOTE_RELEASE' -type f -exec chmod 0640 {} +
  sudo ln -s '$REMOTE_RELEASE' '$REMOTE_CURRENT.$STAMP'
  sudo mv -Tf '$REMOTE_CURRENT.$STAMP' '$REMOTE_CURRENT'
  sudo install -o root -g root -m 0644 '$REMOTE_STATE/signal75-public-preview.conf' /etc/nginx/sites-available/signal75-public-preview
  sudo ln -sfn /etc/nginx/sites-available/signal75-public-preview /etc/nginx/sites-enabled/signal75-public-preview
  sudo nginx -t
  sudo systemctl reload nginx
  printf '%s\n' '$REMOTE_RELEASE' > '$REMOTE_STATE/public-preview-current.txt'
"

echo "OVH private public-site preview refreshed: $REMOTE_RELEASE"
