#!/usr/bin/env python3
"""voice-guard tests: every red-list rule, the things that must stay allowed, and the hook
wiring (spoken vs typed turn, outside jv). Nothing is deleted: only check() is called, on
throwaway folders that stand in for your vital zones.   python3 voice_guard_test.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("vg", HERE / "voice-guard.py")
vg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vg)

H = str(Path.home())
root = Path(tempfile.mkdtemp())
work = root / "work"                      # stands in for a workspace with vital and ordinary parts
wiki, app, scratch = work / "wiki", work / "app", work / "scratch"
few, many = root / "few", root / "many"
for d in (wiki, app / "src", scratch, few, many):
    d.mkdir(parents=True)
for i in range(3):
    (few / f"f{i}.tmp").write_text("x")
for i in range(40):
    (many / f"f{i}.tmp").write_text("x")
vg.VITAL = [wiki, app] + vg.GUARD
W = str(work)

B = lambda cmd, cwd=H: ("Bash", {"command": cmd}, cwd)
ALLOW = [
    B("rm /tmp/foo.txt"),
    B("rm ~/Downloads/installer.dmg"),
    B(f'rm "{W}/scratch/old.mp4"'),
    B(f"rm -rf {few}"),
    B(f"find {few} -name '*.tmp' -delete"),
    B("mv ~/Downloads/old.zip ~/.Trash/"),
    B("git push origin main", str(app)),
    B("git status && git log -3", str(app)),
    B("git checkout -b new-feature", str(app)),
    B("cat README.md", str(app)),
    B("ls ~/.claude/hooks"),
    B("touch ~/.claude/voice/reflex.off"),
    B("cp .env.example .env.example.bak", str(app)),
    ("Read", {"file_path": f"{app}/src/main.py"}, H),
    ("Read", {"file_path": f"{app}/.env.example"}, H),
    ("Read", {"file_path": H + "/.ssh/id_ed25519.pub"}, H),
    ("Edit", {"file_path": f"{app}/src/main.py"}, H),
    ("Write", {"file_path": f"{W}/scratch/idea.md"}, H),
    ("mcp__claude_ai_Gmail__send_message", {"to": "x"}, H),
]
BLOCK = [
    B(f'rm -rf "{app}"'),
    B(f'rm "{wiki}/roadmap.md"'),
    B(f'rm -rf "{W}"'),
    B("rm -rf ~"),
    B("cd app && rm src/main.py", W),
    B(f'mv "{wiki}" ~/.Trash/'),
    B(f'find "{app}" -name "*.json" -delete'),
    B(f"python3 -c \"import shutil; shutil.rmtree('{wiki}')\""),
    B(f"rm -rf {many}"),
    B(f"rm {many}/*.tmp"),
    B("git push --force origin main", str(app)),
    B("git push -f", str(app)),
    B("git reset --hard HEAD~3", str(app)),
    B("git clean -fd", str(app)),
    B("git checkout -- .", str(app)),
    B("git branch -D dev", str(app)),
    B("cat .env", str(app)),
    B("grep API_KEY .env", str(app)),
    B("security find-generic-password -s github -w"),
    B("printenv"),
    B("cat ~/.ssh/id_ed25519"),
    B("echo '{}' > ~/.claude/settings.json"),
    B("sed -i '' 's/deny/allow/' ~/.claude/hooks/voice-guard.py"),
    B("rm ~/.claude/hooks/voice-guard.py"),
    B("echo '{\"vital\": []}' > ~/.claude/voice-guard.json"),
    ("Read", {"file_path": f"{app}/.env"}, H),
    ("Read", {"file_path": H + "/.ssh/id_ed25519"}, H),
    ("Grep", {"pattern": "KEY", "path": f"{app}/.env"}, H),
    ("Edit", {"file_path": H + "/.claude/settings.json"}, H),
    ("Write", {"file_path": H + "/.claude/hooks/voice-guard.py"}, H),
    ("Write", {"file_path": H + "/.claude/voice-guard.json"}, H),
]


def run_hook(event, pane, extra, said=None):
    env = dict(os.environ)
    env.pop("JV_PANE", None)
    if pane:
        env["JV_PANE"] = pane
        if said is not None:
            (vg.VOICE_DIR / f"said-{pane}").write_text(said)
    payload = {"hook_event_name": event, "session_id": "test", "cwd": H, **extra}
    r = subprocess.run([sys.executable, str(HERE / "voice-guard.py")], input=json.dumps(payload), env=env, capture_output=True, text=True)
    return r.stdout


fails = 0
for tool, inp, cwd in ALLOW:
    r = vg.check(tool, inp, cwd)
    if r:
        fails += 1
        print("FAIL should allow:", tool, inp, "->", r)
for tool, inp, cwd in BLOCK:
    if not vg.check(tool, inp, cwd):
        fails += 1
        print("FAIL should block:", tool, inp)

# wiring: spoken turn blocks, typed turn allows, outside jv nothing happens
vg.VOICE_DIR.mkdir(parents=True, exist_ok=True)
pane = "jv-guardtest"
danger = {"tool_name": "Bash", "tool_input": {"command": "rm -rf ~/.claude/hooks"}}   # vital on every install
run_hook("UserPromptSubmit", pane, {"prompt": "delete the hooks"}, said="delete the hooks")
spoken = run_hook("PreToolUse", pane, danger)
run_hook("UserPromptSubmit", pane, {"prompt": "delete the hooks"})
typed = run_hook("PreToolUse", pane, danger)
outside = run_hook("PreToolUse", None, danger)
checks = [("spoken turn denied", '"deny"' in spoken), ("typed turn allowed", typed.strip() == ""),
          ("outside jv untouched", outside.strip() == ""),
          ("red call marked for voiced", (vg.VOICE_DIR / f"lastcall-{pane}").read_text() == "red")]
lines = vg.LOG.read_text().splitlines() if vg.LOG.exists() else []
vg.LOG.write_text("".join(l + "\n" for l in lines if pane not in l))
for f in ("turn", "lastcall", "said"):
    (vg.VOICE_DIR / f"{f}-{pane}").unlink(missing_ok=True)
for name, ok in checks:
    if not ok:
        fails += 1
        print("FAIL", name)

print(f"{len(ALLOW)} allow + {len(BLOCK)} block + {len(checks)} wiring cases: {'ALL PASS' if not fails else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
