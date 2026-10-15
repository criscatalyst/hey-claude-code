"""jv's reflex layer: a spoken sentence in, Mac actions out, before Claude sees it.

Laya (checkpoints/jv-reflex) decides what each clause asks for; code owns the
policy. Only a confident, fully named action fires. Everything else (a question,
a task, a reply to Claude, anything unsure) is returned untouched for Claude.

    import reflex
    reflex.load()                    # once, at voiced startup (~3 s)
    rest = reflex.handle(text)       # "" = all done here, else the words for Claude

Off switch: touch ~/.claude/voice/reflex.off (checked on every sentence).
Every decision is appended to ~/.claude/voice/reflex.jsonl.
"""
import json
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

import schema

HERE = Path(__file__).parent
CKPT = HERE / "checkpoints" / "jv-reflex"
VOICE_DIR = Path.home() / ".claude" / "voice"
OFF = VOICE_DIR / "reflex.off"
LOG = VOICE_DIR / "reflex.jsonl"
HEAD, MAXLEN = 512, 1024
GATE = 0.8                    # intent and target confidence needed to act without Claude
MAX_ACTIONS = 4               # per sentence
MAX_WORDS = 18                # longer than this is a task, not a command: Claude, without asking Laya
COOLDOWN_S = 4.0              # the same launch is not repeated within this window
TERMINALS = {"Terminal", "iTerm2", "cmux", "Ghostty", "Warp", "WezTerm", "Alacritty", "kitty"}

_agent = None
_last = {}

# ------------------------------------------------------------------ words
LEAD = r"(?:(?:ehm|allora|ok|okay|dai|senti|ecco|ehi|jarvis|aspetta|per favore|perfavore|puoi|mi puoi|potresti|riesci a|ti chiedo di)[\s,]+)*"
VERBS = r"(?:apri|aprimi|avvia|lancia|cerca|cercami|googla|googlami|scrivi|digita|detta|chiudi|chiudimi|alza|abbassa|metti|mettimi|fai|fammi|vai|passa|portami|togli|riprendi|silenzia)"
SPLIT = re.compile(r"\s*(?:,|;|\be poi\b|\bpoi\b|\be\b)\s+(?=" + VERBS + r"\b)", re.I)
PREFIX = {
    "web_search": re.compile(r"^" + LEAD + r"(?:(?:mi |puoi )?(?:cerca(?:mi|re)?|googla(?:mi|re)?|ricerca|trova|fa(?:i|mmi) una ricerca)"
                             r"(?: velocemente| un po')?(?: su google| sul web| online| in rete| su internet| per me)?(?: e cerca)?(?: su| di| per)?)[\s:,]+", re.I),
    "type_text": re.compile(r"^" + LEAD + r"(?:scriv(?:i|imi|ici|ere)|digit(?:a|ami|are)|detta(?:to)?|batti|trascrivi|inserisci(?: il testo)?|metti scritto)"
                            r"(?: testuale| esattamente| qui| questo)?(?: nel campo| nella chat| nel messaggio)?[\s:,]+", re.I),
}
TAIL = {
    "web_search": re.compile(r"(?:[\s,]+(?:su google|sul web|online|in rete|su internet|per favore|perfavore|grazie|dai|al volo|subito))+[\s.!?]*$", re.I),
    "type_text": re.compile(r"(?:[\s,]+(?:nel campo|nella chat|nel messaggio))[\s.!?]*$", re.I),
}
COMPOSE = re.compile(r"^" + LEAD + r"scriv(?:imi\b|i\s+(?:a|ad|al|alla|allo|agli|alle)\s|i\s+(?:una?|due|tre|qualche|delle|dei|degli)\s+"
                     r"(?:righe|mail|email|messaggi|post|caption|script|paragraf|testo|riassunt|articol|thread|tweet|fras|bozza))", re.I)
PLATFORM = re.compile(r"\b(?:cerc\w*|trova\w*|ricerca)\s+(?:\w+\s+)?(?:su|in|dentro|nel|nella|sul)\s+(?:instagram|insta|ig|youtube|"
                      r"tiktok|tik tok|linkedin|reddit|amazon|twitter|x|threads|facebook|github|gmail|whatsapp|spotify|"
                      r"netflix|notion|whop|telegram|discord|pinterest)\b", re.I)
FILLER = {"di", "a", "da", "in", "su", "per", "con", "il", "lo", "la", "i", "gli", "le", "un", "una", "e", "che", "come", "ehm"}
DOMAIN = re.compile(r"\b([a-z0-9][a-z0-9-]{1,40})\s+punto\s+(com|it|ai|io|org|net|dev|app|co|eu|so)\b", re.I)


SENTENCE = re.compile(r"(?<=[.?!])\s+")


def clauses(text):
    """Every sentence is its own piece, then each is cut before a command verb. Cutting only at
    verbs let "cerca su Instagram X. Parla di Y. Puoi fare ricerca?" become one Google search."""
    out = []
    for sentence in SENTENCE.split(str(text or "")):
        out += [c.strip(" ,;.?!") for c in SPLIT.split(sentence) if c.strip(" ,;.?!")]
    return out


def slot_text(intent, clause, ws, ans):
    """The free text to search or type. A known verb opening the clause settles
    where it starts (Laya's boundary word wavers by one); Laya's pick is the fallback."""
    m = PREFIX[intent].match(clause.strip())
    if m:
        rest = TAIL[intent].sub("", clause.strip()[m.end():])
        return rest.strip(" .!?,:\"'")
    s, e = ans["slot_start"], ans["slot_end"]
    if s["choice"] == "none":
        return ""
    a = int(s["choice"][1:])
    b = int(e["choice"][1:]) if e["choice"] != "none" and _conf(e) >= 0.6 else len(ws) - 1
    return " ".join(ws[a:max(a, b) + 1]).strip(" .!?,:\"'")


OPEN = re.compile(r"^" + LEAD + r"(?:a[pb]r[iì](?:mi)?(?: l'app(?:licazione)?)?|avvia|lancia|fammi vedere|mostrami|passa a|passami su|portami su|vai su|torna su|tira su|fai partire|mi apri)"
                  r"\s+(?:il |lo |la |le |i |gli |l')?(.+?)(?:[\s,]+(?:per favore|perfavore|grazie|dai|subito|al volo|un attimo|adesso))*[\s.!?]*$", re.I)
_squash = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())


def _similar(a, b):
    a, b = _squash(a), _squash(b)
    if not a or not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return 1 - prev[-1] / max(len(a), len(b))


def sounds_like_app(clause):
    """"apri <name>" and nothing else: match the name against every app's spoken
    names by spelling. Whisper writes "spotifai", "cap cut", "obsidien"; Laya also
    missed plain "apri spotify". A clear winner or nothing (Nus's soundsLike)."""
    m = OPEN.match(clause.strip())
    if not m or len(m.group(1).split()) > 3:
        return None
    heard = re.sub(r"^(?:app |applicazione )", "", m.group(1).strip().lower())
    # "apri gmail" is the website, not Mail: a name that sounds like a site is left to Laya.
    sites = [n.strip() for _, desc in schema.SITES.values() for n in desc.split(",")] + list(schema.SITES)
    if max(_similar(heard, n) for n in sites) >= 0.85:
        return None
    scored = []
    for key, (name, alias) in schema.APPS.items():
        names = [name] + [re.sub(r"^(?:il |lo |la |le |i |gli |l'|l')", "", x.strip()) for x in alias.split(",")]
        scored.append((max(_similar(heard, n) for n in names if len(_squash(n)) >= 3), key))
    scored.sort(reverse=True)
    (best, key), (second, _) = scored[0], scored[1]
    return key if best >= 0.75 and best - second >= 0.15 else None


def _conf(a):
    return a.get("answer_confidence", a.get("confidence", 0.0))


# ------------------------------------------------------------------ model
def load():
    global _agent
    if OFF.exists() or not (CKPT / "model.safetensors").exists():
        return False
    import laya
    _agent = laya.load(str(CKPT), device="mps")
    classify("apri chrome")
    return True


def classify(clause):
    ws, qs = schema.questions(clause, list(schema.APPS))
    return ws, _agent.predict({"utterance": clause}, qs, head_max_len=HEAD, max_len=MAXLEN)["answers"]


def decide(clause, ws, ans):
    """A fireable action for one clause, or None (the clause goes to Claude). Pure."""
    app = sounds_like_app(clause)
    if app:
        return {"intent": "open_app", "app": app}
    it, c = ans["intent"]["choice"], _conf(ans["intent"])
    if c < GATE or it in ("ask", "none"):
        return None
    if it == "open_app":
        app = ans["app"]["choice"]
        return {"intent": it, "app": app} if app != "none" and _conf(ans["app"]) >= GATE else None
    if it == "open_site":
        d = DOMAIN.search(clause)
        if d:
            url = "https://%s.%s" % (d.group(1).lower(), d.group(2).lower())
            known = [k for k, (u, _) in schema.SITES.items() if u.split("//")[1].removeprefix("www.") == url.split("//")[1]]
            return {"intent": it, "url": url, **({"site": known[0]} if known else {})}
        site = ans["site"]["choice"]
        return {"intent": it, "site": site, "url": schema.SITES[site][0]} if site in schema.SITES and _conf(ans["site"]) >= GATE else None
    if it == "close_tab" and ans["app"]["choice"] != "none":
        return None                            # "chiudi il terminale" is not a tab
    if it == "type_text" and COMPOSE.match(clause.strip()):
        return None                            # "scrivimi due righe su...", "scrivi a Lonnie...": write it, Claude
    if it in ("web_search", "type_text"):
        t = slot_text(it, clause, ws, ans)
        if it == "web_search" and PLATFORM.search(clause):
            return None                        # "cerca su Instagram l'ultimo post di…"
        # "cerca di..." cut off mid-sentence: nothing real to search or type.
        return {"intent": it, "text": t} if set(t.lower().split()) - FILLER else None
    return {"intent": it}


# ------------------------------------------------------------------ Mac actions
def _osa(script):
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)


def _front_app():
    r = subprocess.run(["lsappinfo", "info", "-only", "name", subprocess.run(["lsappinfo", "front"], capture_output=True, text=True).stdout.strip()],
                       capture_output=True, text=True)
    m = re.search(r'"LSDisplayName"="([^"]+)"', r.stdout)
    return m.group(1) if m else ""


def _wait_front(app, timeout=3.0):
    t = time.time()
    while time.time() - t < timeout:
        if _front_app() == app:
            time.sleep(0.2)                    # let the window take keyboard focus
            return True
        time.sleep(0.1)
    return False


def _running(app):
    return _osa('application "%s" is running' % app).stdout.strip() == "true"


def run(a):
    """Carry out one action. True = done; False = could not, let Claude have it."""
    it = a["intent"]
    if it == "open_app":
        return subprocess.run(["open", "-a", schema.APPS[a["app"]][0]], capture_output=True).returncode == 0
    if it in ("open_site", "web_search"):
        url = a["url"] if it == "open_site" else "https://www.google.com/search?q=" + urllib.parse.quote_plus(a["text"])
        # Safari unless Chrome was named in the sentence: after "apri chrome e cerca…" plain
        # `open` searched in the system default instead (live 2026-09-28).
        return subprocess.run(["open", "-a", a.get("browser", "Safari"), url], capture_output=True).returncode == 0
    if it in ("new_tab", "close_tab"):
        # The browser in front if it is one, else the sentence's browser (Safari by default).
        front = _front_app()
        app = front if front in ("Safari", "Google Chrome") else a.get("browser", "Safari")
        if it == "close_tab":
            if not _running(app):
                return False
            tab = "current tab" if app == "Safari" else "active tab"
            return _osa('tell application "%s" to if (count of windows) > 0 then close %s of front window' % (app, tab)).returncode == 0
        empty, more = (("make new document", "tell front window to set current tab to (make new tab)") if app == "Safari"
                       else ("make new window", "make new tab at end of tabs of front window"))
        return _osa('tell application "%s"\nactivate\nif (count of windows) = 0 then\n%s\nelse\n%s\nend if\nend tell' % (app, empty, more)).returncode == 0
    if it in ("volume_up", "volume_down"):
        step = 12 if it == "volume_up" else -12
        return _osa("set volume output volume ((output volume of (get volume settings)) + %d)" % step).returncode == 0
    if it == "mute":
        return _osa("set volume output muted (not (output muted of (get volume settings)))").returncode == 0
    if it == "play_pause":
        for app in ("Spotify", "Music"):
            if _running(app):
                return _osa('tell application "%s" to playpause' % app).returncode == 0
        return False
    if it == "screenshot":
        path = Path.home() / "Desktop" / time.strftime("Screenshot %Y-%m-%d alle %H.%M.%S.png")
        return subprocess.run(["screencapture", "-x", str(path)]).returncode == 0
    if it == "type_text":
        # Never into jv's own Terminal: there the words are for Claude.
        if _front_app() in TERMINALS:
            return False
        text = a["text"].replace("\\", "\\\\").replace('"', '\\"')
        return _osa('tell application "System Events" to keystroke "%s"' % text).returncode == 0
    return False


# ------------------------------------------------------------------ entry point
def handle(text):
    """Fire what is sure, return the rest for Claude ("" when nothing is left)."""
    if _agent is None or OFF.exists():
        return text
    t0 = time.time()
    rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "text": text, "clauses": []}
    try:
        if len(str(text).split()) > MAX_WORDS:
            rec["result"] = "claude-long"
            return text
        parts = clauses(text)
        plan = []
        for cl in parts:
            ws, ans = classify(cl)
            a = decide(cl, ws, ans)
            rec["clauses"].append({"c": cl, "intent": ans["intent"]["choice"], "conf": round(_conf(ans["intent"]), 3),
                                   "app": ans["app"]["choice"], "site": ans["site"]["choice"], "action": a})
            plan.append((cl, a))
        # A sentence that is not all actions is a sentence for Claude: "apri chrome e
        # dimmi cosa vedi" must reach Claude whole, not with its first half already done.
        if not plan or any(a is None for _, a in plan) or len(plan) > MAX_ACTIONS:
            rec["result"] = "claude"
            return text
        fired, rest, launched = [], [], None
        for cl, a in plan:
            if any(b.get("app") == "chrome" for _, b in plan) or re.search(r"\bchrome\b", text, re.I):
                a["browser"] = "Google Chrome"
            key = json.dumps(a, sort_keys=True)
            if a["intent"] in ("open_app", "open_site", "web_search") and time.time() - _last.get(key, 0) < COOLDOWN_S:
                fired.append("skip-cooldown")
                continue
            if a["intent"] == "type_text" and launched and not _wait_front(launched):
                ok = False                     # the app never came to the front: type nowhere
            else:
                ok = run(a)
            if a["intent"] == "open_app" and ok:
                launched = schema.APPS[a["app"]][0]
            _last[key] = time.time()
            fired.append(ok)
            if not ok:
                rest.append(cl)
        rec["fired"], rec["result"] = fired, ("reflex" if not rest else "partial")
        return ", ".join(rest)
    except Exception as e:                     # the reflex must never cost jv a sentence
        rec["error"] = repr(e)
        return text
    finally:
        rec["ms"] = int((time.time() - t0) * 1000)
        try:
            with LOG.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass
