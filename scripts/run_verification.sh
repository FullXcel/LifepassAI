#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m compileall -q .
python tests/verify_mvp.py
python cli_demo.py > /tmp/lifepass_ai_report_preview.md
echo "Verification complete. Report preview written to /tmp/lifepass_ai_report_preview.md"
