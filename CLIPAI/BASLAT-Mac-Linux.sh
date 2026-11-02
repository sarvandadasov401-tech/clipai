#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m pip install -r backend/requirements.txt
python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 & API_PID=$!
python3 -m http.server 8080 --directory frontend & WEB_PID=$!
trap 'kill $API_PID $WEB_PID 2>/dev/null || true' EXIT
sleep 2
python3 -c "import webbrowser; webbrowser.open('http://127.0.0.1:8080')" || true
wait
