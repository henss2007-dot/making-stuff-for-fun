#!/usr/bin/env sh
# Start WordMine on macOS / Linux.
# First time:  python3 -m pip install -r requirements.txt && python3 -m wordmine dictionary
cd "$(dirname "$0")" && exec python3 -m wordmine "$@"
