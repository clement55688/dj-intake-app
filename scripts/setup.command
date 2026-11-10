#!/bin/bash
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")/.."
PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then echo 'Install Python 3.10 or later first.'; exit 1; fi
"$PYTHON" -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10 or later is required"'
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
if ! { ffmpeg -version >/dev/null 2>&1 && ffprobe -version >/dev/null 2>&1; } && ! { "$HOME/.stacher/ffmpeg" -version >/dev/null 2>&1 && "$HOME/.stacher/ffprobe" -version >/dev/null 2>&1; }; then
  if command -v brew >/dev/null; then brew install ffmpeg; else echo 'Install FFmpeg (ffmpeg and ffprobe) and rerun setup.'; exit 1; fi
fi
if ! command -v deno >/dev/null && [ ! -x "$HOME/.stacher/deno" ]; then
  if command -v brew >/dev/null; then brew install deno; else echo 'For YouTube, install Deno and rerun setup.'; fi
fi
echo 'Ready. Double-click Launch DJ Intake.command.'
