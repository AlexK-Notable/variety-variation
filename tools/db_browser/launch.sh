#!/bin/bash
# Launch the Variety Database Browser

cd "$(dirname "$0")/../.."

# Start the server in the background
.venv/bin/python -m tools.db_browser.main &
SERVER_PID=$!

# Wait for server to be ready
for i in {1..30}; do
    if curl -s http://127.0.0.1:8765/health > /dev/null 2>&1; then
        break
    fi
    sleep 0.2
done

# Open browser
xdg-open http://127.0.0.1:8765/browse 2>/dev/null || firefox http://127.0.0.1:8765/browse 2>/dev/null &

# Wait for server process
wait $SERVER_PID
