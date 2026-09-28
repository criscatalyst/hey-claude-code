#!/usr/bin/env python3
"""voiced: l'orecchio di `jv`. Ascolta la wake word "hey jarvis" (o un tocco sul ⌘ destro), registra la frase, la trascrive
con mlx-whisper e la scrive nella sessione Claude Code dentro tmux.

Uso: voiced.py <nome-sessione-tmux>   (lo lancia `jv`, muore quando la sessione tmux chiude)

- Mentre `say` parla resta attiva solo la wake word: dirla zittisce la voce (barge-in).
- "stop" / "basta" / "zitto"   -> zittisce e basta
- "interrompi" / "fermati"      -> Esc: ferma Claude
- con un permesso in attesa: "sì" -> Invio, "no" -> Esc
- rispetta voice-off: se il flag della sessione non c'è, ignora la wake word
"""
import importlib.util
import os
import re
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import mlx_whisper
import numpy as np
import sounddevice as sd
from openwakeword.model import Model

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
import voice_speak  # noqa: E402

# Riflesso: i comandi semplici ("apri chrome", "cerca X", "alza il volume") partono sul Mac
# senza passare da Claude. Modello + regole in laya/reflex.py. Spento: touch ~/.claude/voice/reflex.off
sys.path.insert(0, str(Path(__file__).parent / "laya"))
try:
    import reflex  # noqa: E402
except Exception as e:  # senza riflesso jv funziona come prima
    print("reflex non disponibile:", e, flush=True)
    reflex = None

PANE = sys.argv[1]
VOICE_DIR = voice_speak.VOICE_DIR
WHISPER = "mlx-community/whisper-large-v3-turbo-q4"
LANG = voice_speak.settings()["language"]   # whisper language code, from settings.json
SR, CHUNK = 16000, 1280          # 80 ms, il passo di openWakeWord
WAKE_THRESHOLD = 0.4                # la pronuncia italiana arriva ~0.5, l'inglese ~0.99
BEEP = Path(__file__).parent / "beep.wav"   # 80 ms: i suoni di sistema durano >0.5s e coprono la frase
SKIP_S = 0.15                     # audio buttato dopo il wake: coda del nome + beep
SILENCE_END_S, START_TIMEOUT_S, MAX_S = 1.5, 5.0, 30.0
RECORDINGS = VOICE_DIR / "recordings"   # ogni frase salvata, per confrontare modelli e impostazioni
# Contesto per whisper: indovina meglio le parole se sa di cosa si parla.
PROMPT = ("Comandi a voce a un assistente: apri, cerca, scrivi, chiudi, alza, abbassa. Claude, Jarvis, Laya, "
          "Spotify, WhatsApp, CapCut, Obsidian, Chrome, Safari, Notion, BooSend, Whop, file, cartella, repo, commit, "
          "dashboard, carosello, reel, script, video, wiki, terminale, Telegram, MAC-C, MAC-L.")

STOP = {"stop", "basta", "zitto", "silenzio", "fermo", "ok basta"}
INTERRUPT = {"interrompi", "fermati", "annulla", "ferma tutto"}
YES = {"sì", "si", "ok", "okay", "vai", "procedi", "certo", "va bene", "yes"}
NO = {"no", "non farlo", "nega", "rifiuta"}
HALLUCINATIONS = ("sottotitoli", "grazie per la visione", "amara.org")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True).returncode == 0


def beep(sound=BEEP):
    subprocess.Popen(["afplay", str(sound)])


def voice_on():
    sid_file = VOICE_DIR / f"pane-{PANE}"
    return sid_file.exists() and (VOICE_DIR / f"{sid_file.read_text().strip()}.on").exists()


def rms(chunk):
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))


def record(stream, floor):
    """Registra finché non smetti di parlare, senza nome e beep in testa. None se non dici niente."""
    threshold = max(floor * 2.5, 250.0)
    frames, started, silent, t0 = [], False, 0.0, time.time()
    while time.time() - t0 < MAX_S:
        chunk, _ = stream.read(CHUNK)
        chunk = chunk[:, 0]
        if time.time() - t0 < SKIP_S:
            continue
        frames.append(chunk)
        if rms(chunk) > threshold:
            started, silent = True, 0.0
        else:
            silent += CHUNK / SR
        if not started and time.time() - t0 > START_TIMEOUT_S:
            return None
        if started and silent >= SILENCE_END_S:
            break
    return np.concatenate(frames) if frames else None


def save(audio, text):
    RECORDINGS.mkdir(parents=True, exist_ok=True)
    stem = RECORDINGS / time.strftime("%Y%m%d-%H%M%S")
    with wave.open(f"{stem}.wav", "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(audio.tobytes())
    Path(f"{stem}.txt").write_text(text)


def transcribe(audio):
    text = mlx_whisper.transcribe(audio.astype(np.float32) / 32768.0, path_or_hf_repo=WHISPER,
                                  language=LANG, initial_prompt=voice_speak.settings().get("whisper_prompt", PROMPT))["text"].strip()
    if any(h in text.lower() for h in HALLUCINATIONS):
        return ""
    # Toglie la wake word in testa anche se whisper la storpia ("di Jarvis", "ehi Jarvis,").
    return re.sub(r"^\W*(?:\w+\W+){0,2}?jarvis\W*", "", text, flags=re.IGNORECASE).strip()


def handle(text):
    key = text.lower().strip(" .,!?")
    perm = VOICE_DIR / f"perm-{PANE}"
    if not key:
        beep(Path("/System/Library/Sounds/Basso.aiff"))
        return
    if key in STOP:
        return  # la voce è già stata zittita al risveglio
    if key in INTERRUPT:
        tmux("send-keys", "-t", PANE, "Escape")
        return
    if perm.exists() and (key in YES or key in NO):
        # Lista rossa (hooks/voice-guard.py): un "sì" detto nella stanza non la approva mai.
        last = VOICE_DIR / f"lastcall-{PANE}"
        if key in YES and last.exists() and last.read_text().strip() == "red":
            log("sì a voce rifiutato: azione nella lista rossa, serve la tastiera")
            beep(Path("/System/Library/Sounds/Basso.aiff"))
            voice_speak.enqueue(["Questa la devi confermare con la tastiera."])
            return
        tmux("send-keys", "-t", PANE, "Enter" if key in YES else "Escape")
        perm.unlink(missing_ok=True)
        return
    if reflex:
        rest = reflex.handle(text)
        if rest != text:
            log("riflesso:", repr(text), "->", "fatto" if not rest else "a Claude: " + repr(rest))
        if not rest:
            return
        text = rest
    (VOICE_DIR / f"said-{PANE}").write_text(text)   # voice-guard: questo turno è a voce
    tmux("send-keys", "-t", PANE, "-l", "--", text)
    tmux("send-keys", "-t", PANE, "Enter")


def speak_watch():
    """Le righe 🔊 si dicono appena Claude le scrive nel transcript, non al tool dopo (misurato
    2026-09-28: 0,7 s di attesa in mediana, fino a 2,8 s). Stessa funzione e stesso lock dell'hook."""
    spec = importlib.util.spec_from_file_location("voice_mode", Path.home() / ".claude" / "hooks" / "voice-mode.py")
    vm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vm)
    seen = None
    while True:
        time.sleep(0.2)
        try:
            sid = (VOICE_DIR / f"pane-{PANE}").read_text().strip()
            path = (VOICE_DIR / f"{sid}.transcript").read_text().strip()
            if not (VOICE_DIR / f"{sid}.on").exists() or not (VOICE_DIR / f"{sid}.state").exists():
                continue
            stamp = (path, os.path.getmtime(path))
            if stamp != seen:
                seen = stamp
                vm.speak_new(sid, path)
        except (OSError, ValueError):
            continue


RIGHT_CMD = 54                    # keycode del ⌘ destro
TAP_MAX_S = 0.6                   # premuto e rilasciato entro questo tempo, senza altri tasti


def cmd_tap_watch(trigger):
    """Un tocco sul ⌘ destro da solo vale come "hey jarvis". Con altri tasti o click in mezzo
    (⌘C, ⌘+click) è una scorciatoia e non conta. Tap in sola lettura: non tocca i tasti."""
    import Quartz
    st = {"down": 0.0, "other": False}

    def cb(proxy, etype, event, refcon):
        if etype in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            Quartz.CGEventTapEnable(tap, True)   # macOS spegne i tap lenti: Chirp era muto da giorni così
            return event
        if etype == Quartz.kCGEventFlagsChanged:
            code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            if code == RIGHT_CMD:
                if Quartz.CGEventGetFlags(event) & Quartz.kCGEventFlagMaskCommand:
                    st["down"], st["other"] = time.time(), False
                elif st["down"]:
                    if not st["other"] and time.time() - st["down"] < TAP_MAX_S:
                        trigger.set()
                    st["down"] = 0.0
            elif st["down"]:
                st["other"] = True
        elif st["down"]:
            st["other"] = True                    # un tasto o un click mentre ⌘ è giù
        return event

    mask = 0
    for t in (Quartz.kCGEventFlagsChanged, Quartz.kCGEventKeyDown, Quartz.kCGEventLeftMouseDown,
              Quartz.kCGEventRightMouseDown, Quartz.kCGEventScrollWheel):
        mask |= Quartz.CGEventMaskBit(t)
    tap = Quartz.CGEventTapCreate(Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
                                  Quartz.kCGEventTapOptionListenOnly, mask, cb, None)
    if tap is None:
        log("⌘ destro non disponibile: serve il permesso Monitoraggio input per il Terminale")
        return
    Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetCurrent(),
                              Quartz.CFMachPortCreateRunLoopSource(None, tap, 0), Quartz.kCFRunLoopCommonModes)
    Quartz.CGEventTapEnable(tap, True)
    log("⌘ destro pronto: un tocco e parli")
    Quartz.CFRunLoopRun()


def main():
    log("carico whisper + wake word…")
    mlx_whisper.transcribe(np.zeros(SR, np.float32), path_or_hf_repo=WHISPER, language=LANG)
    wake = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
    global reflex
    try:
        if reflex and LANG == "it" and reflex.load():   # the reflex model is trained on Italian
            log("riflesso pronto")
        else:
            reflex = None
    except Exception as e:
        log("riflesso non caricato:", e)
        reflex = None
    threading.Thread(target=speak_watch, daemon=True).start()
    tapped = threading.Event()
    threading.Thread(target=cmd_tap_watch, args=(tapped,), daemon=True).start()
    floor = 200.0
    log("pronto, in ascolto su", PANE)
    with sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=CHUNK) as stream:
        last_check = 0.0
        while True:
            if time.time() - last_check > 2:
                if not tmux("has-session", "-t", PANE):
                    log("sessione chiusa, esco")
                    return
                last_check = time.time()
            chunk, _ = stream.read(CHUNK)
            chunk = chunk[:, 0]
            if not voice_speak.speaking():
                floor = 0.95 * floor + 0.05 * rms(chunk)  # rumore di fondo, solo quando lui tace
            score = wake.predict(chunk)["hey_jarvis"]
            tap = tapped.is_set()
            tapped.clear()
            if 0.2 < score < WAKE_THRESHOLD and not tap:
                log(f"quasi wake ({score:.2f})")  # per tarare la soglia sulla voce vera
            if (score < WAKE_THRESHOLD and not tap) or not voice_on():
                continue
            log("⌘ destro" if tap else f"wake ({score:.2f})")
            voice_speak.stop_all()  # barge-in
            beep()
            audio = record(stream, floor)
            text = transcribe(audio) if audio is not None else ""
            log("sentito:", repr(text))
            if audio is not None:
                save(audio, text)
            handle(text)
            wake.reset()
            if stream.read_available:
                stream.read(stream.read_available)  # butta l'audio accumulato mentre trascrivevo


if __name__ == "__main__":
    main()
