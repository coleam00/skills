"""Insert a finished segment (an ad read, an intro, a pre-cut section) into a workspace as one more clip.

Usage:
  uv run --project $S python $S/insert_segment.py <ws> <finished.mp4> --after <segment key> [--key m01] [--no-asr]
  uv run --project $S python $S/insert_segment.py <ws> --check <exported.mp4> [--tag v1] [--offset 0]

Insert: the file gets its own workspace (<ws>/inserts/<key>/), is transcribed and trimmed as ONE segment (heads and
tails cut like every other clip, nothing inside it touched), and is then copied into <ws>: its clip into config.json,
its words into words.json, its audio into audio/<key>_*.wav and its segment into cuts.json right after --after.
config.json "inserts" records it, so a later cutpoints.py run puts it back in the same place instead of re-cutting it
at its pauses. Keys start with "m": assemble.py never punches in on them and pauses.py leaves them alone.
Then: assemble.py <ws> --level (a mastered insert lands 2-3 dB hot otherwise), validate_cut.py, and a transition or a
clean cut on BOTH of its joins. Place it where a section ends and the next opens with its own setup line.

--check: after the export, cross-correlates the exported audio against each source clip just before, inside and just
after every insert. The export's own sync probe compares against the clean cut, so it cannot see an insert that
shifted everything after it. Any lag over ~5 ms (a third of a frame at 60 fps) needs fixing: pad or trim room tone in
the pause after the insert by the printed amount, re-assemble, re-export, re-check. --offset: seconds of extra
material at the head of the export (0 for finalize.py and export_final.py).
"""
import os, shutil, subprocess, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import load, probe, save, ws

def arg(a, k, default=None): return a[a.index(k) + 1] if k in a else default

def step(*cmd):
    print("  $", " ".join(os.path.basename(c) if c.endswith(".py") else c for c in cmd))
    r = subprocess.run([sys.executable, *cmd], text=True, encoding="utf-8", errors="replace", capture_output=True)
    if r.returncode: sys.exit(r.stdout[-1500:] + r.stderr[-1500:])
    return r.stdout

def insert(d, cfg, a):
    src = os.path.abspath(a[2]); after = arg(a, "--after") or sys.exit("--after <segment key> is required (where the insert goes)")
    key = arg(a, "--key", "m01")
    if not key.startswith("m"): sys.exit("insert keys start with 'm' (m01, m02): other scripts treat those as finished inserts")
    cuts = load(d, "cuts.json") or sys.exit("run cutpoints.py on the workspace first")
    if not any(s["key"] == after for s in cuts["segments"]): sys.exit(f"no segment {after} in cuts.json")
    sub = os.path.join(d, "inserts", key)
    step(os.path.join(HERE, "init_workspace.py"), src, "--out", sub, "--no-sync")
    step(os.path.join(HERE, "transcribe.py"), sub)
    step(os.path.join(HERE, "cutpoints.py"), sub, "--max-pause", "99", *(["--no-asr"] if "--no-asr" in a else []))
    segs = load(sub, "cuts.json")["segments"]
    if len(segs) > 1: print(f"  NOTE {len(segs)} segments in the insert (a retake?); using first in to last out")
    s0, s1 = segs[0], segs[-1]
    info = probe(src)
    if (info["w"], info["h"], info["fps"]) != (cfg["w"], cfg["h"], cfg["fps"]):
        print(f"  WARN insert is {info['w']}x{info['h']}@{info['fps']}, the edit is {cfg['w']}x{cfg['h']}@{cfg['fps']}: "
              "assemble.py scales it to fit, check its frames for stretching")
    seg = dict(key=f"{key}_s01", clip=key, path=src, lo_lim=0.0, hi_lim=round(info["dur"], 3), **{"in": s0["in"]}, out=s1["out"],
               onset=s0["onset"], v_end=s1["v_end"], end=s1["end"], decay_end=s1["decay_end"],
               text=" ".join(s["text"] for s in segs))
    words = load(d, "words.json") or {}; words[key] = load(sub, "words.json")["c01"]; save(words, d, "words.json")
    for sr in ("48k", "16k"):
        shutil.copy2(os.path.join(sub, "audio", f"c01_{sr}.wav"), os.path.join(d, "audio", f"{key}_{sr}.wav"))
    cfg["clips"] = [c for c in cfg["clips"] if c["key"] != key] + [{"key": key, "path": src, "dur": round(info["dur"], 3), "audio": info["audio"]}]
    cfg["inserts"] = [i for i in cfg.get("inserts", []) if i["key"] != key] + [{"key": key, "path": src, "after": after, "segment": seg}]
    save(cfg, d, "config.json")
    out = [s for s in cuts["segments"] if s["clip"] != key]
    pos = max(i for i, s in enumerate(out) if s["key"] == after or s["key"].startswith(after))   # after its splice parts too
    out.insert(pos + 1, seg); cuts["segments"] = out; save(cuts, d, "cuts.json")
    print(f"inserted {seg['key']} after {after}: {seg['in']:.3f}-{seg['out']:.3f} ({seg['out'] - seg['in']:.2f}s)  {seg['text'][:80]}")
    print("next: assemble.py <ws> --level, validate_cut.py, transitions on both joins; after export, insert_segment.py <ws> --check <file>")

_PCM = {}

def pcm(path, ss, t, sr=16000):
    """Audio of `path` from ss for t seconds. Each file is decoded once from its start and sliced: input seeking
    (-ss before -i) on an AAC file can return a window that starts a few frames late, which reads as a fake lag."""
    if path not in _PCM:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                             capture_output=True).stdout
        _PCM[path] = np.frombuffer(raw, np.int16)
    x = _PCM[path]; a = int(max(0, ss) * sr)
    return x[a:a + int(t * sr)].astype(np.float32)

def lag_ms(ref, got, pre, sr=16000):
    """How many ms later `ref` sits in `got` than expected (got was cut starting `pre` s before the expected spot)."""
    n = 1 << int(np.ceil(np.log2(len(ref) + len(got))))
    c = np.fft.irfft(np.fft.rfft(got, n) * np.conj(np.fft.rfft(ref, n)), n)[:len(got) - len(ref) + 1]
    k = int(np.argmax(c)); corr = c[k] / (np.linalg.norm(ref) * np.linalg.norm(got[k:k + len(ref)]) + 1e-9)
    return (k - int(round(pre * sr))) / sr * 1000, corr

SEARCH = 0.25

def check(d, cfg, a):
    final = a[a.index("--check") + 1]; tag = arg(a, "--tag", "v1"); off = float(arg(a, "--offset", "0"))
    tl = load(d, "cut", f"timeline_{tag}.json") or sys.exit(f"no cut/timeline_{tag}.json")
    keys = [s["key"] for s in tl]; bad = 0
    for ins in cfg.get("inserts", []):
        mine = [i for i, s in enumerate(tl) if s["clip"] == ins["key"]]
        if not mine: print(f"{ins['key']}: not in timeline_{tag}"); continue
        around = sorted({max(0, mine[0] - 1), *mine, min(len(tl) - 1, mine[-1] + 1)})
        print(f"{ins['key']}: source vs export, around the insert")
        for i in around:
            s = tl[i]; L = s["a_out"] - s["a_in"]
            for frac in ((0.15, 0.85) if L > 4 else (0.5,)):
                src_t = s["a_in"] + L * frac - 1.0; out_t = s["out_start"] + (src_t - s["a_in"]) + off
                if src_t < s["a_in"]: src_t, out_t = s["a_in"], s["out_start"] + off
                pre = min(SEARCH, out_t)
                ref = pcm(s["path"], src_t, 2.0); got = pcm(final, out_t - pre, 2.0 + pre + SEARCH)
                if len(ref) < 8000 or len(got) <= len(ref): continue
                ms, corr = lag_ms(ref, got, pre)
                flag = "" if abs(ms) <= 5 or corr < 0.5 else "  CHECK"
                bad += bool(flag)
                print(f"  {keys[i]:10} @ {out_t:8.2f}s  lag {ms:+7.1f} ms  (match {corr:.2f}){flag}"
                      + ("  weak match: read this one by ear" if corr < 0.5 else ""))
    print(f"{bad} probes off by more than 5 ms" if bad else "all probes within 5 ms")

def main():
    d, cfg = ws(); a = sys.argv
    if "--check" in a: check(d, cfg, a)
    elif len(a) > 2: insert(d, cfg, a)
    else: sys.exit(__doc__)

if __name__ == "__main__":
    main()
