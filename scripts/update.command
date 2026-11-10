#!/bin/bash
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")/.."
git pull --ff-only
./scripts/setup.command
.venv/bin/python scripts/build_app.py --desktop
echo 'Update complete. Double-click DJ Intake on your Desktop.'
