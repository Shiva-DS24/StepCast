#!/usr/bin/env bash
# Start StepCast on Linux / macOS (run install-linux-mac.sh once first)
# StepCast 1.3 - Dr Sivakumar Manickam <skumar@staff.odc.edu.om>, developed with the help of Claude (Anthropic)
cd "$(dirname "$0")"
if [ ! -x app/.venv/bin/python ]; then
  echo "StepCast is not installed yet. Please run install-linux-mac.sh first."
  read -r -p "Press Enter to close..." _
  exit 1
fi
nohup app/.venv/bin/python app/record.py >/dev/null 2>&1 &
