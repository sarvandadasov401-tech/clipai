# CLIPAI — local video clipping studio

Functional local-first starter: responsive frontend, FastAPI backend, SQLite persistence, file uploads and real FFmpeg MP4 rendering. Rendered clips are genuine source segments, evenly sampled across the video. This build does **not** claim AI semantic moment detection, ASR/subtitles, silence removal, or face-aware cropping; those need configured integrations. YouTube importing is intentionally unavailable—upload media you have permission to process.

## Install and run
1. Install Python 3.10+ and FFmpeg (`ffmpeg` and `ffprobe` on PATH). macOS: `brew install ffmpeg`; Debian/Ubuntu: `sudo apt install ffmpeg`; Windows: install an FFmpeg build and add `bin` to PATH.
2. `python -m pip install -r backend/requirements.txt`
3. Backend: `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`
4. In another terminal: `python -m http.server 8080 --directory frontend`
5. Open http://127.0.0.1:8080. Defaults use backend http://127.0.0.1:8000.

Scripts: `BASLAT-Windows.bat` or `bash BASLAT-Mac-Linux.sh`.

## Configuration and limitations
`MAX_UPLOAD_MB` controls upload limit (default 2048). Database and media live in `backend/database`. Optional service secrets belong on the backend only. Jobs run as FastAPI background tasks, suitable for local/single-user use; production should add durable workers, authentication, restricted CORS, quotas, secure storage, and monitoring. Current CORS allows all origins for local development. Advanced AI integrations need implementation/configuration; no API key is required for real upload and FFmpeg rendering.

Errors retain source uploads and are persisted on project records. FFmpeg failure reason is shown as Failed. You can test backend/FFmpeg status in Settings.
