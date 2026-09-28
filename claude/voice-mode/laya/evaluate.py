"""Score a Laya checkpoint on the blind test set, the way voiced would use it.

    python evaluate.py <checkpoint dir or hub id> [data/blind_test.json]

Reports raw accuracy per question and the number that matters for a voice
reflex: with a confidence gate, how many commands fire correctly, how many are
handed to Claude (safe), and how many fire WRONG (the dangerous ones).
"""
import json
import statistics
import sys
import time
from collections import Counter, defaultdict

import laya

import reflex
import schema

HEAD = 512
MAXLEN = 1024
GATE = reflex.GATE
SLOT_INTENTS = {"web_search", "type_text"}


def slot_from(ws, ans):
    s, e = ans["slot_start"]["choice"], ans["slot_end"]["choice"]
    if s == "none" or e == "none":
        return ""
    a, b = int(s[1:]), int(e[1:])
    return " ".join(ws[a:b + 1]).rstrip(".?!,") if b >= a else ""


def conf(a):
    return a.get("answer_confidence", a.get("confidence", 0.0))


def norm(s):
    return " ".join(str(s).lower().strip(" .?!,:").split())


def decide(utt, ws, ans):
    """What voiced does: the reflex's own decision, as (action, target)."""
    a = reflex.decide(utt, ws, ans)
    if a is None:
        return ("claude", None)
    if a["intent"] == "open_app":
        return ("open_app", a["app"])
    if a["intent"] == "open_site":
        return ("open_site", a.get("site", "other"))
    if a["intent"] in SLOT_INTENTS:
        return (a["intent"], norm(a["text"]))
    return (a["intent"], None)


def expected(t):
    it = t["intent"]
    if it in ("ask", "none"):
        return ("claude", None)
    if it == "open_app":
        return ("open_app", t["app"]) if t["app"] != "none" else ("claude", None)
    if it == "open_site":
        if t["site"] == "other":
            return ("open_site", "other") if reflex.DOMAIN.search(t["utt"]) else ("claude", None)
        return ("open_site", t["site"])
    if it in SLOT_INTENTS:
        return (it, norm(t["slot"]))
    return (it, None)


def main():
    ckpt = sys.argv[1]
    test = json.load(open(sys.argv[2] if len(sys.argv) > 2 else "data/blind_test.json"))
    agent = laya.load(ckpt, device="mps")
    apps = list(schema.APPS)
    agent.predict({"utterance": "apri chrome"}, schema.questions("apri chrome", apps)[1], head_max_len=HEAD, max_len=MAXLEN)

    ok = Counter()
    lat, outcomes, per_intent = [], Counter(), defaultdict(Counter)
    wrong_fires = []
    for t in test:
        ws, qs = schema.questions(t["utt"], apps)
        t0 = time.perf_counter()
        ans = agent.predict({"utterance": t["utt"]}, qs, head_max_len=HEAD, max_len=MAXLEN)["answers"]
        lat.append((time.perf_counter() - t0) * 1000)
        ok["intent"] += ans["intent"]["choice"] == t["intent"]
        if t["intent"] == "open_app":
            ok["app_n"] += 1; ok["app"] += ans["app"]["choice"] == t["app"]
        if t["intent"] == "open_site":
            ok["site_n"] += 1; ok["site"] += ans["site"]["choice"] == t["site"]
        if t["intent"] in SLOT_INTENTS:
            ok["slot_n"] += 1; ok["slot"] += norm(slot_from(ws, ans)) == norm(t["slot"])
        got, want = decide(t["utt"], ws, ans), expected(t)
        if got == want:
            o = "correct"
        elif got[0] == "claude":
            o = "deferred"      # nothing fired: Claude handles it or nothing happens
        else:
            o = "WRONG_FIRE"
            wrong_fires.append((t["utt"], want, got, round(conf(ans["intent"]), 2)))
        outcomes[o] += 1
        per_intent[t["intent"]][o] += 1

    n = len(test)
    print(f"\n== {ckpt}  (n={n}, gate={GATE})")
    print(f"intent {ok['intent']}/{n} ({ok['intent']/n:.0%})  app {ok['app']}/{ok['app_n']}  site {ok['site']}/{ok['site_n']}  slot {ok['slot']}/{ok['slot_n']}")
    print(f"voiced outcome: correct {outcomes['correct']}  deferred {outcomes['deferred']}  WRONG_FIRE {outcomes['WRONG_FIRE']}")
    print(f"latency p50 {statistics.median(lat):.0f}ms  p95 {sorted(lat)[int(.95*n)-1]:.0f}ms")
    for it, c in sorted(per_intent.items()):
        print(f"  {it:12} " + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
    if wrong_fires:
        print("wrong fires:")
        for w in wrong_fires:
            print("  ", w)


if __name__ == "__main__":
    main()
