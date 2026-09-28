#!/bin/bash
# Build the Italian training set, fine-tune Laya on this Mac's GPU (~70 min on an M5, keep it plugged in
# and the lid open), then score it on the 150-command blind test. jv picks the model up on its next start.
set -euo pipefail
cd "$(dirname "$0")"
PY=../venv/bin/python
$PY gen_data.py 3000
PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.6 PYTORCH_MPS_LOW_WATERMARK_RATIO=0.5 caffeinate -i $PY -u train.py 3 2>&1 | tee train.log
$PY evaluate.py checkpoints/jv-reflex
