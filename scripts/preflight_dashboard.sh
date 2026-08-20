#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
DASHBOARD="$ROOT/analysis/v2ex-analysis"

"$PYTHON" -m unittest discover -s "$ROOT/tests" -p 'test_*.py'
"$PYTHON" "$ROOT/scripts/evaluate_title_keywords.py"
"$PYTHON" "$ROOT/scripts/audit_source_quality.py" --fail-on-regression
if [[ -f "$ROOT/v2ex.sqlite" ]]; then
  "$PYTHON" "$ROOT/analysis/build_analytics.py" --if-changed
elif [[ ! -f "$DASHBOARD/public/dynamic-manifest.json" ]]; then
  "$PYTHON" "$ROOT/scripts/fetch_dashboard_data.py"
fi
"$PYTHON" "$ROOT/scripts/validate_analytics.py"

cd "$DASHBOARD"
npm run build
npm run test:budget
npm run test:e2e
