#!/usr/bin/env bash
# Start both Amplify sandbox (backend) and Vite dev server (frontend) together.
# Usage: ./scripts/dev.sh
# Stop: Ctrl+C (kills both processes)

set -e
cd "$(dirname "$0")/.."

echo "🚀 Starting Amplify Sandbox + Vite Dev Server..."
echo "   Backend: npx ampx sandbox"
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

# Start Vite dev server in background (always starts immediately)
npx vite --host &
VITE_PID=$!
echo "✔ Vite dev server started (PID: $VITE_PID)"

# Start sandbox in foreground (blocks until Ctrl+C)
# This keeps the script alive and shows sandbox output in terminal
npx ampx sandbox
