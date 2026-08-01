#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
DASHBOARD="$ROOT/analysis/v2ex-analysis"

"$PYTHON" "$ROOT/analysis/build_analytics.py" --if-changed
"$PYTHON" -m unittest discover -s "$ROOT/tests" -p 'test_*.py'
"$PYTHON" "$ROOT/scripts/validate_analytics.py"

cd "$DASHBOARD"
npm run build
npm run test:budget
npm run test:e2e
