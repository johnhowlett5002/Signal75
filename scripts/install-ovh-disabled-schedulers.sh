#!/bin/bash
set -euo pipefail

BASE_DIR=$(cd "$(dirname "$0")/.." && pwd)
UNIT_DIR="$BASE_DIR/deploy/systemd"
SYSTEMD_DIR=/etc/systemd/system

if [ -e /etc/signal75/live-pipeline-enabled ] || [ -e /etc/signal75/production.env ]; then
  echo "Refusing disabled-scheduler installation: a production activation file already exists." >&2
  exit 1
fi

units=(
  signal75-live@.service
  signal75-live-failure@.service
  signal75-morning.timer
  signal75-results.timer
  signal75-learning.timer
  ovh-readonly-health.service
  ovh-readonly-health.timer
)

systemd-analyze verify "${units[@]/#/$UNIT_DIR/}"
sudo install -d -m 0750 -o debian -g debian \
  /srv/signal75/state/health \
  /srv/signal75/state/scheduler-failures
for unit in "${units[@]}"; do
  sudo install -m 0644 "$UNIT_DIR/$unit" "$SYSTEMD_DIR/$unit"
done
sudo systemctl daemon-reload
sudo systemctl enable --now ovh-readonly-health.timer

for timer in signal75-morning.timer signal75-results.timer signal75-learning.timer; do
  if [ "$(systemctl is-enabled "$timer" 2>/dev/null || true)" != disabled ]; then
    echo "Production timer unexpectedly enabled: $timer" >&2
    exit 1
  fi
  if [ "$(systemctl is-active "$timer" 2>/dev/null || true)" != inactive ]; then
    echo "Production timer unexpectedly active: $timer" >&2
    exit 1
  fi
done

echo "OVH scheduler definitions installed; production timers remain disabled and inactive."
