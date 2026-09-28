#!/bin/bash
# Maintainer tool: copy the files of a working install (~/.claude, ~/.local/bin) back into this repo.
# Run it after changing the live setup, then review `git diff` before committing.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
C="$HOME/.claude"
mkdir -p "$R/bin" "$R/claude/hooks" "$R/claude/voice-mode/laya/data"
cp "$HOME/.local/bin/jv" "$HOME/.local/bin/voice-on" "$HOME/.local/bin/voice-off" "$R/bin/"
cp "$C/hooks/voice-mode.py" "$C/hooks/voice_speak.py" "$C/hooks/voice-guard.py" "$C/hooks/voice_guard_test.py" "$R/claude/hooks/"
cp "$C/voice-mode/voiced.py" "$C/voice-mode/beep.wav" "$R/claude/voice-mode/"
cp "$C/voice-mode/laya/"{reflex,schema,gen_data,train,evaluate}.py "$C/voice-mode/laya/train-reflex.sh" "$R/claude/voice-mode/laya/"
cp "$C/voice-mode/laya/data/blind_test.json" "$R/claude/voice-mode/laya/data/"
chmod +x "$R/bin/"* "$R/claude/hooks/"*.py
echo "exported into $R — now: git -C \"$R\" diff"
