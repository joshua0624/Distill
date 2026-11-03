#!/usr/bin/env bash
# Set up (or update) Distill as an always-on service on this Mac. Safe to re-run:
# after a `git pull`, run it again to rebuild and restart. See docs/deploy.md.
#
#   ./scripts/setup-mac-mini.sh
#
# It installs uv and Node (official builds, into ~/.local) if they're missing, builds the app, and installs a
# LaunchAgent that runs `distill serve --schedule` at login and restarts it if it stops.
# It changes no system settings: the sleep and login settings it reminds you about are yours.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="net.distill.serve"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGS="$HOME/Library/Logs/Distill"
PORT="${PORT:-8000}"
NODE_DIR="$HOME/.local/node"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m! %s\033[0m\n' "$*"; }

[[ "$(uname)" == "Darwin" ]] || { echo "This script is for macOS."; exit 1; }
cd "$REPO"

say "1/5 Tools"
# Official prebuilt downloads into ~/.local, not Homebrew: Homebrew no longer builds packages
# for Intel Macs, so it would compile Node from source.
export PATH="$HOME/.local/bin:$NODE_DIR/bin:$PATH"
if ! command -v uv >/dev/null; then
  echo "Installing uv from astral.sh"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
fi
UV="$(command -v uv)"
if ! command -v node >/dev/null; then
  arch="$(uname -m)"; [[ "$arch" == x86_64 ]] && arch=x64
  # Newest LTS release that still ships a build for this Mac.
  version="$(curl -fsSL https://nodejs.org/dist/index.json | "$UV" run --no-project python -I -c "
import json, sys
print(next(r['version'] for r in json.load(sys.stdin) if r['lts'] and 'osx-$arch-tar' in r['files']))")"
  echo "Installing Node $version from nodejs.org"
  rm -rf "$NODE_DIR" && mkdir -p "$NODE_DIR"
  curl -fsSL "https://nodejs.org/dist/$version/node-$version-darwin-$arch.tar.gz" | tar -xz -C "$NODE_DIR" --strip-components 1
fi
echo "uv $("$UV" --version | cut -d' ' -f2), node $(node --version)"

say "2/5 Build"
"$UV" sync --no-dev
(cd frontend && npm ci --no-audit --no-fund && npm run build)

say "3/5 Data"
missing=0
if [[ ! -f .env ]]; then
  warn "No .env here. Copy it from your other Mac (it holds YOUTUBE_API_KEY and ANTHROPIC_API_KEY)."
  missing=1
fi
if [[ ! -f data/distill.db ]]; then
  warn "No data/distill.db. On your other Mac run 'uv run distill backup ~/Desktop/distill-transfer',"
  warn "then copy that file here as $REPO/data/distill.db."
  missing=1
fi
if [[ $missing == 1 ]]; then
  echo "Add the files above, then run this script again."
  exit 1
fi
echo "Found .env and data/distill.db."

say "4/5 Service"
mkdir -p "$LOGS" "$(dirname "$PLIST")"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$UV</string><string>run</string><string>--no-dev</string>
    <string>distill</string><string>serve</string><string>--schedule</string>
    <string>--port</string><string>$PORT</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$(dirname "$UV"):/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$LOGS/serve.log</string>
  <key>StandardErrorPath</key><string>$LOGS/serve.log</string>
</dict>
</plist>
EOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
for _ in $(seq 1 30); do
  curl -fsS "http://127.0.0.1:$PORT/api/triage/stats" >/dev/null 2>&1 && break
  sleep 1
done
if curl -fsS "http://127.0.0.1:$PORT/api/triage/stats" >/dev/null 2>&1; then
  echo "Distill is running at http://127.0.0.1:$PORT (logs: $LOGS/serve.log)."
else
  warn "Distill didn't answer on port $PORT. Check $LOGS/serve.log."
  exit 1
fi

say "5/5 Tailscale"
TS="$(command -v tailscale || true)"
[[ -z "$TS" && -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ]] && TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
if [[ -z "$TS" ]]; then
  warn "Tailscale isn't installed. Install the Tailscale app (tailscale.com/download), sign in,"
  warn "then re-run this script to publish Distill on your tailnet."
elif ! "$TS" status >/dev/null 2>&1; then
  warn "Tailscale is installed but not signed in. Open the Tailscale app, sign in, then re-run this."
else
  # HTTPS on your tailnet only: nothing is exposed to the internet.
  "$TS" serve --bg "$PORT"
  "$TS" serve status
fi

say "Remaining one-time settings (yours to change, in System Settings)"
cat <<'EOF'
  - Energy: turn on "Prevent automatic sleeping when the display is off" and
    "Start up automatically after a power failure".
  - Users & Groups: turn on automatic login for this user, so Distill starts after a reboot
    without anyone signing in (the service runs as this user).
  - On your iPhone: install Tailscale and sign in with the same account, open the
    https://...ts.net address above in Safari, then Share > Add to Home Screen.
EOF
