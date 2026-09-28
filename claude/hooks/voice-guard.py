#!/usr/bin/env python3
"""voice-guard: what a spoken request may NOT do in a `jv` session, whoever is speaking.

A microphone is an unauthenticated input: anyone in the room (or a video playing) can say
"hey jarvis". Messages, BooSend, deleting ordinary files: allowed by voice. The red list,
denied deterministically in turns that came from the voice (no sentence can argue with it):

  1. deleting inside a vital zone (listed in ~/.claude/voice-guard.json, plus the guard itself
     and any .env), or a folder that contains one
  2. mass deletion: more than MASS files in one command
  3. git that destroys work or history: push --force, reset --hard, clean, checkout --, branch -D
  4. reading secrets: .env, private keys, credentials, keychain, env dump
  5. changing the guard: settings.json, hooks/, voice-mode/

From the keyboard nothing changes. A red-listed call is also marked in `lastcall-<pane>`, so
voiced refuses a spoken "sì" on its permission prompt even in a keyboard turn.

Events: UserPromptSubmit (decides if the turn is spoken: voiced wrote the same words in
`said-<pane>` just before typing them) and PreToolUse (the check). Outside jv: exits at once.
Tests: voice_guard_test.py next to this file.
"""
import glob
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

HOME = Path.home()
VOICE_DIR = HOME / ".claude" / "voice"
CONFIG = HOME / ".claude" / "voice-guard.json"   # {"vital": ["~/path", ...]}: your own vital zones
GUARD = [HOME / ".claude" / "settings.json", HOME / ".claude" / "settings.local.json",
         HOME / ".claude" / "hooks", HOME / ".claude" / "voice-mode", CONFIG]


def _vital_zones():
    try:
        zones = json.loads(CONFIG.read_text()).get("vital", [])
    except (OSError, ValueError):
        zones = ["~/Documents", "~/Desktop"]      # until you list your own
    return [Path(os.path.expanduser(z)) for z in zones]


VITAL = _vital_zones() + GUARD
MASS = 25
LOG = VOICE_DIR / "guard.jsonl"

DELETE_VERBS = {"rm", "rmdir", "unlink", "shred", "srm", "trash", "truncate"}
WRITE_VERBS = {"rm", "rmdir", "unlink", "mv", "cp", "tee", "truncate", "chmod", "chown", "ln", "touch", "rsync", "install"}
SECRET_NAME = re.compile(r"(^|/)(\.env(\.[\w-]+)?|id_(rsa|ed25519|ecdsa)[\w.-]*|[^/]*\.pem|[^/]*\.p12|credentials(\.json)?|[^/]*secret[^/]*\.json|\.netrc|\.npmrc|\.pypirc)$", re.I)
SECRET_OK = re.compile(r"\.(example|sample|template|dist)$|\.pub$", re.I)
SECRET_CMD = re.compile(r"\bsecurity\s+(find-(generic|internet)-password|dump-keychain|export)\b|^\s*(printenv|env|export\s+-p|set)\s*$|\bcompgen\s+-v\b", re.I | re.M)
GIT_DESTROY = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?(?:push\b[^;&|]*?(?:\s--force(?:-with-lease)?\b|\s-f\b|\s\+\S)|reset\b[^;&|]*--hard|clean\b[^;&|]*-[a-z]*f|checkout\s+(?:\S+\s+)?--\s|checkout\s+\.(?:\s|$)|restore\s+(?:--\S+\s+)*\.(?:\s|$)|branch\s+-D\b|stash\s+(?:drop|clear)\b|filter-branch|filter-repo)", re.I)
OPAQUE_DELETE = re.compile(r"(^|\s)-delete(\s|$)|-exec\s+(rm|unlink)\b|\bxargs\s+(-\S+\s+)*rm\b|rmtree|os\.remove|os\.unlink|\.unlink\(|\bunlinkSync\b|rmSync|\brsync\b[^;&|]*--delete|\bdiskutil\s+(erase|reformat)|\bmkfs\b|\bdd\b[^;&|]*\bof=", re.I)


# ------------------------------------------------------------------ paths
def resolve(p, cwd):
    p = os.path.expandvars(os.path.expanduser(p.strip("'\"")))
    return Path(os.path.normpath(p if os.path.isabs(p) else os.path.join(cwd, p)))


def inside(p, zone):
    try:
        p.relative_to(zone)
        return True
    except ValueError:
        return False


def vital_hit(p):
    """The zone this path deletes into, or that it contains. None if it touches no vital zone."""
    if SECRET_NAME.search(str(p)) and not SECRET_OK.search(str(p)):
        return str(p)
    for z in VITAL:
        if inside(p, z) or inside(z, p):
            return str(z)
    return None


def count_files(paths, limit=MASS + 1):
    n = 0
    for p in paths:
        if p.is_dir() and not p.is_symlink():
            for _, _, files in os.walk(p):
                n += len(files) or 1
                if n >= limit:
                    return n
        else:
            n += 1
        if n >= limit:
            return n
    return n


def targets(args, cwd):
    out = []
    for a in args:
        if a.startswith("-"):
            continue
        r = resolve(a, cwd)
        if any(ch in a for ch in "*?["):
            out += [Path(x) for x in glob.glob(str(r))] or [r.parent]
        else:
            out.append(r)
    return out


# ------------------------------------------------------------------ the check
def segments(cmd):
    return [s for s in re.split(r"\s*(?:;|&&|\|\||\||\n)\s*", cmd) if s.strip()]


def words(seg):
    try:
        return shlex.split(seg)
    except ValueError:
        return seg.split()


def check_bash(cmd, cwd):
    if GIT_DESTROY.search(cmd):
        return "git that destroys work or history (push --force, reset --hard, clean, checkout --, branch -D)"
    if SECRET_CMD.search(cmd):
        return "reading secrets (keychain or environment variables)"
    for seg in segments(cmd):
        w = words(seg)
        if not w:
            continue
        verb = os.path.basename(w[0]) if w[0] != "sudo" else os.path.basename(w[1]) if len(w) > 1 else ""
        args = w[1:] if w[0] != "sudo" else w[2:]
        if verb == "cd":                         # "cd dashboard && rm server.py"
            cwd = str(resolve(args[0], cwd)) if args else str(HOME)
            continue
        # secrets: any real .env / key file mentioned in any command
        for a in args:
            if not a.startswith("-") and SECRET_NAME.search(a.strip("'\"")) and not SECRET_OK.search(a.strip("'\"")):
                return "a file holding secrets (%s)" % os.path.basename(a.strip("'\""))
        # the guard itself: no writes to it by voice
        writes = verb in WRITE_VERBS or re.search(r"(^|[^2&])>{1,2}\s*\S", seg) or (verb in ("sed", "perl") and any(x.startswith("-i") for x in args))
        if writes:
            for t in targets(args, cwd) + [resolve(m, cwd) for m in re.findall(r">{1,2}\s*(\S+)", seg)]:
                if any(inside(t, g) or inside(g, t) for g in GUARD):
                    return "changing the voice-guard or Claude Code settings (%s)" % t
        delete = verb in DELETE_VERBS or (verb == "mv" and any(".Trash" in a for a in args))
        if delete:
            ts = targets(args[:-1] if verb == "mv" else args, cwd)
            for t in ts:
                z = vital_hit(t)
                if z:
                    return "deleting inside a vital zone (%s)" % z
            n = count_files(ts)
            if n > MASS:
                return "mass deletion (more than %d files)" % MASS
    if OPAQUE_DELETE.search(cmd):
        # Paths as the shell sees them (spaces inside quotes kept), plus paths quoted inside
        # code strings: python3 -c "shutil.rmtree('/Users/…/Media')".
        found = [w for seg in segments(cmd) for w in words(seg) if re.match(r"(?:~|\$HOME|/|\.{1,2}(?:/|$))", w)]
        found += re.findall(r"['\"]((?:~|/)[^'\"]+)['\"]", cmd)
        roots = [resolve(a, cwd) for a in found] or [Path(cwd)]
        for r in roots:
            z = vital_hit(r)
            if z:
                return "deleting inside a vital zone (%s)" % z
        if count_files([r for r in roots if r.exists()]) > MASS:
            return "mass deletion (more than %d files)" % MASS
    return None


def check(tool, inp, cwd):
    """The red-list reason for this call, or None."""
    inp = inp or {}
    if tool == "Bash":
        return check_bash(str(inp.get("command", "")), cwd)
    path = inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or ""
    if tool in ("Read", "Grep", "Glob", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        pats = [path, inp.get("glob", ""), inp.get("pattern", "") if tool == "Glob" else ""]
        for p in filter(None, pats):
            if SECRET_NAME.search(p.rstrip("*")) and not SECRET_OK.search(p):
                return "a file holding secrets (%s)" % os.path.basename(p)
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit") and path:
        t = resolve(path, cwd)
        if any(inside(t, g) for g in GUARD):
            return "changing the voice-guard or Claude Code settings (%s)" % t
    return None


# ------------------------------------------------------------------ hook
def norm(t):
    return " ".join(str(t or "").split()).strip().lower()


def main():
    pane = os.environ.get("JV_PANE")
    if not pane:
        return                                   # not a jv session: never in the way
    payload = json.load(sys.stdin)
    event = payload.get("hook_event_name")
    turn = VOICE_DIR / f"turn-{pane}"
    if event == "UserPromptSubmit":
        said = VOICE_DIR / f"said-{pane}"
        spoken = said.exists() and norm(said.read_text()) == norm(payload.get("prompt"))
        said.unlink(missing_ok=True)
        turn.write_text("voice" if spoken else "keyboard")
        return
    if event != "PreToolUse":
        return
    reason = check(payload.get("tool_name", ""), payload.get("tool_input"), payload.get("cwd") or os.getcwd())
    (VOICE_DIR / f"lastcall-{pane}").write_text("red" if reason else "ok")
    # Unknown turn origin in a jv session counts as spoken: the safe side.
    spoken = not turn.exists() or turn.read_text().strip() != "keyboard"
    if not (reason and spoken):
        return
    with LOG.open("a") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "pane": pane, "tool": payload.get("tool_name"),
                            "input": payload.get("tool_input"), "reason": reason}, ensure_ascii=False) + "\n")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": "Blocked by voice-guard: %s. This request came in by voice, and this action is never "
                                    "done by voice, whoever is speaking. Tell the user: if they really want it, they "
                                    "type it on the keyboard." % reason}}))


if __name__ == "__main__":
    main()
