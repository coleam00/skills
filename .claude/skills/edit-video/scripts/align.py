"""Place a cut head or tail with forced alignment, not Whisper timestamps.

Usage:
  uv run --project $S --extra align python $S/align.py <ws> <segment> head  [--word N] [--write]
  uv run --project $S --extra align python $S/align.py <ws> <segment> tail  [--write]
  uv run --project $S --extra align python $S/align.py <ws> <clip> --from <s> --to <s>       # word table only

Why: Whisper's word ends run 50-300 ms early, and Whisper completes a word from its first half, so a cut placed
from its timestamps (or "proved" by re-transcribing) can still clip a syllable. This aligns the known words to the
audio with torchaudio's MMS_FA model, then reads the waveform around the aligned word:

  head  the safe in point for <segment>: before the target word's first sound (aligned start, walked back to where
        the level leaves the room), after the previous word's decay. --word N picks the Nth word of the segment
        (0 = first) when a false start is being trimmed off the front.
  tail  the safe out point: after the last word's aligned end AND its decay to room tone, and after any voiced
        burst within 0.3 s of it (that burst is the end of the word, not a new sound), before the next word.
  table aligned start/end for every word in a window of a clip, next to Whisper's.

Prints the aligned words, Whisper's times and the suggested point. --write puts it into overrides.json ("in" or
"out" for that segment); re-run cutpoints.py, assemble.py and validate_cut.py after. Nothing else is written.
Needs the `align` extra (torch + torchaudio); runs on the GPU if torch sees one, else the CPU (seconds per window).
"""
import os, re, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HOP, bands, envelope, load, read_wav, save, ws

SR = 16000
PRE = 0.03        # lead before the first sound of the head word
POST = 0.03       # room tone kept after the tail word's decay
DECAY_MAX = 0.40  # a falling ending takes up to this long to reach the room
BURST = 0.30      # a voiced burst this close after the word belongs to the word

norm = lambda w: re.sub(r"[^a-z']", "", w.lower().replace("’", "'"))

def model():
    import warnings
    warnings.filterwarnings("ignore", message=".*forced_align has been deprecated.*")
    try:
        import torch, torchaudio
    except ImportError:
        sys.exit("align.py needs the align extra: uv run --project $S --extra align python $S/align.py ...")
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    b = torchaudio.pipelines.MMS_FA
    return torch, b.get_model(with_star=False).to(dev), b.get_tokenizer(), b.get_aligner(), dev

def align(audio16, t0, words, M):
    """Aligned (start, end) in clip seconds for every word; None for a word with no letters (a number, a symbol)."""
    torch, mdl, tok, aligner, dev = M
    keep = [i for i, w in enumerate(words) if norm(w["w"]).strip("'")]
    if not keep: return [None] * len(words)
    x = torch.from_numpy(audio16.astype(np.float32)).unsqueeze(0).to(dev)
    with torch.inference_mode(): em, _ = mdl(x)
    spans = aligner(em[0], tok([norm(words[i]["w"]).strip("'") for i in keep]))
    ratio = x.size(1) / em.size(1) / SR
    out = [None] * len(words)
    for i, sp in zip(keep, spans): out[i] = (t0 + sp[0].start * ratio, t0 + sp[-1].end * ratio)
    return out

def window(d, clip, lo, hi):
    """16 kHz audio of the clip from lo to hi seconds."""
    x, sr = read_wav(os.path.join(d, "audio", f"{clip}_16k.wav"))
    if sr != SR: sys.exit(f"expected 16 kHz audio in audio/{clip}_16k.wav (run transcribe.py)")
    return x[int(max(0, lo) * SR):int(hi * SR)]

def levels(d, clip):
    x, sr = read_wav(os.path.join(d, "audio", f"{clip}_48k.wav"))
    db = envelope(x, sr); t, lo, _ = bands(x, sr)
    loud = db[db > db.max() - 60]; lvl = np.percentile(loud, 60)
    room = max(np.percentile(db, 10) + 10, lvl - 38)
    lo_thr = np.percentile(lo[lo > lo.max() - 60], 70) - 18
    return db, room, t, lo, lo_thr

def table(words, al):
    print(f"  {'word':18} {'whisper':>15}   {'aligned':>15}   start/end shift")
    for w, a in zip(words, al):
        if a is None: print(f"  {w['w'][:18]:18} {w['s']:7.3f}-{w['e']:<7.3f}   (not alignable: no letters)"); continue
        print(f"  {w['w'][:18]:18} {w['s']:7.3f}-{w['e']:<7.3f}   {a[0]:7.3f}-{a[1]:<7.3f}   {a[0] - w['s']:+.3f} / {a[1] - w['e']:+.3f}")

def main():
    d, cfg = ws(); a = sys.argv
    if len(a) < 3: sys.exit(__doc__)
    target = a[2]; W = load(d, "words.json") or sys.exit("run transcribe.py first")
    M = model()
    if "--from" in a:                                    # word table for a window of a clip
        clip, lo, hi = target, float(a[a.index("--from") + 1]), float(a[a.index("--to") + 1])
        words = [w for w in W[clip] if w["s"] >= lo and w["e"] <= hi]
        al = align(window(d, clip, lo - 0.5, hi + 0.5), max(0, lo - 0.5), words, M); table(words, al); return
    mode = a[3] if len(a) > 3 else sys.exit("say head or tail")
    seg = next((s for s in load(d, "cuts.json")["segments"] if s["key"] == target), None) or sys.exit(f"no segment {target} in cuts.json")
    clip = seg["clip"]; cw = W[clip]
    inside = [i for i, w in enumerate(cw) if w["e"] > seg["in"] - 0.05 and w["s"] < seg["out"] + 0.05]
    if not inside: sys.exit("no words in that segment")
    if mode == "head":
        k = inside[0] + int(a[a.index("--word") + 1]) if "--word" in a else inside[0]
        idx = list(range(max(0, k - 2), min(len(cw), k + 3)))
    else:
        k = inside[-1]; idx = list(range(max(0, k - 3), min(len(cw), k + 2)))
    words = [cw[i] for i in idx]; lo, hi = words[0]["s"] - 0.6, words[-1]["e"] + 0.6
    al = align(window(d, clip, lo, hi), max(0, lo), words, M); table(words, al)
    j = idx.index(k); A = al[j]
    if A is None: sys.exit(f"'{cw[k]['w']}' has no letters to align; place this cut by the waveform")
    db, room, t, lo_b, lo_thr = levels(d, clip); n = len(db)
    i_ = lambda s: int(np.clip(s / HOP, 0, n - 1))
    if mode == "head":
        i = i_(A[0])
        while i > 0 and db[i - 1] > room and (A[0] - i * HOP) < 0.25: i -= 1      # the first sound can precede the aligned start
        onset = i * HOP; floor = 0.0
        prev = al[j - 1] if j > 0 else None
        if prev:                                                                # never inside the previous word or its decay
            p = i_(prev[1])
            while p < n - 1 and db[p] > room and (p * HOP - prev[1]) < DECAY_MAX: p += 1
            floor = p * HOP
        point = max(floor, onset - PRE)
        print(f"\nHEAD {target}: '{cw[k]['w']}' aligned {A[0]:.3f}, first sound {onset:.3f}"
              + (f", previous word '{cw[idx[j - 1]]['w']}' decays to {floor:.3f}" if prev else "") + f"\n  safe in = {point:.3f}  (current {seg['in']:.3f})")
        if prev and floor > onset - 0.01: print("  WARN no room tone between the two words: the head cannot be clean here; cut at the decay and listen")
        key = "in"
    else:
        i = i_(A[1]); low = db[i]; start = i
        while i < n - 1 and db[i] > room and (i - start) * HOP < DECAY_MAX:
            low = min(low, db[i])
            if low < room + 8 and db[i] > low + 10: break                      # rising again near the floor: a breath
            i += 1
        decay = i * HOP; point = decay + POST
        ti = int(np.searchsorted(t, decay)); burst = None
        for m in range(ti, min(len(t), int(np.searchsorted(t, decay + BURST)))):
            if lo_b[m] > lo_thr: burst = float(t[m]); break
        nxt = al[j + 1] if j + 1 < len(al) else None
        if burst is not None and (nxt is None or burst < nxt[0] - 0.05):
            m = int(np.searchsorted(t, burst))
            while m < len(t) - 1 and lo_b[m] > lo_thr - 6: m += 1
            print(f"  voiced burst at {burst:.3f}, {burst - A[1]:.2f} s after the word: treated as its ending")
            point = max(point, float(t[m]) + POST)
        if nxt: point = min(point, nxt[0] - 0.02)
        print(f"\nTAIL {target}: '{cw[k]['w']}' aligned end {A[1]:.3f}, decay to room {decay:.3f}\n  safe out = {point:.3f}  (current {seg['out']:.3f})")
        if nxt and nxt[0] - 0.02 < decay: print("  WARN the next word starts inside this one's decay: no clean tail; listen before cutting")
        key = "out"
    if "--write" in a:
        ov = load(d, "overrides.json", default={}) or {}
        ov.setdefault(key, {})[target] = round(point, 3); save(ov, d, "overrides.json")
        print(f"  wrote overrides.json {key}.{target} = {point:.3f}; re-run cutpoints.py, assemble.py, validate_cut.py")

if __name__ == "__main__":
    main()
