#!/usr/bin/env python3
"""Coda unica delle frasi da dire con `say`: una alla volta, in ordine, mai sovrapposte.

Le casse sono una sola, quindi la coda è globale (non per sessione).
  enqueue(lines) -> accoda e, se nessuno sta parlando, avvia un worker staccato
  stop_all()     -> svuota la coda e zittisce la frase in corso (barge-in, nuova domanda, voice-off)
  speaking()     -> True mentre `say` sta parlando (voiced lo usa per non sentirsi da solo)
CLI: voice_speak.py drain | stop
"""
import fcntl
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

VOICE_DIR = Path.home() / ".claude" / "voice"
QUEUE = VOICE_DIR / "queue.txt"
QUEUE_LOCK = VOICE_DIR / "queue.lock"
WORKER_LOCK = VOICE_DIR / "worker.lock"
SPEAKING = VOICE_DIR / "speaking.pid"
SETTINGS_FILE = Path.home() / ".claude" / "voice-mode" / "settings.json"
DEFAULTS = {"language": "it", "tts_voice": "Luca (Enhanced)"}


def settings():
    """~/.claude/voice-mode/settings.json over the defaults: language (whisper code), tts_voice (`say -v`)."""
    try:
        return {**DEFAULTS, **json.loads(SETTINGS_FILE.read_text())}
    except (OSError, ValueError):
        return dict(DEFAULTS)


VOICE = settings()["tts_voice"]


def _with_queue(fn):
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return fn()


def enqueue(lines):
    lines = [l.replace("\n", " ").strip() for l in lines if l.strip()]
    if not lines:
        return

    def add():
        with open(QUEUE, "a") as q:
            q.write("\n".join(lines) + "\n")

    _with_queue(add)
    subprocess.Popen([sys.executable, __file__, "drain"], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _pop():
    def pop():
        if not QUEUE.exists():
            return None
        lines = QUEUE.read_text().splitlines()
        if not lines:
            return None
        QUEUE.write_text("".join(l + "\n" for l in lines[1:]))
        return lines[0]

    return _with_queue(pop)


def _speaking_pid():
    try:
        pid = int(SPEAKING.read_text())
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


def speaking():
    return _speaking_pid() is not None


def stop_all():
    _with_queue(lambda: QUEUE.write_text(""))
    pid = _speaking_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def drain():
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        with open(WORKER_LOCK, "w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return  # c'è già un worker: ci pensa lui
            while (line := _pop()) is not None:
                proc = subprocess.Popen(["say", "-v", VOICE, line])
                SPEAKING.write_text(str(proc.pid))
                proc.wait()
                SPEAKING.unlink(missing_ok=True)
        # Lock rilasciato: se nel frattempo qualcuno ha accodato, rigira.
        if not (QUEUE.exists() and QUEUE.read_text().strip()):
            return


if __name__ == "__main__":
    {"drain": drain, "stop": stop_all}[sys.argv[1]]()
