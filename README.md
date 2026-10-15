# hey-claude-code

Talk to Claude Code. Tap the right ⌘ key, say what you want, and your Mac does it.

"Open Spotify" or "search flights to Lisbon" run in about 150 ms without waking Claude at all. Real work goes to Claude Code with every skill you've installed, and it talks back to you while it works.

This is the setup I use every day on my MacBook. It's built around my Italian voice, but the language is a setting.

## What happens when you talk

```
tap right ⌘  (or say "hey jarvis")
      │
      ▼
records until you stop talking
      │
      ▼
whisper-large-v3-turbo transcribes it on your Mac (~0.4 s)
      │
      ▼
reflex layer (~120 ms): a simple Mac action it's sure about?
      ├── yes ──► runs it right away. Claude never sees it
      │
      ▼ no
typed into Claude Code ──► Claude works and speaks its 🔊 lines as it writes them
      │
      ▼
voice-guard hook: a short list of actions is never allowed by voice
```

## What's inside

- **`jv`**: starts Claude Code inside tmux with a voice daemon attached. Close the window and everything stops, microphone included.
- **Hands-free control**: "stop" silences it and "interrompi" presses Esc. When Claude waits for a permission, "sì" or "no" answers it.
- **The reflex layer**: 13 Mac actions decided by a small local model instead of Claude. Open an app or a site, search, dictate text, open or close a tab, change the volume, play/pause, take a screenshot.
- **voice-guard**: a Claude Code hook that blocks destructive actions when the request came from the microphone. More on this below, read it.

## Install

You need a Mac with Apple Silicon, [Claude Code](https://claude.com/claude-code) and about 2 GB of free disk.

```bash
git clone https://github.com/criscatalyst/hey-claude-code.git
cd hey-claude-code
./install.sh
```

The installer copies the files into `~/.claude` and `~/.local/bin`, builds a Python environment, registers the hooks (after backing up your `settings.json`) and runs the voice-guard tests. Run it again any time: it never overwrites your settings.

Then open a new Terminal and type `jv`.

macOS will ask for a few permissions the first time:

| Permission | Why |
|---|---|
| Microphone (Terminal) | so jv can hear you |
| Input Monitoring (Terminal) | the right-⌘ tap |
| Accessibility + Automation (Terminal) | "scrivi …" types into the app in front, tab commands talk to your browser |

For the Italian voice, download "Luca (Enhanced)" in System Settings › Accessibility › Spoken Content › System voice › Manage Voices.

## Talking to it

| You do | jv does |
|---|---|
| tap right ⌘ once (alone, quick) | beep, listens, stops when you stop talking |
| "hey jarvis" | same thing, hands free |
| "apri Spotify", "cerca meteo Napoli", "alza il volume" | reflex: done in ~150 ms, no Claude |
| "scrivimi uno script per un reel su…" | goes to Claude, you hear its progress out loud |
| "stop" / "basta" | silences the voice |
| click **■ zitto** in the tmux status bar, or tap right ⌘ | silences it while it's talking ("hey jarvis" is ignored while it speaks, so it never hears itself) |
| "interrompi" | Esc: stops Claude |
| "sì" / "no" while Claude waits for a permission | Enter / Esc |

⌘C, ⌘ + click or holding ⌘ never trigger it. Only a quick tap on its own does.

## Safety: voice-guard

A microphone doesn't know who's talking. Anyone in the room, or a video playing in the background, can say "hey jarvis". So when a request comes from the voice, `voice-guard.py` blocks this list before Claude can run it, whatever anyone says:

- deleting inside your vital folders, or a folder that contains one
- deleting more than 25 files in one command
- git that destroys work: `push --force`, `reset --hard`, `clean`, `checkout --`, `branch -D`
- reading secrets: `.env` files, SSH keys, credentials, keychain, environment dumps
- changing the guard itself or your Claude Code settings

Sending messages, creating automations and deleting ordinary files still work by voice. From the keyboard nothing changes. And a spoken "sì" never approves a red-list action, even when you typed the request yourself.

List your vital folders in `~/.claude/voice-guard.json`:

```json
{ "vital": ["~/Documents", "~/Projects/my-main-app"] }
```

Test it: `python3 ~/.claude/hooks/voice_guard_test.py` (54 cases). Every block is logged in `~/.claude/voice/guard.jsonl`.

Honest limit: it's a list, and a command nobody thought of can slip through. Keep real backups too. I run Syncthing with 30-day file versioning, so a deleted file is always one copy away.

## The reflex layer (Italian, optional)

Most of what you say to a voice assistant isn't work. It's "open Chrome". Sending that to a frontier model costs seconds. The reflex layer is a classifier, not a chatbot: it picks an intent, an app and the words to search from fixed lists, in one forward pass on your Mac's GPU. If it isn't sure, the sentence goes to Claude untouched.

The model is [Laya](https://github.com/NandhaKishorM/laya) (`laya-multilingual`, 322M params), fine-tuned on 3,000 synthetic Italian commands. You train it yourself, on your own Mac:

```bash
cd ~/.claude/voice-mode/laya && ./train-reflex.sh
```

On my M5 with 16 GB it took 72 minutes. Keep the Mac plugged in with the lid open. On a 150-command blind test written separately from the training data:

| | base Laya | fine-tuned + rules |
|---|---|---|
| right intent | 51% | 95% |
| wrong action actually fired | 29 | 1 |
| handed to Claude instead | 57 | 9 |

Two things made the difference beyond training. App names are matched by spelling in code, so Whisper's "spotifai" still opens Spotify. The text to search or type is cut in code after a known verb, because the model's boundary word wobbled by one.

A sentence that isn't all simple actions goes to Claude whole. "Apri Chrome e dimmi cosa vedi" never opens Chrome and then sends half a sentence. Turn the reflex off with `touch ~/.claude/voice/reflex.off`. Every decision is logged in `~/.claude/voice/reflex.jsonl`, and your real sentences there are the best data for the next training run.

Another language? Rewrite the templates in `gen_data.py` and the verbs in `reflex.py`, then train. Until then jv just skips the reflex and sends everything to Claude.

## Settings

`~/.claude/voice-mode/settings.json`:

```json
{
  "language": "it",
  "tts_voice": "Luca (Enhanced)",
  "whisper_prompt": "Claude, Spotify, WhatsApp, CapCut, the names you say often"
}
```

`language` is a Whisper code (`en`, `es`, `fr`…). Claude's spoken lines follow it too. `whisper_prompt` is optional: the names in it get transcribed right far more often.

## Known limits

- Two `jv` windows open at once both react to the wake word and the tap.
- The control words ("stop", "interrompi", "sì") are Italian. They're sets at the top of `voiced.py`.
- Apple Silicon only: speech runs on MLX and the reflex on PyTorch's Metal backend.
- The "hey jarvis" wake word model is non-commercial. See [THIRD_PARTY.md](THIRD_PARTY.md) before using this for a client. The ⌘ tap doesn't need it.

## Credits

The reflex idea comes from taking apart Nūs Companion, which does the same with TypeSafe's hosted Jev model. Laya made it possible to run it locally for free. Wake word by [openWakeWord](https://github.com/dscripka/openWakeWord), speech to text by [mlx-whisper](https://github.com/ml-explore/mlx-examples).

---

I build systems like this for creators and founders in [Velocity Lab](https://velocity-lab.vercel.app?utm_source=github&utm_medium=readme&utm_campaign=hey-claude-code).

Follow [@criscatalyst](https://www.instagram.com/criscatalyst) for daily AI systems to grow your business.
