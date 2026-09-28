#!/usr/bin/env python3
"""Voice mode per singola sessione Claude Code: Claude scrive righe 🔊, `say` le legge in coda.

Flag per sessione: ~/.claude/voice/<session_id>.on (voice-on / voice-off, o `jv` all'avvio).
Un solo script per tutti gli eventi:
  SessionStart     -> se lanciata da `jv` (env JV_PANE): accende il flag e dice a voiced il session_id
  UserPromptSubmit -> zittisce la risposta vecchia, chiede a Claude le righe 🔊
  PreToolUse       -> legge le 🔊 nuove scritte tra un'azione e l'altra (parla mentre lavora)
  Notification     -> avvisa a voce quando serve un permesso (e voiced accetta "sì"/"no")
  Stop             -> legge le 🔊 rimaste della risposta finale
  SessionEnd       -> pulisce
"""
import fcntl
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import voice_speak  # noqa: E402

VOICE_DIR = voice_speak.VOICE_DIR
LANGUAGES = {"it": "Italian", "en": "English", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese"}
_lang = voice_speak.settings()["language"]
INSTRUCTION = (
    "Voice mode is on: the user is listening to you, like a spoken assistant. "
    "While you work, before a meaningful step write one line starting with '🔊 ' with ONE short "
    "sentence on what you're doing or what you found (not at every single tool). Always end the "
    "answer with a '🔊 ' line of 1-2 sentences that gives the gist. Write the 🔊 lines in spoken "
    f"{LANGUAGES.get(_lang, _lang)}: no markdown, code, paths or symbols, and never say the word 'Jarvis'."
)


def transcript_lines(path):
    if not path or not Path(path).exists():
        return []
    return Path(path).read_text().splitlines()


def spoken_in(text):
    return [l.strip().removeprefix("🔊").strip() for l in text.splitlines()
            if l.strip().startswith("🔊")]


def turn_voice_lines(lines, offset):
    """Tutte le righe 🔊 scritte da Claude nel turno corrente, in ordine."""
    out = []
    for line in lines[offset:]:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        for block in entry.get("message", {}).get("content", []):
            if block.get("type") == "text":
                out += spoken_in(block.get("text", ""))
    return out


def first_sentence(text):
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[`*_#>|]", "", text).strip()
    return re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0][:300]


def speak_new(sid, transcript_path, final=None):
    """Dice le righe 🔊 del turno non ancora dette. La chiama l'hook (PreToolUse/Stop) e la chiama
    voiced ogni 0,2 s appena il transcript cambia, così una 🔊 si sente quando Claude la scrive e non
    al tool successivo. Il lock per sessione impedisce che la stessa riga esca due volte."""
    state = VOICE_DIR / f"{sid}.state"   # "offset spoken": inizio del turno nel transcript, righe già dette
    with open(VOICE_DIR / f"{sid}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        transcript = transcript_lines(transcript_path)
        try:
            offset, spoken = map(int, state.read_text().split())
        except (FileNotFoundError, ValueError):
            offset, spoken = len(transcript), 0  # voice acceso a metà turno: non rileggere lo storico
        lines = turn_voice_lines(transcript, offset)
        if final is not None:
            tail = spoken_in(final)
            if tail and lines[-len(tail):] != tail:
                lines += tail  # il transcript non ha ancora l'ultimo messaggio
            if not lines and final:
                lines = [first_sentence(final)]
        voice_speak.enqueue(lines[spoken:])
        state.write_text(f"{offset} {max(spoken, len(lines))}")


def main():
    payload = json.load(sys.stdin)
    sid = payload.get("session_id", "")
    event = payload.get("hook_event_name")
    pane = os.environ.get("JV_PANE")
    flag = VOICE_DIR / f"{sid}.on"
    state = VOICE_DIR / f"{sid}.state"   # "offset spoken": inizio del turno nel transcript, righe già dette
    perm = VOICE_DIR / f"perm-{pane}" if pane else None

    if event == "SessionStart" and pane and sid:
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        flag.touch()
        (VOICE_DIR / f"pane-{pane}").write_text(sid)
        return
    if event == "SessionEnd":
        for f in (flag, state, VOICE_DIR / f"{sid}.transcript", VOICE_DIR / f"{sid}.lock"):
            f.unlink(missing_ok=True)
        return
    if not sid or not flag.exists():
        return

    if event in ("UserPromptSubmit", "PreToolUse", "Stop") and perm:
        perm.unlink(missing_ok=True)

    if event == "UserPromptSubmit":
        voice_speak.stop_all()  # nuova domanda: zittisci la risposta vecchia
        with open(VOICE_DIR / f"{sid}.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state.write_text(f"{len(transcript_lines(payload.get('transcript_path')))} 0")
        (VOICE_DIR / f"{sid}.transcript").write_text(payload.get("transcript_path") or "")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit", "additionalContext": INSTRUCTION}}))
        return

    if event == "Notification":
        msg = payload.get("message", "")
        if payload.get("notification_type") == "permission_prompt" or "permission" in msg.lower():
            tool = re.search(r"use (\S+)", msg)
            voice_speak.enqueue([f"Mi serve il tuo ok per usare {tool.group(1) if tool else 'uno strumento'}. "
                                 "Dimmi sì o no."])
            if perm:
                perm.touch()
        return

    if event in ("PreToolUse", "Stop"):
        speak_new(sid, payload.get("transcript_path"),
                  payload.get("last_assistant_message", "") if event == "Stop" else None)


if __name__ == "__main__":
    main()
