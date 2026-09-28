"""Synthetic Italian voice commands for jv, labelled by construction.

Every utterance is built from a template whose parts are known, so the intent,
the app/site and the exact words of the free text are exact, not guessed.
Output: data/train.jsonl, one {"utt","intent","app","site","slot","apps"} per line.
"""
import json
import random
import sys
from pathlib import Path

from schema import APPS, SITES

R = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 7)
N_TOTAL = int(sys.argv[1]) if len(sys.argv) > 1 else 3000

# ---------------------------------------------------------------- spoken names
APP_SAID = {
    "chrome": ["chrome", "google chrome", "il browser", "crome"],
    "safari": ["safari"],
    "finder": ["il finder", "finder", "i file", "le cartelle"],
    "notes": ["note", "le note", "l'app note", "appunti", "l'app delle note"],
    "terminal": ["il terminale", "terminale", "la shell", "terminal"],
    "spotify": ["spotify", "spotifai", "spoti"],
    "whatsapp": ["whatsapp", "whats app", "uotsap", "wazzap"],
    "calendar": ["il calendario", "calendario", "calendar"],
    "mail": ["mail", "la posta", "l'app mail", "apple mail"],
    "capcut": ["capcut", "cap cut", "kapkat"],
    "obsidian": ["obsidian", "obsidien", "il vault", "la wiki"],
    "settings": ["le impostazioni", "impostazioni", "le preferenze di sistema", "impostazioni di sistema"],
    "notion": ["notion", "noscion"],
    "discord": ["discord", "discordo"],
    "claude": ["claude", "l'app di claude", "cloud desktop", "clod"],
    "canva": ["canva", "canvas"],
    "obs": ["obs", "o b s", "obs studio"],
    "zoom": ["zoom"],
    "excel": ["excel", "il foglio di calcolo", "ecsel"],
    "word": ["word", "microsoft word"],
    "messages": ["messaggi", "i messaggi", "imessage"],
    "photos": ["foto", "le foto", "la galleria", "l'app foto"],
    "reminders": ["promemoria", "i promemoria"],
    "calculator": ["la calcolatrice", "calcolatrice"],
    "preview": ["anteprima", "preview"],
    "music": ["apple music", "l'app musica", "musica di apple"],
    "facetime": ["facetime", "face time"],
    "maps": ["mappe", "le mappe", "apple maps"],
    "fathom": ["fathom", "fatom"],
    "lmstudio": ["lm studio", "elle emme studio"],
    "appstore": ["l'app store", "app store"],
    "voicememos": ["memo vocali", "i memo vocali", "il registratore"],
    "quicktime": ["quicktime", "quick time"],
    "textedit": ["textedit", "text edit", "l'editor di testo"],
    "pages": ["pages"],
}
UNKNOWN_APPS = ["figma", "photoshop", "slack", "telegram", "premiere", "final cut", "davinci", "lightroom",
                "xcode", "cursor", "trello", "teams", "skype", "illustrator", "after effects", "logic pro",
                "garageband", "keynote", "firefox", "brave", "arc", "vlc", "steam", "1password"]
SITE_SAID = {
    "youtube": ["youtube", "iutub", "you tube"],
    "gmail": ["gmail", "gi mail", "la mail di google"],
    "instagram": ["instagram", "insta", "ig"],
    "tiktok": ["tiktok", "tik tok"],
    "x": ["x", "twitter", "x punto com"],
    "linkedin": ["linkedin", "linkedin punto com", "linkdin"],
    "github": ["github", "git hub"],
    "claude_web": ["claude punto ai", "claude sul browser", "claude.ai"],
    "chatgpt": ["chatgpt", "chat gpt", "ciat gpt"],
    "gcal": ["google calendar", "il calendario di google"],
    "drive": ["google drive", "drive"],
    "whop": ["whop", "uop", "whop punto com"],
    "vercel": ["vercel", "versel"],
    "reddit": ["reddit", "reddit punto com"],
    "amazon": ["amazon", "amazon punto it"],
}
OTHER_SITES = ["booking punto com", "wikipedia", "airbnb", "netflix", "twitch", "figma punto com",
               "il sito della posta", "ryanair punto com", "subito punto it", "corriere punto it",
               "producthunt", "hacker news", "notion punto so", "zalando", "ebay"]

# ---------------------------------------------------------------- phrasing parts
LEAD = ["", "", "", "", "ehm ", "allora ", "ok ", "dai ", "senti ", "ok allora ", "jarvis ", "ehi ", "aspetta ", "ecco "]
POLITE = ["", "", "", "puoi ", "mi puoi ", "potresti ", "per favore ", "riesci a ", "ti chiedo di "]
TAIL = ["", "", "", "", " per favore", " grazie", " dai", " subito", " al volo", " un attimo", " adesso", " perfavore"]

OPEN_APP_V = ["apri", "aprimi", "apri l'app", "apri l'applicazione", "avvia", "lancia", "fammi vedere", "vai su",
              "passa a", "portami su", "mi apri", "apriamo", "tira su", "metti su", "voglio", "mostrami", "torna su",
              "passami su", "fai partire", "apri un attimo"]
OPEN_APP_POLITE_V = ["aprire", "aprirmi", "avviare", "lanciare", "farmi vedere", "passare a", "portarmi su", "aprirmi un attimo"]
OPEN_SITE_V = ["apri", "vai su", "aprimi", "portami su", "apri il sito di", "vai sul sito di", "apri la pagina di",
               "fammi vedere", "mettimi", "carica", "entra su", "apriamo"]
OPEN_SITE_TAIL = ["", "", "", " nel browser", " su chrome", " in una nuova scheda", " sul browser"]
SEARCH_V = ["cerca", "cercami", "cerca su google", "googla", "fai una ricerca su", "cerca online", "cerca in rete",
            "cerca sul web", "mi cerchi", "trova su google", "cerca un po'", "vai su google e cerca", "ricerca",
            "fammi una ricerca su", "cerca velocemente", "googlami"]
SEARCH_POLITE_V = ["cercare", "cercarmi", "fare una ricerca su", "googlare"]
SEARCH_TAIL = ["", "", "", "", " su google", " online", " sul web", " in rete", " su internet"]
TYPE_V = ["scrivi", "digita", "detta", "scrivi testuale", "scrivi esattamente", "batti", "inserisci il testo",
          "metti scritto", "scrivi qui", "digitami", "scrivici", "scrivi:", "digita:", "dettato", "trascrivi"]
TYPE_POLITE_V = ["scrivere", "digitare", "scrivermi qui"]
TYPE_TAIL = ["", "", "", "", "", " nel campo", " qui", " nella chat", " e basta", " nel messaggio"]

QUERIES = [
    "ricetta carbonara", "prezzo macbook air m5", "meteo milano domani", "come si usa obsidian",
    "migliori microfoni per reel", "orari treni napoli roma", "cos'è il fine tuning", "risultati serie a",
    "come aprire una partita iva", "costo abbonamento claude max", "migliore luce per video verticali",
    "apri un conto business online", "chrome estensioni per creator", "whisper large v3 turbo",
    "remotion best practices", "come funziona boosend", "laya modello open source", "ristoranti sushi vicino a me",
    "tassi mutuo fisso ottobre", "come fare un carosello instagram", "hook virali per reel", "stipendio medio growth engineer",
    "voli per lisbona", "farmacia aperta adesso", "spotify wrapped 2026", "nuovo iphone uscita",
    "come si scrive una email di follow up", "traduzione di leverage", "significato di churn", "tiktok creator fund italia",
    "mac m5 temperatura alta", "whop commissioni", "vercel prezzi pro", "come rinnovare il passaporto",
    "palestra aperta domenica", "prezzo bitcoin oggi", "the batch newsletter", "karpathy nano gpt",
    "come si apre un file json", "tutorial capcut transizioni", "installare homebrew", "python venv errore ssl",
    "quanto costa un reel sponsorizzato", "calendario lezioni università", "orario apertura poste", "notizie ai di oggi",
    "obs registrare schermo e webcam", "sincronizzare due mac", "syncthing conflitti", "migliori cuffie bluetooth",
    "google calendar condividere", "linkedin post virali", "come crescere su threads", "numero verde enel",
    "ricetta tiramisù senza uova", "film stasera in tv", "chi ha vinto ieri sera", "distanza napoli milano",
    "cambio euro dollaro", "come funziona la wake word", "openwakeword italiano", "tmux send keys",
    "apple m5 benchmark", "creatina effetti", "piano alimentare massa", "mlx whisper velocità",
]
TYPE_TEXTS = [
    "ciao a tutti", "ok ci vediamo alle cinque", "grazie mille", "arrivo tra dieci minuti", "perfetto ci sentiamo dopo",
    "ottimo lavoro ragazzi", "sì va bene", "domani alle dieci", "buongiorno", "a che ora ci vediamo",
    "fatto", "ci penso e ti dico", "mandami il link", "non riesco oggi", "top grazie", "hello world",
    "test uno due tre", "prova microfono", "ti chiamo più tardi", "tutto ok", "sto arrivando",
    "ok per me", "bella idea", "ricordami di comprare il latte", "apri il file domani", "cerca di arrivare presto",
    "sono in call", "ci aggiorniamo lunedì", "la riunione è spostata", "scrivo io a marco", "a dopo",
    "ho finito il montaggio", "il reel è pronto", "controlla la mail", "grazie per il feedback", "ci sta",
    "buona serata", "ok chiudo", "nuovo progetto", "lista della spesa", "idee per reel", "titolo provvisorio",
]
ASK_TEMPLATES = [
    "scrivimi uno script per un reel su {t}", "scrivi una mail a {p} per {g}", "scrivimi una caption per il reel su {t}",
    "fammi un carosello su {t}", "che cosa ho in calendario {d}", "cosa ho da fare {d}", "controlla le email dei brand",
    "controlla le mail e dimmi se c'è qualcosa di urgente", "come si apre il terminale", "come si fa uno screenshot sul mac",
    "com'è andato l'ultimo reel", "analizza il repo {r}", "sistemami il bug della dashboard", "fammi un riassunto di {t}",
    "dimmi cosa c'è di nuovo su {t}", "ricordami di {g} {d}", "prepara la risposta a {p}", "rispondi a {p} su whatsapp dicendo che arrivo",
    "trova il video dove parlo di {t}", "cerca nella wiki {t}", "cerca nelle mie email la fattura di {p}",
    "quanti follower ho guadagnato {d}", "fai il backup", "lancia la batch di video", "genera tre hook su {t}",
    "dammi un'idea per un reel", "cosa ne pensi di {t}", "spiegami {t}", "traducimi in inglese la caption",
    "come faccio ad aprire obsidian dal terminale", "perché chrome è così lento", "quale app uso per montare i video",
    "puoi controllare se il bot telegram è attivo", "dimmi il meteo di domani", "quanto manca alla call con {p}",
    "sposta la call con {p} a {d}", "manda un messaggio a {p}", "crea un evento {d} alle cinque", "scrivi un post per linkedin su {t}",
    "correggimi il testo che ho scritto", "leggimi l'ultima mail di {p}", "a che punto è il task di prima",
    "riassumimi questa pagina", "cosa c'è in questa schermata", "migliora questo script", "fammi una scaletta per il video su {t}",
    "qual è il prossimo step della roadmap", "aggiorna la roadmap", "pubblica il carosello di oggi", "come sta andando whop questo mese",
    "apri una issue su github per {g}", "committa le modifiche", "fai partire i test", "chi mi ha scritto oggi",
]
TOPICS = ["le automazioni", "claude code", "il fine tuning", "laya", "velocity lab", "la content factory", "i brand deal",
          "whisper", "gli agenti ai", "la growth", "il personal branding", "remotion", "i caroselli", "il mio corso",
          "jarvis", "gli hook", "la produttività", "mission control", "il dual mac", "notion ai"]
PEOPLE = ["marco", "giulia", "luca", "il cliente", "sara", "andrea", "il brand", "mamma", "francesco", "chiara"]
GOALS = ["chiedere un aggiornamento", "spostare la call", "mandare il preventivo", "ringraziarlo", "chiedere il contratto",
         "chiamare il commercialista", "pagare la bolletta", "sistemare il sito", "confermare la collaborazione"]
DAYS = ["oggi", "domani", "stasera", "lunedì", "questa settimana", "venerdì", "dopodomani", "stamattina"]
REPOS = ["video factory", "mission control", "jarvis", "la dashboard", "content mining"]

NONE_TEXTS = [
    "allora dunque", "ok aspetta", "sì sì va bene", "no niente", "grazie", "lascia stare", "niente scusa", "ok perfetto grazie",
    "va bene così", "aspetta un attimo", "mmm", "vediamo", "no no", "ah ok", "fantastico", "bravo", "ok ci sono",
    "sì ci sentiamo dopo ciao", "mamma arrivo tra poco", "sì sì amore arrivo", "pronto? sì dimmi", "no guarda non posso adesso",
    "ma dai davvero", "che ore sono ah no lascia stare", "niente niente", "scusa stavo parlando con un'altra persona",
    "ok allora dopo lo facciamo", "e poi", "quindi", "comunque", "cioè", "fermo così", "sì esatto", "ho capito", "grazie jarvis",
    "no scusa non era per te", "ok basta così per ora", "ci penso io", "dopo", "tra poco",
]
NEG_TEMPLATES = ["non aprire {a}", "no non aprire {a}", "lascia stare {a}", "non serve che apri {a}", "non mi aprire {a}",
                 "no aspetta non aprire {a}", "evita di aprire {a}", "non cercare {q}", "no non cercare niente",
                 "non scrivere niente", "non ti ho chiesto di aprire {a}", "non adesso {a}", "no, {a} no",
                 "ho detto di non aprire {a}", "non chiudere la scheda", "non alzare il volume", "non fare lo screenshot"]
FRAGMENTS = ["apri il", "apri la", "cerca", "scrivi", "vai su", "apri", "e poi apri", "aprimi il", "cerca su",
             "digita", "fammi vedere il", "allora apri", "puoi aprire", "ok vai su"]

SIMPLE = {
    "new_tab": ["apri una nuova scheda", "nuova scheda", "apri un nuovo tab", "nuovo tab", "aprimi un'altra scheda",
                "apri una scheda vuota", "fammi una nuova scheda", "un'altra scheda", "apri un tab nuovo", "scheda nuova",
                "aggiungi una scheda", "apri una tab"],
    "close_tab": ["chiudi la scheda", "chiudi questo tab", "chiudila", "chiudi questa pagina", "chiudi la finestra",
                  "chiudimi questa scheda", "chiudi il tab", "chiudi questa", "togli questa scheda", "chiudi tutto questo tab",
                  "chiudi la tab", "chiudi questa finestra"],
    "volume_up": ["alza il volume", "alza un po'", "più forte", "volume su", "alza l'audio", "metti più alto",
                  "aumenta il volume", "alza la musica", "un po' più forte", "alzalo", "sentiamo più forte", "volume più alto"],
    "volume_down": ["abbassa il volume", "più piano", "abbassa un po'", "volume giù", "diminuisci il volume",
                    "abbassa la musica", "abbassalo", "un po' più piano", "metti più basso", "abbassa l'audio", "volume più basso",
                    "troppo forte abbassa"],
    "mute": ["muto", "togli l'audio", "silenzia", "metti in muto", "rimetti l'audio", "disattiva l'audio",
             "togli il volume", "audio off", "riattiva l'audio", "silenzia il mac", "muta tutto", "togli l'audio al mac"],
    "play_pause": ["pausa", "metti in pausa", "fai ripartire la musica", "riprendi", "play", "stoppa la musica",
                   "fai partire la musica", "rimetti la canzone", "ferma il video", "metti play", "pausa la musica",
                   "fai ripartire il video", "stop musica", "riprendi la riproduzione"],
    "screenshot": ["fai uno screenshot", "screenshot", "cattura lo schermo", "fammi uno screen", "fotografa lo schermo",
                   "fai una schermata", "fai uno screen", "cattura la schermata", "salva uno screenshot", "screenshotta",
                   "fai una foto allo schermo", "scatta uno screenshot"],
}


def dress(core, polite_form=None):
    """Wrap a core command in lead filler, politeness and tail, Whisper-style."""
    lead = R.choice(LEAD)
    if polite_form and R.random() < 0.3:
        p = R.choice(["puoi ", "mi puoi ", "potresti ", "riesci a ", "per favore puoi "])
        core = p + polite_form
    elif R.random() < 0.15:
        core = R.choice(["per favore ", "dai "]) + core
    text = lead + core + R.choice(TAIL)
    return whisperize(text)


def whisperize(text):
    text = " ".join(text.split())
    if R.random() < 0.55:
        text = text[:1].upper() + text[1:]
    if R.random() < 0.4:
        text += R.choice([".", ".", "?", "!"]) if not text.endswith((".", "?", "!")) else ""
    if R.random() < 0.08:
        text = text.replace(" ", ", ", 1)
    return text


def with_slot(prefix, payload, suffix, polite_prefix=None):
    """Build an utterance where the payload words are known exactly."""
    lead = R.choice(LEAD)
    if polite_prefix and R.random() < 0.25:
        prefix = R.choice(["puoi ", "mi puoi ", "potresti ", "per favore puoi "]) + polite_prefix
    before = (lead + prefix).split()
    mid = payload.split()
    after = (suffix + R.choice(TAIL)).split()
    ws = before + mid + after
    cap = R.random() < 0.55
    end = R.choice(["", "", "."])
    if cap:
        ws[0] = ws[0][:1].upper() + ws[0][1:]
    if end:
        ws[-1] += end
    slot_words = ws[len(before):len(before) + len(mid)]
    return " ".join(ws), " ".join(slot_words).rstrip(".")


def catalog(target=None, drop_target=False):
    keys = list(APPS)
    n = R.randint(12, len(keys))
    pick = R.sample(keys, n)
    if target and not drop_target and target not in pick:
        pick[0] = target
    if drop_target and target in pick:
        pick.remove(target)
    R.shuffle(pick)
    return pick


def ex(utt, intent, app="none", site="none", slot="", apps=None):
    return {"utt": utt, "intent": intent, "app": app, "site": site, "slot": slot, "apps": apps or catalog()}


def gen_open_app():
    r = R.random()
    if r < 0.12:  # app not installed / not in catalog
        name = R.choice(UNKNOWN_APPS)
        v = R.choice(OPEN_APP_V)
        return ex(dress(v + " " + name, "aprire " + name), "open_app", "none", apps=catalog())
    key = R.choice(list(APPS))
    said = R.choice(APP_SAID[key])
    drop = r < 0.18
    v = R.choice(OPEN_APP_V)
    pv = R.choice(OPEN_APP_POLITE_V)
    return ex(dress(v + " " + said, pv + " " + said), "open_app", "none" if drop else key, apps=catalog(key, drop))


def gen_open_site():
    v = R.choice(OPEN_SITE_V)
    tail = R.choice(OPEN_SITE_TAIL)
    if R.random() < 0.15:
        name = R.choice(OTHER_SITES)
        return ex(dress(v + " " + name + tail), "open_site", site="other")
    key = R.choice(list(SITES))
    said = R.choice(SITE_SAID[key])
    return ex(dress(v + " " + said + tail), "open_site", site=key)


def gen_search():
    q = R.choice(QUERIES)
    v = R.choice(SEARCH_V)
    tail = R.choice(SEARCH_TAIL) if "google" not in v else ""
    utt, slot = with_slot(v + " ", q, tail, R.choice(SEARCH_POLITE_V) + " ")
    return ex(utt, "web_search", slot=slot)


def gen_type():
    t = R.choice(TYPE_TEXTS)
    v = R.choice(TYPE_V)
    utt, slot = with_slot(v + " ", t, R.choice(TYPE_TAIL), R.choice(TYPE_POLITE_V) + " ")
    return ex(utt, "type_text", slot=slot)


def gen_ask():
    t = R.choice(ASK_TEMPLATES).format(t=R.choice(TOPICS), p=R.choice(PEOPLE), g=R.choice(GOALS), d=R.choice(DAYS), r=R.choice(REPOS))
    return ex(dress(t), "ask")


def gen_none():
    r = R.random()
    if r < 0.4:
        return ex(whisperize(R.choice(NONE_TEXTS)), "none")
    if r < 0.8:
        a = R.choice(APP_SAID[R.choice(list(APPS))] + [R.choice(SITE_SAID[k]) for k in SITES])
        return ex(whisperize(R.choice(NEG_TEMPLATES).format(a=a, q=R.choice(QUERIES))), "none")
    return ex(whisperize(R.choice(LEAD) + R.choice(FRAGMENTS)), "none")


def gen_simple():
    intent = R.choice(list(SIMPLE))
    return ex(dress(R.choice(SIMPLE[intent])), intent)


MIX = [(gen_open_app, 0.20), (gen_open_site, 0.10), (gen_search, 0.15), (gen_type, 0.10),
       (gen_ask, 0.15), (gen_none, 0.12), (gen_simple, 0.18)]


def main():
    out = Path(__file__).parent / "data"
    out.mkdir(exist_ok=True)
    seen, rows = set(), []
    fns, weights = zip(*MIX)
    tries = 0
    while len(rows) < N_TOTAL and tries < N_TOTAL * 20:
        tries += 1
        row = R.choices(fns, weights)[0]()
        k = (row["utt"].lower().strip(" .?!"), row["intent"])
        if k in seen:
            continue
        seen.add(k)
        rows.append(row)
    path = out / "train.jsonl"
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(len(rows), "rows ->", path)
    print(Counter(r["intent"] for r in rows).most_common())


if __name__ == "__main__":
    main()
