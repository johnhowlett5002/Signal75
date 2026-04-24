#!/bin/bash
# Signal 75 — Mac Scheduler Setup
# Run this ONCE to set up automatic 10am picks and 7pm results
# Usage: bash setup-scheduler.sh YOUR-ANTHROPIC-API-KEY

set -e

ANTHROPIC_KEY="$1"

if [ -z "$ANTHROPIC_KEY" ]; then
  echo "❌ Usage: bash setup-scheduler.sh YOUR-ANTHROPIC-API-KEY"
  echo "   Get your key from: platform.claude.com/settings/keys"
  exit 1
fi

echo "🏇 Signal 75 — Mac Scheduler Setup"
echo "==================================="

# ── CHECK REPO EXISTS ────────────────────────────────────────────
if [ ! -d ~/Signal75 ]; then
  echo "📥 Cloning Signal75 repo..."
  git clone https://github.com/johnhowlett5002/Signal75.git ~/Signal75
  echo "✅ Repo cloned"
else
  echo "✅ Repo exists at ~/Signal75"
fi

# ── INSTALL PYTHON DEPS ──────────────────────────────────────────
echo "📦 Installing Python packages..."
pip3 install anthropic --break-system-packages --quiet 2>/dev/null || \
pip3 install anthropic --quiet 2>/dev/null || \
pip install anthropic --quiet 2>/dev/null
echo "✅ anthropic installed"

# ── STORE API KEY IN MAC KEYCHAIN (secure — not in any file) ────
echo "🔐 Storing API key in Mac Keychain..."
security delete-generic-password -a "signal75" -s "anthropic-api-key" 2>/dev/null || true
security add-generic-password -a "signal75" -s "anthropic-api-key" -w "$ANTHROPIC_KEY"
echo "✅ API key stored in Keychain (secure)"

# ── CREATE WRAPPER SCRIPTS ───────────────────────────────────────
# These read the key from Keychain at runtime — never stored in files

cat > ~/signal75-run-picks.sh << 'WRAPPER'
#!/bin/bash
# Signal 75 — Morning picks runner
# Reads API key from Mac Keychain at runtime
KEY=$(security find-generic-password -a "signal75" -s "anthropic-api-key" -w 2>/dev/null)
if [ -z "$KEY" ]; then
  echo "❌ API key not found in Keychain" >> ~/signal75-picks.log
  exit 1
fi
cd ~/Signal75
git pull --rebase --quiet 2>/dev/null || true
ANTHROPIC_API_KEY="$KEY" /usr/bin/python3 ~/Signal75/scripts/generate-picks-mac.py
WRAPPER
chmod +x ~/signal75-run-picks.sh

cat > ~/signal75-run-results.sh << 'WRAPPER'
#!/bin/bash
# Signal 75 — Evening results runner
# Reads API key from Mac Keychain at runtime
KEY=$(security find-generic-password -a "signal75" -s "anthropic-api-key" -w 2>/dev/null)
if [ -z "$KEY" ]; then
  echo "❌ API key not found in Keychain" >> ~/signal75-results.log
  exit 1
fi
cd ~/Signal75
git pull --rebase --quiet 2>/dev/null || true
ANTHROPIC_API_KEY="$KEY" /usr/bin/python3 ~/Signal75/scripts/update-results-mac.py
WRAPPER
chmod +x ~/signal75-run-results.sh

echo "✅ Wrapper scripts created"

# ── CREATE LAUNCHD PLIST — MORNING 10AM ─────────────────────────
MORNING_PLIST=~/Library/LaunchAgents/co.signal75.morning.plist
cat > "$MORNING_PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>co.signal75.morning</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/$(whoami)/signal75-run-picks.sh</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>10</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>/Users/$(whoami)/signal75-picks.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/$(whoami)/signal75-picks-error.log</string>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
PLIST

# ── CREATE LAUNCHD PLIST — EVENING 7PM ──────────────────────────
EVENING_PLIST=~/Library/LaunchAgents/co.signal75.evening.plist
cat > "$EVENING_PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>co.signal75.evening</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/$(whoami)/signal75-run-results.sh</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>19</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>/Users/$(whoami)/signal75-results.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/$(whoami)/signal75-results-error.log</string>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
PLIST

echo "✅ Scheduler plists created"

# ── LOAD SCHEDULERS ──────────────────────────────────────────────
launchctl unload "$MORNING_PLIST" 2>/dev/null || true
launchctl load "$MORNING_PLIST"
echo "✅ Morning scheduler loaded (10:00am daily)"

launchctl unload "$EVENING_PLIST" 2>/dev/null || true
launchctl load "$EVENING_PLIST"
echo "✅ Evening scheduler loaded (7:00pm daily)"

# ── VERIFY ───────────────────────────────────────────────────────
echo ""
echo "🎉 Setup complete!"
echo ""
echo "Scheduled jobs:"
launchctl list | grep signal75
echo ""
echo "To test picks RIGHT NOW:"
echo "  bash ~/signal75-run-picks.sh"
echo ""
echo "To test results RIGHT NOW:"
echo "  bash ~/signal75-run-results.sh"
echo ""
echo "To check logs:"
echo "  tail -f ~/signal75-picks.log"
echo "  tail -f ~/signal75-results.log"
echo ""
echo "To remove scheduler:"
echo "  launchctl unload ~/Library/LaunchAgents/co.signal75.morning.plist"
echo "  launchctl unload ~/Library/LaunchAgents/co.signal75.evening.plist"
