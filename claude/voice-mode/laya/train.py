"""Fine-tune laya-multilingual on jv's Italian commands, on this Mac's GPU (MPS).

    python train.py [epochs]

Single-device port of the official Kaggle recipe (notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb):
RLCD = GRPO-style policy gradient over noisy logits rewarded by proper scoring
rules + full-weight soft cross-entropy, AdamW with separate encoder/head LRs,
cosine schedule, temperature calibration on a held-out slice. No DDP, fp32.
Items are encoded with the agent's own _encode_state, so training and inference
see byte-identical sequences.
"""
import json
import os
import random
import shutil
import sys
import time

import torch
from safetensors.torch import save_file

import laya
from laya.common import proper_reward

import schema

BASE = "convaiinnovations/laya-multilingual"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "checkpoints", "jv-reflex")
HEAD, MAXLEN = 512, 1024
SMOOTH = 0.1                 # soft targets: 0.9 on the gold option, 0.1 spread over the rest
KEEP_OFFTOPIC = 0.35         # app/site/slot questions whose answer is "none" are sub-sampled
EPOCHS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
MICRO_BATCH, GRAD_ACCUM = 4, 8   # 16 GB shared with the rest of the Mac: batch 8 thrashed swap
GROUP_SIZE = 4
LR_ENCODER, LR_HEAD = 2.5e-5, 1.0e-4
SIGMA_START, SIGMA_END = 0.4, 0.1
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def soft(keys, gold):
    k = len(keys)
    t = [SMOOTH / (k - 1)] * k
    t[keys.index(gold)] = 1.0 - SMOOTH
    return t


def slot_bounds(ws, slot):
    if not slot:
        return "none", "none"
    sw = [w.rstrip(".?!,:").lower() for w in slot.split()]
    clean = [w.rstrip(".?!,:").lower() for w in ws]
    for i in range(len(clean) - len(sw) + 1):
        if clean[i:i + len(sw)] == sw:
            return "w%d" % i, "w%d" % (i + len(sw) - 1)
    raise ValueError("slot not found: %r in %r" % (slot, ws))


def build_items(agent, rows, rng):
    items = []
    for r in rows:
        ws, qs = schema.questions(r["utt"], r["apps"])
        s0, s1 = slot_bounds(ws, r["slot"])
        gold = {"intent": r["intent"], "app": r["app"], "site": r["site"], "slot_start": s0, "slot_end": s1}
        keep = ["intent"]
        for qid in ("app", "site", "slot_start", "slot_end"):
            if gold[qid] != "none" or rng.random() < KEEP_OFFTOPIC:
                keep.append(qid)
        internal = {q: agent._to_internal(qs[q]) for q in keep}
        enc = agent._encode_state({"utterance": r["utt"]}, keep, internal, MAXLEN, HEAD)
        for qid, it in zip(keep, enc):
            keys = list(qs[qid]["criteria"].keys())
            t = soft(keys, gold[qid])
            assert len(it["markers"]) == len(keys), (qid, r["utt"])
            items.append({"ids": it["ids"], "markers": it["markers"], "qtype": it["qtype"], "target": t, "label": t.index(max(t))})
    return items


def collate(items, pad_id):
    n, L = len(items), max(len(it["ids"]) for it in items)
    kmax = max(len(it["markers"]) for it in items)
    ids = torch.full((n, L), pad_id, dtype=torch.long)
    att = torch.zeros((n, L), dtype=torch.long)
    mpos = torch.zeros((n, kmax), dtype=torch.long)
    mmask = torch.zeros((n, kmax), dtype=torch.bool)
    target = torch.zeros((n, kmax), dtype=torch.float32)
    for i, it in enumerate(items):
        ids[i, :len(it["ids"])] = torch.tensor(it["ids"])
        att[i, :len(it["ids"])] = 1
        k = len(it["markers"])
        mpos[i, :k] = torch.tensor(it["markers"])
        mmask[i, :k] = True
        target[i, :k] = torch.tensor(it["target"])
    return ids, att, mpos, mmask, target, torch.tensor([it["qtype"] for it in items])


def forward(model, batch):
    ids, att, mpos, mmask, _, qt = batch
    return model(ids.to(DEVICE), att.to(DEVICE), mpos.to(DEVICE), mmask.to(DEVICE), qt.to(DEVICE))


def fit_temp(sel):
    if len(sel) < 10:
        return 1.0
    kmax = max(len(z) for z, _ in sel)
    Z = torch.full((len(sel), kmax), -1e4)
    T = torch.zeros((len(sel), kmax))
    for i, (z, t) in enumerate(sel):
        Z[i, :len(z)] = torch.tensor(z)
        T[i, :len(t)] = torch.tensor(t)
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = -(T * torch.log_softmax(Z / log_t.exp(), -1)).sum(-1).mean()
        loss.backward()
        return loss
    opt.step(closure)
    return float(torch.clamp(log_t.exp(), 0.1, 10.0).item())


def main():
    rng = random.Random(20260928)
    agent = laya.load(BASE, device="cpu")
    tok, model = agent.tok, agent.model
    rows = [json.loads(l) for l in open(os.path.join(HERE, "data", "train.jsonl"))]
    t0 = time.time()
    items = build_items(agent, rows, rng)
    print(f"{len(rows)} utterances -> {len(items)} items ({time.time()-t0:.0f}s)", flush=True)

    order = list(range(len(items)))
    rng.shuffle(order)
    n_cal = min(400, len(items) // 10)
    calib = [items[i] for i in order[:n_cal]]
    train = [items[i] for i in order[n_cal:]]

    model.encoder.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.head_checkpointing = True
    model.to(DEVICE).train()
    # The 256k-token vocabulary is 197M of the 322M params: its grad + AdamW state
    # alone (~2.3 GB) pushed MPS out of memory. Our commands do not need it retrained.
    model.encoder.embeddings.tok_embeddings.weight.requires_grad_(False)
    enc_p = [p for n, p in model.named_parameters() if n.startswith("encoder.") and p.requires_grad]
    head_p = [p for n, p in model.named_parameters() if not n.startswith("encoder.")]
    opt = torch.optim.AdamW([{"params": enc_p, "lr": LR_ENCODER}, {"params": head_p, "lr": LR_HEAD}], weight_decay=0.01)
    total = max(1, (len(train) // (MICRO_BATCH * GRAD_ACCUM)) * EPOCHS)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=total, eta_min=1e-6)
    print(f"training {len(train)} items, {n_cal} held out for calibration, {EPOCHS} epochs, {total} updates on {DEVICE}", flush=True)

    t0 = time.time()
    for epoch in range(EPOCHS):
        rng.shuffle(train)
        sigma = SIGMA_START + (SIGMA_END - SIGMA_START) * (epoch / max(1, EPOCHS - 1))
        opt.zero_grad(set_to_none=True)
        run_loss, nb = 0.0, 0
        for bi in range(0, len(train), MICRO_BATCH):
            batch = collate(train[bi:bi + MICRO_BATCH], tok.pad_token_id)
            logits, act = forward(model, batch)
            logits = logits.float()
            mask = batch[3].to(DEVICE)
            target = batch[4].to(DEVICE)
            qt = batch[5].to(DEVICE)
            k = mask.sum(-1, keepdim=True).float()
            eps = torch.randn((GROUP_SIZE,) + logits.shape, device=DEVICE) * sigma * mask
            eps = (eps - eps.sum(-1, keepdim=True) / k) * mask
            z = logits.detach().unsqueeze(0) + eps
            q = torch.softmax(z.masked_fill(~mask, -1e4), -1)
            with torch.no_grad():
                r = proper_reward(q, target.unsqueeze(0), qt, mask, w_sph=0.75, w_rps=1.0)
                adv = r - r.mean(0, keepdim=True)
                adv = adv / (adv.std() + 1e-6)
            logp = -(((z - logits.unsqueeze(0)) ** 2) * mask).sum(-1) / (2 * sigma ** 2)
            loss_rl = -(adv * logp).mean()
            loss_ce = -(target * torch.log_softmax(logits.masked_fill(~mask, -1e4), -1)).sum(-1).mean()
            loss = (loss_rl + loss_ce) / GRAD_ACCUM + 0.0 * act.sum()
            loss.backward()
            nb += 1
            run_loss += loss_ce.item()
            if nb % GRAD_ACCUM == 0 or bi + MICRO_BATCH >= len(train):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step(); sched.step(); opt.zero_grad(set_to_none=True)
            if nb % 50 == 0 or nb == 10:
                done = (epoch * len(train) + bi) / (EPOCHS * len(train))
                el = time.time() - t0
                print(f"  ep {epoch+1}/{EPOCHS} step {nb} ce {run_loss/50:.3f} reward {r.mean().item():.3f} "
                      f"| {done:.0%} {el/60:.1f}min, eta {el/max(done,1e-6)*(1-done)/60:.1f}min", flush=True)
                run_loss = 0.0
        print(f"=== epoch {epoch+1} done at {(time.time()-t0)/60:.1f}min", flush=True)

    model.eval()
    preds = []
    with torch.no_grad():
        for ci in range(0, len(calib), 16):
            chunk = calib[ci:ci + 16]
            lg, _ = forward(model, collate(chunk, tok.pad_token_id))
            lg = lg.float().cpu().numpy()
            for j, it in enumerate(chunk):
                preds.append((it["qtype"], lg[j, :len(it["markers"])].tolist(), it["target"]))
    temps = [1.0, 1.0, 1.0]
    for qt in range(3):
        sel = [(z, t) for q, z, t in preds if q == qt]
        if sel:
            temps[qt] = fit_temp(sel)
    held_acc = sum(max(range(len(z)), key=z.__getitem__) == t.index(max(t)) for _, z, t in preds) / max(1, len(preds))
    print(f"calibration temps {temps}  held-out item accuracy {held_acc:.3f}", flush=True)

    # Save as a normal Laya checkpoint: base files + new weights + new config.
    from huggingface_hub import snapshot_download
    base_dir = snapshot_download(BASE)
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(base_dir, OUT, ignore=shutil.ignore_patterns("model.safetensors", "*.md", ".gitattributes"))
    sd = {k: v.half().contiguous().cpu() for k, v in model.state_dict().items()}
    save_file(sd, os.path.join(OUT, "model.safetensors"))
    cfg = dict(agent.cfg)
    cfg.update({"fine_tuned": True, "model_name": "jv-reflex", "temperature": temps, "head_max_len": HEAD, "max_len": MAXLEN})
    cfg.pop("temperature_by_options", None)
    with open(os.path.join(OUT, "rl_agent_config.json"), "w") as f:
        json.dump(cfg, f, indent=2, default=str)
    print(f"saved -> {OUT}  total {(time.time()-t0)/60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
