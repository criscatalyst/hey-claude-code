#!/bin/bash
# hey-claude-code installer: puts jv, the voice daemon and the hooks in place on this Mac.
# Safe to run again: it never overwrites your settings, and backs up ~/.claude/settings.json first.
set -euo pipefail
R="$(cd "$(dirname "$0")" && pwd)"
C="$HOME/.claude"
VM="$C/voice-mode"
say_step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

say_step "Checking this Mac"
[ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] || { echo "hey-claude-code needs a Mac with Apple Silicon (M1 or newer)."; exit 1; }
command -v claude >/dev/null || { echo "Claude Code not found. Install it first: https://claude.com/claude-code"; exit 1; }
if ! command -v tmux >/dev/null; then
  command -v brew >/dev/null || { echo "tmux is missing and Homebrew isn't installed. Install tmux, then run this again."; exit 1; }
  echo "Installing tmux with Homebrew…"; brew install tmux
fi

say_step "Copying files"
mkdir -p "$C/hooks" "$VM/laya/data" "$C/voice" "$HOME/.local/bin"
cp "$R"/claude/hooks/*.py "$C/hooks/"
cp "$R"/claude/voice-mode/voiced.py "$R"/claude/voice-mode/beep.wav "$VM/"
cp "$R"/claude/voice-mode/laya/*.py "$R"/claude/voice-mode/laya/train-reflex.sh "$VM/laya/"
cp "$R"/claude/voice-mode/laya/data/blind_test.json "$VM/laya/data/"
cp "$R"/bin/* "$HOME/.local/bin/"
chmod +x "$HOME/.local/bin/jv" "$HOME/.local/bin/voice-on" "$HOME/.local/bin/voice-off" "$C"/hooks/*.py
[ -f "$VM/settings.json" ] || cp "$R/examples/settings.example.json" "$VM/settings.json"
[ -f "$C/voice-guard.json" ] || cp "$R/examples/voice-guard.example.json" "$C/voice-guard.json"

say_step "Python environment (~2 GB with the speech and reflex models' libraries)"
if command -v uv >/dev/null; then
  [ -x "$VM/venv/bin/python" ] || uv venv --python 3.11 "$VM/venv"
  VIRTUAL_ENV="$VM/venv" uv pip install -q -r "$R/requirements.txt"
else
  [ -x "$VM/venv/bin/python" ] || python3 -m venv "$VM/venv"
  "$VM/venv/bin/python" -m pip install -q --upgrade pip
  "$VM/venv/bin/python" -m pip install -q -r "$R/requirements.txt"
fi
"$VM/venv/bin/python" -c "import openwakeword.utils as u; u.download_models(model_names=['hey_jarvis'])" >/dev/null

say_step "Registering the hooks in ~/.claude/settings.json"
python3 - "$C/settings.json" <<'PY'
import json, shutil, sys, time
from pathlib import Path
p = Path(sys.argv[1])
s = json.loads(p.read_text()) if p.exists() else {}
if p.exists():
    shutil.copy(p, p.with_name("settings.json.bak-%s" % time.strftime("%Y%m%d-%H%M%S")))
hooks = s.setdefault("hooks", {})
home = str(Path.home())
want = [("PreToolUse", "*", "voice-mode.py"), ("PreToolUse", "*", "voice-guard.py"),
        ("UserPromptSubmit", None, "voice-mode.py"), ("UserPromptSubmit", None, "voice-guard.py"),
        ("Stop", None, "voice-mode.py"), ("Notification", None, "voice-mode.py"),
        ("SessionStart", None, "voice-mode.py"), ("SessionEnd", None, "voice-mode.py")]
for event, matcher, script in want:
    lst = hooks.setdefault(event, [])
    cmd = "%s/.claude/hooks/%s" % (home, script)
    if any(h.get("command") == cmd for e in lst for h in e.get("hooks", [])):
        continue
    entry = {"hooks": [{"type": "command", "command": cmd}]}
    if matcher:
        entry = {"matcher": matcher, **entry}
    lst.append(entry)
p.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n")
PY

say_step "Testing the voice-guard"
python3 "$C/hooks/voice_guard_test.py"

cat <<EOF

Done. Next steps:
  1. Make sure ~/.local/bin is on your PATH, then open a new Terminal and type:  jv
  2. The first time, macOS asks for the Microphone. For the right-⌘ tap, turn on Terminal in
     System Settings > Privacy & Security > Input Monitoring.
  3. List the folders you never want deleted by voice in ~/.claude/voice-guard.json
  4. Italian voice "Luca (Enhanced)": System Settings > Accessibility > Spoken Content > System
     voice > Manage Voices. Other language? Edit ~/.claude/voice-mode/settings.json
  5. Optional, Italian only: train the fast reflex layer (about 70 min on an M-series Mac):
     cd ~/.claude/voice-mode/laya && ./train-reflex.sh
EOF
