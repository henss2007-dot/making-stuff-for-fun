#!/usr/bin/env sh
# Start WordMine on macOS / Linux. First time: pip install -r requirements.txt
cd "$(dirname "$0")" && exec python3 -m wordmine "$@"
