@echo off
cd /d "%~dp0"
py -m pip install -r backend\requirements.txt
start "CLIPAI API" cmd /k py -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
start "CLIPAI Web" cmd /k py -m http.server 8080 --directory frontend
timeout /t 3
start http://127.0.0.1:8080
