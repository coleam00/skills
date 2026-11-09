"""Find dead space INSIDE segments: a swallow, a breath, a second spent remembering the next line, a stutter.
cutpoints.py only trims heads and tails; nothing else looks at the middle of a take, and viewers hear every one of these.

Usage: uv run --project $S python pauses.py <ws> [--min 0.60] [--keep 0.25] [--apply]
  Lists every internal pause >= --min seconds (quiet stretch between two words, measured on the audio, not on
  Whisper's timestamps) and every repeated word or short phrase ("I I", "also I also"), with the words around it.
  --apply writes a splice for each pause into overrides.json "splice", keeping --keep seconds of the quiet
  (half on each side), merged with any splices already there. Then re-run cutpoints.py + assemble.py.

Read the list before applying. A pause on purpose (a beat before a punchline, a click on screen being shown) stays:
delete its entry from overrides.json. Repeats are only REPORTED: confirm each on the raw clip (references/cutting.md, Slips)
and splice it by hand; Whisper invents doubles.
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import envelope, HOP, load, p, read_wav, save, ws

def main():
    d, cfg = ws()
    arg = lambda k, v: float(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else v
    MIN, KEEP = arg("--min", 0.60), arg("--keep", 0.25)
    cuts = load(d, "cuts.json")["segments"]; W = load(d, "words.json")
    ov = load(d, "overrides.json") or {}; spl = ov.setdefault("splice", {})
    norm = lambda s: re.sub(r"[^a-z0-9']", "", s.lower())
    found = 0
    for s in cuts:
        k, clip = s["key"], s["clip"]
        if k.endswith("b") or clip.startswith("m"): continue   # spliced parts and finished inserts are left alone
        x, sr = read_wav(p(d, "audio", f"{clip}_48k.wav")); db = envelope(x, sr)
        thr = max(-60.0, float(sorted(db[db > -70])[int(0.60 * (db > -70).sum())]) - 14) if (db > -70).any() else -45
        words = [w for w in W[clip] if w["s"] >= s["in"] - 0.05 and w["e"] <= s["out"] + 0.05]
        last = -1.0
        for a, b in zip(words, words[1:]):
            lo, hi = int(a["s"] / HOP), int(b["e"] / HOP)   # search between the two words' middles
            run, best = 0, (0, 0)
            for i in range(lo, hi):
                run = run + 1 if db[i] < thr else 0
                if run > best[0]: best = (run, i)
            dur = best[0] * HOP
            if dur < MIN: continue
            q1 = best[1] * HOP; q0 = q1 - dur + HOP
            if q0 < last: continue   # the same quiet stretch, seen again from the next word pair
            last = q1
            ctx = " ".join(w["w"] for w in words[max(0, words.index(a) - 5): words.index(a) + 1])
            nxt = " ".join(w["w"] for w in words[words.index(b): words.index(b) + 5])
            print(f"PAUSE {k} {q0:7.2f}-{q1:7.2f} ({dur:.2f}s)  ...{ctx} | {nxt}...")
            found += 1
            cut = [round(q0 + KEEP / 2, 3), round(q1 - KEEP / 2, 3)]
            if "--apply" in sys.argv and not any(c[0] <= cut[1] and cut[0] <= c[1] for c in spl.get(k, [])):
                spl.setdefault(k, []).append(cut)
        t = [norm(w["w"]) for w in words]
        for n in (1, 2, 3):
            for i in range(len(t) - 2 * n + 1):
                if t[i:i + n] == t[i + n:i + 2 * n] and all(t[i:i + n]) and not (n == 1 and t[i] in ("that", "had", "is")):
                    print(f"REPEAT {k} {words[i]['s']:7.2f}  '{' '.join(w['w'] for w in words[max(0, i - 3): i + 2 * n + 3])}'")
        for i in range(len(t) - 2):   # "also I also": a word, one filler, the word again
            if t[i] and t[i] == t[i + 2] and t[i] not in ("the", "a", "and", "to", "of"):
                print(f"RESTART {k} {words[i]['s']:7.2f}  '{' '.join(w['w'] for w in words[max(0, i - 3): i + 6])}'")
    if "--apply" in sys.argv:
        for k in spl: spl[k] = sorted(spl[k])
        save(ov, d, "overrides.json"); print(f"{found} pauses; splices written to overrides.json")
    else:
        print(f"{found} pauses >= {MIN}s (dry run; --apply writes splices)")

if __name__ == "__main__":
    main()
