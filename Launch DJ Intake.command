#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then ./scripts/setup.command; fi
exec .venv/bin/python -m dj_intake.server
