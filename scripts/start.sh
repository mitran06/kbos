#!/usr/bin/env bash
# Start KBOS for the demo: backend (voice + REST + /ws) serving the dashboard at /admin.
#   scripts/start.sh            # run in the foreground (Ctrl-C stops it)
#   scripts/start.sh --reset    # also reset the demo data once the server is up
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT=7860

if [[ ! -f "$ROOT/dashboard/dist/index.html" ]]; then
  echo "building dashboard…"
  (cd "$ROOT/dashboard" && pnpm install --frozen-lockfile && pnpm build)
fi

# free the port if an old server is still around
fuser -k ${PORT}/tcp >/dev/null 2>&1 || true

echo
echo "KBOS server: http://0.0.0.0:${PORT}   dashboard: http://localhost:${PORT}/admin"
echo "Phone server URL (long-press KBOS on the people grid → Settings), one of:"
ip -4 -o addr show | awk '!/ lo |docker|br-|CloudflareWARP/ {split($4,a,"/"); printf "   http://%s:%d   (%s)\n", a[1], '"$PORT"', $2}'
if command -v adb >/dev/null && adb get-state >/dev/null 2>&1; then
  adb reverse tcp:${PORT} tcp:${PORT} >/dev/null && echo "   http://localhost:${PORT}   (USB phone, adb reverse set)"
fi
echo

if [[ " $* " == *" --reset "* ]]; then
  ( for i in $(seq 1 60); do curl -s -o /dev/null localhost:${PORT}/api/health && break; sleep 0.5; done
    curl -s -X POST localhost:${PORT}/api/demo/reset >/dev/null && echo "demo reset ✓" ) &
fi

cd "$ROOT/backend"
exec uv run python -m kbos
