"""The reflex registry for jv: what a voice command may be, as Laya questions.

One source of truth for the training data, the evaluation and (later) voiced.
Laya never generates text: it picks an intent, an app or a site from a list,
and the first and last word of any free text out of the words actually said.
"""

INTENTS = {
    "open_app": "aprire, avviare o passare a un'applicazione del Mac per nome",
    "open_site": "aprire un sito web preciso nel browser (youtube, gmail, instagram)",
    "web_search": "cercare qualcosa sul web o su google",
    "type_text": "dettare parole esatte da scrivere nel campo o nella finestra attiva",
    "new_tab": "aprire una nuova scheda vuota del browser",
    "close_tab": "chiudere la scheda o la finestra corrente",
    "volume_up": "alzare il volume",
    "volume_down": "abbassare il volume",
    "mute": "togliere o rimettere l'audio",
    "play_pause": "mettere in pausa, riprendere o far partire la musica o un video",
    "screenshot": "fare uno screenshot dello schermo",
    "ask": "una domanda o un lavoro per l'assistente AI: scrivere contenuti, analizzare, controllare, rispondere",
    "none": "niente da fare: riempitivo, chiacchiera, negazione, frase interrotta senza comando",
}

# Spoken names people use on this Mac. key -> (app name, aliases).
APPS = {
    "chrome": ("Google Chrome", "chrome, il browser"),
    "safari": ("Safari", "safari"),
    "finder": ("Finder", "finder, i file, le cartelle"),
    "notes": ("Notes", "note, l'app note, appunti"),
    "terminal": ("Terminal", "terminale, la shell, riga di comando"),
    "spotify": ("Spotify", "spotify, la musica"),
    "whatsapp": ("WhatsApp", "whatsapp"),
    "calendar": ("Calendar", "calendario"),
    "mail": ("Mail", "mail, la posta, email"),
    "capcut": ("CapCut", "capcut, il montaggio video"),
    "obsidian": ("Obsidian", "obsidian, il vault, la wiki"),
    "settings": ("System Settings", "impostazioni, preferenze di sistema"),
    "notion": ("Notion", "notion"),
    "discord": ("Discord", "discord"),
    "claude": ("Claude", "l'app di claude"),
    "canva": ("Canva", "canva"),
    "obs": ("OBS", "obs, registrazione schermo"),
    "zoom": ("zoom.us", "zoom, videochiamata"),
    "excel": ("Microsoft Excel", "excel, foglio di calcolo"),
    "word": ("Microsoft Word", "word, documento word"),
    "messages": ("Messages", "messaggi, imessage, sms"),
    "photos": ("Photos", "foto, la galleria"),
    "reminders": ("Reminders", "promemoria"),
    "calculator": ("Calculator", "calcolatrice"),
    "preview": ("Preview", "anteprima"),
    "music": ("Music", "apple music, l'app musica"),
    "facetime": ("FaceTime", "facetime"),
    "maps": ("Maps", "mappe"),
    "fathom": ("Fathom", "fathom"),
    "lmstudio": ("LM Studio", "lm studio"),
    "appstore": ("App Store", "app store"),
    "voicememos": ("VoiceMemos", "memo vocali, registratore"),
    "quicktime": ("QuickTime Player", "quicktime"),
    "textedit": ("TextEdit", "textedit, editor di testo"),
    "pages": ("Pages", "pages"),
}

SITES = {
    "youtube": ("https://www.youtube.com", "YouTube"),
    "gmail": ("https://mail.google.com", "Gmail, la casella email nel browser"),
    "instagram": ("https://www.instagram.com", "Instagram"),
    "tiktok": ("https://www.tiktok.com", "TikTok"),
    "x": ("https://x.com", "X, ex Twitter"),
    "linkedin": ("https://www.linkedin.com", "LinkedIn"),
    "github": ("https://github.com", "GitHub"),
    "claude_web": ("https://claude.ai", "claude punto ai, Claude nel browser"),
    "chatgpt": ("https://chatgpt.com", "ChatGPT"),
    "gcal": ("https://calendar.google.com", "Google Calendar"),
    "drive": ("https://drive.google.com", "Google Drive"),
    "whop": ("https://whop.com", "Whop"),
    "vercel": ("https://vercel.com", "Vercel"),
    "reddit": ("https://www.reddit.com", "Reddit"),
    "amazon": ("https://www.amazon.it", "Amazon"),
}

NONE_APP = "nessuna applicazione nominata, oppure l'app nominata non è in questa lista"
NONE_SITE = "nessun sito nominato"
OTHER_SITE = "è nominato un sito che non è in questa lista"
NONE_WORD = "non c'è testo libero da cercare o scrivere"

MAX_WORDS = 40


def words(text):
    return str(text or "").split()[:MAX_WORDS]


def app_criteria(app_keys):
    c = {"none": NONE_APP}
    for k in app_keys:
        name, alias = APPS[k]
        c[k] = "%s (%s)" % (name, alias)
    return c


def site_criteria():
    c = {"none": NONE_SITE, "other": OTHER_SITE}
    for k, (_, desc) in SITES.items():
        c[k] = desc
    return c


def questions(utterance, app_keys=None):
    """The five questions asked about one utterance, in one forward pass each."""
    ws = words(utterance)
    wc = {"none": NONE_WORD}
    for i, w in enumerate(ws):
        wc["w%d" % i] = 'parola %d: "%s"' % (i, w)
    return ws, {
        "intent": {"type": "choice", "instructions": "Cosa vuole che faccia il computer, adesso, chi parla in `utterance`?", "criteria": INTENTS},
        "app": {"type": "choice", "instructions": "Quale applicazione chiede di aprire `utterance`?", "criteria": app_criteria(app_keys or list(APPS))},
        "site": {"type": "choice", "instructions": "Quale sito web chiede di aprire `utterance`?", "criteria": site_criteria()},
        "slot_start": {"type": "choice", "instructions": "`utterance` può contenere un testo libero da cercare o da scrivere. Qual è la PRIMA parola di quel testo, esclusi i comandi intorno?", "criteria": wc},
        "slot_end": {"type": "choice", "instructions": "`utterance` può contenere un testo libero da cercare o da scrivere. Qual è l'ULTIMA parola di quel testo?", "criteria": wc},
    }
