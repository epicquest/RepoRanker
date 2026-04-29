#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/server.log"
PID_FILE="$SCRIPT_DIR/server.pid"

if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Server is already running (PID $PID). Use kill-server.sh to stop it."
        exit 1
    else
        rm -f "$PID_FILE"
    fi
fi

cd "$SCRIPT_DIR"
nohup .venv/bin/python manage.py runserver localhost:5000 >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "Server started (PID $(cat "$PID_FILE")). Logging to $LOG_FILE"
