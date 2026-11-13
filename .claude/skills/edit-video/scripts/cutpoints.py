"""Decide every cut: segments, head (in) and tail (out) points, on the source timelines.

Usage: uv run --project $S python cutpoints.py <ws> [--max-pause 0.6] [--split-clips] [--no-asr]

Segments
  clips mode  : one segment per clip (add --split-clips to also cut long pauses inside clips)
  single mode : the file is split wherever the gap between words exceeds --max-pause (jump cuts)
Head : first sustained sound (40 ms) before the first word, minus PRE. Never earlier than first word - HEAD_CAP,
       so an inhale before the line is dropped while unvoiced initials ("So", "Then") keep their consonant.
Tail : (1) voiced end: walk forward from the last word through low-band (voicing) energy, tolerating dips < 80 ms
       (2) attach a final unvoiced consonant (high band, <= 0.12 s, no gap) - "defenses", "actions"
       (3) ASR probe: earliest cut where the last word is still transcribed exactly by two decodes (unless --no-asr)
       (4) keep the word's decay until it reaches the room (<= DECAY_MAX), then give back natural silence
           (<= 0.2 s) but stop the moment a breath or next sound starts
Writes <ws>/cuts.json and prints one line per segment. Apply manual decisions in <ws>/overrides.json:
  {"drop": ["c03_s02"], "in": {"c04_s01": 1.20}, "out": {...}, "video_out": {"c02_s01": 11.19}}
"""
import os, re, subprocess, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HOP, asr_model, bands, envelope, load, p, read_wav, save, wav, ws

PRE = 0.10        # lead-in before the first sound: enough that the first consonant is not clipped
HEAD_CAP = 0.25   # never start more than this before Whisper's first word (drops inhales)
DIP_OK = 0.08     # a voicing dip shorter than this is inside a word, not its end
FRIC_MAX = 0.12   # an attached final fricative is shorter than this; longer broadband sound is a breath
DECAY_MAX = 0.40  # the last word's decay is kept until it reaches the room, up to this; it is sound, not pause.
                  # measured from the robust end on falling endings: 0.32, 0.38, 0.40 s
SIL_PAD = 0.20    # natural silence kept after the last word (target join pause ~0.2-0.3 s total)
MIN_TAIL = 0.06   # always keep at least this after the robust end (word decay)
JOIN_MAX = 0.25   # pause budget per join (tail pad + next head lead-in); above ~0.4 s heard reads as dead air

norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())

def segments_for(cfg, words, max_pause, split_clips):
    segs = []
    inserts = {i["key"] for i in cfg.get("inserts", [])}
    for c in cfg["clips"]:
        if c["key"] in inserts: continue          # a finished segment from insert_segment.py: placed whole, below
        ws_ = words.get(c["key"], [])
        if not ws_: continue
        groups = [[ws_[0]]]
        for a, b in zip(ws_, ws_[1:]):
            if (cfg["mode"] == "single" or split_clips) and b["s"] - a["e"] > max_pause: groups.append([b])
            else: groups[-1].append(b)
        for i, g in enumerate(groups):
            segs.append({"key": f"{c['key']}_s{i + 1:02d}", "clip": c["key"], "path": c["path"], "words": g,
                         "lo_lim": 0.0 if i == 0 else groups[i - 1][-1]["e"] + 0.05,
                         "hi_lim": c["dur"] if i == len(groups) - 1 else groups[i + 1][0]["s"] - 0.05})
    return segs

def c_dur(cfg, k):
    return next(c["dur"] for c in cfg["clips"] if c["key"] == k)

def main():
    d, cfg = ws()
    args = sys.argv
    max_pause = float(args[args.index("--max-pause") + 1]) if "--max-pause" in args else 0.6
    use_asr = "--no-asr" not in args
    words = load(d, "words.json")
    if not words: sys.exit("Run transcribe.py first")
    segs = segments_for(cfg, words, max_pause, "--split-clips" in args)
    model = None
    if use_asr:
        model = asr_model(cfg, d)
    cache = {}
    for s in segs:
        k = s["clip"]
        if k not in cache:
            src = next(c["path"] for c in cfg["clips"] if c["key"] == k)      # a clip rebuilt since transcribe.py
            os.makedirs(os.path.join(d, "audio"), exist_ok=True)
            x, sr = read_wav(wav(src, os.path.join(d, "audio", f"{k}_48k.wav")))   # ran: refresh its audio first
            db = envelope(x, sr); t, lo, hi = bands(x, sr)
            loud = db[db > db.max() - 60]
            cache[k] = dict(x=x, sr=sr, db=db, t=t, lo=lo, hi=hi, lvl=np.percentile(loud, 60), floor=np.percentile(db, 10),
                            lo_thr=np.percentile(lo[lo > lo.max() - 60], 70) - 18, hi_thr=np.percentile(hi[hi > hi.max() - 60], 70) - 18)
        a = cache[k]; db, t, lo, hi = a["db"], a["t"], a["lo"], a["hi"]
        idx = lambda sec: int(np.clip(sec / HOP, 0, len(db) - 1))
        tid = lambda sec: int(np.clip(np.searchsorted(t, sec), 0, len(t) - 1))
        w0, w1 = s["words"][0], s["words"][-1]
        # ---- head
        thr = a["lvl"] - 16; kk = int(0.04 / HOP)
        i = idx(max(s["lo_lim"], w0["s"] - 0.6))
        while i < len(db) - kk and not (db[i:i + kk] > thr).all(): i += 1
        onset = i * HOP
        cut_in = max(s["lo_lim"], onset - PRE)
        if w0["s"] > 0.05: cut_in = max(cut_in, w0["s"] - HEAD_CAP)
        # ---- tail: voiced end with dip tolerance
        j = tid(w1["e"] - 0.05); last_on = j; quiet = 0
        while j < len(t) - 1:
            if lo[j] > a["lo_thr"]: last_on = j; quiet = 0
            else:
                quiet += 1
                if quiet * HOP >= DIP_OK: break
            j += 1
        v_end = float(t[last_on]); end = v_end; m = j; gap = 0
        while m < len(t) - 1 and t[m] - v_end < FRIC_MAX:          # attached final fricative
            if hi[m] > a["hi_thr"]: end = float(t[m]); gap = 0
            else:
                gap += 1
                if gap * HOP > 0.03: break
            m += 1
        hi_lim = s["hi_lim"]
        # ---- ASR probe: earliest robust end
        if model is not None:
            # never probe before the head: a sub-second segment at a clip's end ("Thank you.") put the window inside out
            target = norm(w1["w"]); probes = []; c_ = max(end - 0.12, cut_in + 0.1)
            while c_ <= min(hi_lim, end + 0.45):
                probes.append(c_); c_ += 0.04
            # local Whisper: two beams must agree. A remote model (full mode) ignores beam_size, so one call per point,
            # all points of a segment at once (one by one, a full video took ~2 hours)
            remote = getattr(model, "remote", False)
            beams = (1,) if remote else (5, 1)

            def probe(ic, k=k, target=target):
                i_, c = ic
                tmp = p(d, "audio", f"_probe{i_ if remote else ''}.wav")
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(cut_in, c - 5):.3f}", "-to", f"{c:.3f}", "-i",
                                os.path.join(d, "audio", f"{k}_48k.wav"), "-ar", "16000", tmp], check=True)
                ok = 0
                for beam in beams:
                    out, _ = model.transcribe(tmp, language=cfg.get("language", "en"), beam_size=beam, condition_on_previous_text=False)
                    toks = " ".join(x.text for x in out).split()
                    ok += bool(toks) and norm(toks[-1]) == target
                return c, ok == len(beams)
            if remote:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(8) as ex: pts = list(ex.map(probe, enumerate(probes)))
            else:
                pts = [probe((0, c)) for c in probes]
            if remote:   # one read per point varies call to call: a lone miss among good reads is noise, a clipped
                # word fails several points in a row, so it is the earliest good point with no two misses in a row after it
                gs = [g for _, g in pts]
                robust = next((pt for i_, (pt, g) in enumerate(pts) if g and gs[-1]
                               and not any(not a_ and not b_ for a_, b_ in zip(gs[i_:], gs[i_ + 1:]))), None)
            else:
                robust = next((pt for i_, (pt, _) in enumerate(pts) if all(g for _, g in pts[i_:])), None)
            if robust is not None: end = max(robust, end - 0.06)
            else: print(f"   WARN {s['key']}: last word '{w1['w']}' never transcribed reliably; keeping acoustic end")
        # ---- word decay: the ASR robust end sits mid-decay on falling endings ("eventually", "sessions"), so walk
        # until the level reaches the room (<= DECAY_MAX). A fixed 0.12 s cut three of those on sound
        sil = max(a["floor"] + 10, a["lvl"] - 38); i = idx(end); start = i; low = db[i]
        while i < len(db) - 1 and db[i] > sil and (i - start) * HOP < DECAY_MAX:
            low = min(low, db[i])
            if low < a["lvl"] - 30 and db[i] > low + 10: break      # rising again near the floor: breath, not decay
            i += 1
        decay_end = i * HOP; q0 = i
        while i < len(db) - 1 and db[i] <= sil and (i - q0) * HOP < SIL_PAD: i += 1        # true silence, stop at breath
        cut_out = min(hi_lim, max(end + MIN_TAIL, i * HOP))
        # a cut clamped to the file's edge never found silence there: the camera file probably starts late or stops early
        file_end = len(db) * HOP
        if s["hi_lim"] >= c_dur(cfg, k) - 0.01:
            if cut_out > file_end - 0.1 and db[-int(0.05 / HOP):].max() > -50:   # still a word decaying (pad_takes ABS_TAIL)
                print(f"   WARN {s['key']}: OUT AT FILE END: the camera file may have stopped mid-word. "
                      f"Run pad_takes.py <ws> --long ... (--keys {k} --force if it says ok)")
        if cut_in < 0.02 and s["lo_lim"] == 0.0:
            print(f"   WARN {s['key']}: IN AT FILE START: the camera file may have started after you began talking. "
                  f"Run pad_takes.py <ws> --long ... (STARTS ON SOUND)")
        s.update({"in": round(cut_in, 3), "out": round(cut_out, 3), "onset": round(onset, 3), "v_end": round(v_end, 3), "end": round(end, 3),
                  "decay_end": round(min(hi_lim, decay_end), 3), "text": " ".join(w["w"] for w in s["words"])})
        print(f"{s['key']:9} in {cut_in:7.3f}  out {cut_out:7.3f}  ({cut_out - cut_in:5.2f}s)  {s['text'][:70]}")
    ov = load(d, "overrides.json", default={}) or {}
    segs = [s for s in segs if s["key"] not in set(ov.get("drop", []))]
    # ---- neighbours from the same recording with no real pause between them (Whisper invented the gap) are one
    # segment: cutting there would play audio twice or punch in mid-sentence
    k = 0
    while k < len(segs) - 1:
        s, nx = segs[k], segs[k + 1]
        if s["clip"] == nx["clip"] and nx["onset"] - s["end"] < 0.15:
            s.update(out=nx["out"], end=nx["end"], v_end=nx["v_end"], decay_end=nx["decay_end"], text=s["text"] + " " + nx["text"], words=s["words"] + nx["words"])
            print(f"merged {nx['key']} into {s['key']} (no pause between them)"); del segs[k + 1]
        else: k += 1
    # ---- pause budget: silence after the decay + next head lead-in. Trim the tail first, never into the decay
    for s, nx in zip(segs, segs[1:]):
        over = (s["out"] - s["decay_end"]) + (nx["onset"] - nx["in"]) - JOIN_MAX
        if over > 0: s["out"] = round(max(s["end"] + MIN_TAIL, s["decay_end"], s["out"] - over), 3)
    # ---- inserts (insert_segment.py): a finished segment goes in whole, after the segment it was placed after
    for ins in cfg.get("inserts", []):
        pos = next((i for i, s in enumerate(segs) if s["key"] == ins["after"]), None)
        if pos is None: pos = next((i for i, s in enumerate(segs) if s["clip"] == ins["after"].split("_")[0]), None)
        if pos is None: print(f"WARN insert {ins['key']}: segment {ins['after']} not found; appended at the end"); pos = len(segs) - 1
        while pos + 1 < len(segs) and segs[pos + 1]["clip"] == segs[pos]["clip"] and segs[pos + 1]["key"].startswith(ins["after"]): pos += 1
        segs.insert(pos + 1, dict(ins["segment"], words=[w for w in words.get(ins["key"], []) if ins["segment"]["in"] - 0.05 <= w["s"] < ins["segment"]["out"]]))
    for s in segs:
        if s["key"] in ov.get("in", {}): s["in"] = ov["in"][s["key"]]
        if s["key"] in ov.get("out", {}): s["out"] = ov["out"][s["key"]]
    # ---- splices: a slip inside a clip ("the the", a restarted word) is removed by cutting the segment in two around
    # it. overrides.json "splice": {"c14_s01": [[51.40, 51.66]]} (source seconds); the parts are <key>, <key>b, ...
    # Find the range with the slip search (references/cutting.md) and prove it by transcribing the spliced audio.
    out_segs = []; segs_keys = {s["key"] for s in segs}
    for s in segs:
        cuts = sorted(ov.get("splice", {}).get(s["key"], []))
        if not cuts: out_segs.append(s); continue
        edges = [s["in"]] + [x for a_b in cuts for x in a_b] + [s["out"]]
        for j in range(0, len(edges), 2):
            a, b = edges[j], edges[j + 1]
            part = dict(s, key=s["key"] + ("" if j == 0 else chr(ord("a") + j // 2)), words=[w for w in s["words"] if a - 0.05 <= w["s"] < b])
            part["text"] = " ".join(w["w"] for w in part["words"])
            if j > 0: part.update(**{"in": a, "onset": a})
            if j < len(edges) - 2: part.update(out=b, end=b, v_end=b, decay_end=b)
            out_segs.append(part)
        print(f"spliced {s['key']} at {cuts} -> {len(edges) // 2} parts")
    # in/out set on a splice PART (c02_s01b, the key the FINAL table prints) only exists now: apply it here, or it was
    # starred in the table and silently ignored. An override on the base key still sets the whole segment's ends above.
    for s in out_segs:
        if s["key"] in segs_keys: continue
        if s["key"] in ov.get("in", {}): s["in"] = s["onset"] = ov["in"][s["key"]]
        if s["key"] in ov.get("out", {}): s["out"] = ov["out"][s["key"]]
    segs = out_segs
    # ---- retakes: a segment that restarts the same words as one of the next three is almost always a flubbed take.
    # Reported, never dropped automatically: read both and put the loser in overrides.json "drop" (usually the earlier).
    import difflib
    head = lambda s: [norm(w["w"]) for w in s["words"][:8]]
    for i, s in enumerate(segs):
        for nx in segs[i + 1:i + 4]:
            r = difflib.SequenceMatcher(a=head(s), b=head(nx)).ratio()
            if r >= 0.6: print(f"RETAKE? {s['key']} ~ {nx['key']} ({r:.2f}): {' '.join(head(s))!r}")
    save({"segments": [{k: v for k, v in s.items() if k != "words"} for s in segs]}, d, "cuts.json")
    # The lines above are the detector's proposals; this is what cuts.json now holds (after drops, merges, the join
    # budget, overrides and splices), so a hand-set in/out can be checked here rather than by opening cuts.json.
    print("FINAL (cuts.json; * = set in overrides.json)")
    for s in segs:
        mi = "*" if s["key"] in ov.get("in", {}) else " "
        mo = "*" if s["key"] in ov.get("out", {}) else " "
        vo = f"  video_out {ov['video_out'][s['key']]:.3f}" if s["key"] in ov.get("video_out", {}) else ""
        print(f"  {s['key']:9} in {s['in']:7.3f}{mi} out {s['out']:7.3f}{mo} ({s['out'] - s['in']:5.2f}s){vo}")
    print(f"{len(segs)} segments, {sum(s['out'] - s['in'] for s in segs):.1f}s kept")

if __name__ == "__main__":
    main()
