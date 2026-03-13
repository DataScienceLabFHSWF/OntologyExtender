#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "Missing .env file. Copy .env.example to .env and update values first."
  exit 1
fi

prompt="${*:-Summarize the current Miro board and list top 5 actionable items.}"

PYTHON_BIN="python"
if [[ -x .venv/bin/python ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

"$PYTHON_BIN" client_bridge.py --prompt "$prompt"
