#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/server.pid"

if [[ ! -f "$PID_FILE" ]]; then
    echo "No PID file found. Is the server running?"
    exit 1
fi

PID=$(cat "$PID_FILE")
if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    rm -f "$PID_FILE"
    echo "Server (PID $PID) stopped."
else
    echo "No process found with PID $PID. Removing stale PID file."
    rm -f "$PID_FILE"
    exit 1
fi
