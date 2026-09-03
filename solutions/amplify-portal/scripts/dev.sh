#!/usr/bin/env bash
# Start both Amplify sandbox (backend) and Vite dev server (frontend) together.
# Usage: ./scripts/dev.sh
# Stop: Ctrl+C (kills both processes)

set -e
cd "$(dirname "$0")/.."

echo "🚀 Starting Amplify Sandbox + Vite Dev Server..."
echo "   Backend: ./scripts/sandbox.sh (targets the sandbox amplify_outputs.json names)"
echo "   Frontend: http://localhost:5173"
echo ""
echo "   Press Ctrl+C to stop both."
echo ""

# Trap Ctrl+C to kill child processes
cleanup() {
  echo ""
  echo "🛑 Stopping..."
  jobs -p | xargs -r kill 2>/dev/null
  wait 2>/dev/null
  echo "✔ Stopped."
}
trap cleanup EXIT INT TERM

# Storage Browser's download path needs its service worker served from this
# origin; without it downloads fall back to an in-memory blob that a phone gives
# the user no way to find. Copied from the installed package, not committed.
npm run copy-sw >/dev/null

# Start Vite dev server in background (always starts immediately)
npx vite --host &
VITE_PID=$!
echo "✔ Vite dev server started (PID: $VITE_PID)"

# Start sandbox in foreground (blocks until Ctrl+C)
# This keeps the script alive and shows sandbox output in terminal.
# Goes through the wrapper so the sandbox identifier is named explicitly rather
# than defaulting to one derived from the OS user -- see scripts/sandbox.sh.
./scripts/sandbox.sh
