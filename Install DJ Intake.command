#!/bin/bash
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
destination="$HOME/Library/Application Support/DJ Intake Source"
if ! xcode-select -p >/dev/null 2>&1; then
  echo 'Install Apple Command Line Tools with xcode-select --install, then run this again.'
  exit 1
fi
if [ ! -d "$destination/.git" ]; then
  mkdir -p "$(dirname "$destination")"
  git clone https://github.com/clement55688/dj-intake-app.git "$destination"
fi
cd "$destination"
./scripts/setup.command
.venv/bin/python scripts/build_app.py --desktop
open "$HOME/Desktop/DJ Intake.app"
