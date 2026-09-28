# Third-party pieces and their licenses

This repo's own code is MIT (see `LICENSE`). It downloads and runs other people's work, each
under its own license. Read this before you use jv for a client or a paid product.

| Piece | What it does here | License |
|---|---|---|
| [openWakeWord](https://github.com/dscripka/openWakeWord) (library) | listens for the wake word | Apache 2.0 |
| `hey_jarvis` wake word model (downloaded by the installer) | the "hey jarvis" trigger | **CC BY-NC-SA 4.0: non-commercial only** |
| [mlx-whisper](https://github.com/ml-explore/mlx-examples) + `whisper-large-v3-turbo` | speech to text, on your Mac | MIT |
| [Laya](https://github.com/NandhaKishorM/laya) (`laya-multilingual` checkpoint) | the reflex layer you fine-tune | Apache 2.0 |
| [PyObjC](https://github.com/ronaldoussoren/pyobjc) | the right-⌘ tap | MIT |

**Commercial use:** the "hey jarvis" model is the one piece you can't use commercially. The right-⌘
tap does the same job without it. To remove the wake word entirely, delete the `wake` lines in
`claude/voice-mode/voiced.py` or train your own wake word with openWakeWord's training notebook.
