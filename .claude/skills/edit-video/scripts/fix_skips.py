"""Repair recorder audio buffer skips (CPU overload) in the face clips: find and smooth, never retime.

Usage: uv run --project $S python fix_skips.py <ws> [--out <dir>] [--th 8] [--report] [--long "<folder>/<glob>"]

What the defect is: when a screen recorder's audio thread is starved it drops whole 1024-frame buffers. Nothing
goes silent; the waveform jumps at one sample and the speech lurches ahead, heard as a cut or stutter. Zero-run and
level-dip checks find nothing. Whether every file carries the skips depends on the recorder: on one setup the face,
screen and composite files all had them, but on another (OBS with Source Record, Fable 11/13) only the separately
recorded camera and screen files did, and the main composite recording was clean.
--report --long "<glob>": score each clip AND its longer recording of the same take (the composite, paired in order,
exactly like pad_takes.py) and print both. When the long files are clean and the clips are not, do not smooth: rebuild
every clip on the long file's audio, which RESTORES the dropped audio instead of hiding the click:
  pad_takes.py <ws> --long "<glob>" --apply --all [--inset x,y,w,h]
then re-run transcribe.py and cutpoints.py and compare the new outs with the old cuts.json (see cutting.md).
How it is found: an LPC residual (order 20, fitted on the previous 20 ms) cancels normal speech; a skip is a residual
spike far above the local level. Skips sit on the take's 1024-sample buffer grid, so the grid phase is the 3-sample
window holding the most big spikes, and only grid boundaries are scored (score > --th in speech). Natural spikes
rarely land within a sample of the grid; one 20-minute recording: 52 of 343 big spikes in one window where chance predicts 1.
How it is repaired: the step is what is heard (a click/cut). The sample after the skip is predicted from the two before
it and the difference is relaxed to zero over 3 ms, so value and slope are continuous at the joint. Timing never
changes, so picture sync cannot drift; outside those 3 ms no sample moves. The skipped audio itself is gone.
Writes <out>/<clip file name> (video stream-copied, FLAC audio) and <ws>/skips.json. Point config.json clips at <out>
for the repaired cut; the originals stay for an unrepaired version.
"""
import collections, json, os, subprocess, sys
import numpy as np
from scipy.linalg import solve_toeplitz
from scipy.signal import lfilter
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ws

SR, ORD, B = 48000, 20, 960

def pcm(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
    ch = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels", "-of", "csv=p=0", path],
                            capture_output=True, text=True).stdout.strip() or 1)
    return np.frombuffer(raw, np.float32).astype(np.float64).reshape(-1, ch)

def residual(x):
    e = np.zeros_like(x)
    for i in range(B, len(x) - B, B):
        h = x[i - B:i] * np.hanning(B); r = np.correlate(h, h, "full")[B - 1:B + ORD]
        if r[0] < 1e-9: continue
        try: a = solve_toeplitz(r[:ORD], r[1:ORD + 1])
        except Exception: continue
        seg = x[i - ORD:i + B]; e[i:i + B] = (seg - lfilter(np.r_[0, a], [1], seg))[ORD:]
    return e

def find(mono, th):
    e = np.abs(residual(mono)); env = np.sqrt(np.convolve(mono * mono, np.ones(960) / 960, "same"))
    sc = e / (np.convolve(e, np.ones(960) / 960, "same") + 1e-6)
    big = np.where((sc > 12) & (env > 0.01))[0]
    hist = collections.Counter(int(i) % 1024 for i in big)
    ph = max(range(1024), key=lambda p: hist[p] + hist[(p - 1) % 1024] + hist[(p + 1) % 1024])
    support = hist[ph] + hist[(ph - 1) % 1024] + hist[(ph + 1) % 1024]
    hits = []
    for g in range(ph, len(mono) - 2, 1024):
        lo = max(0, g - 3); k = lo + int(np.argmax(sc[lo:g + 4]))
        if sc[k] > th and env[k] > 0.006: hits.append((k, float(sc[k])))
    return hits, ph, support, len(big)

def period(x):
    x = x - x.mean(); r = np.correlate(x, x, "full")[len(x) - 1:]
    lo, hi = SR // 400, SR // 70
    if r[0] <= 0: return None
    k = lo + int(np.argmax(r[lo:hi]))
    return k if r[k] / r[0] > 0.45 else None                       # voiced only

def repair(a, k):
    """a: (n, ch) float; k: the residual spike, within a few samples of the jump."""
    mono = a.mean(1)
    # snap to the exact jump: the residual peak lands 1-3 samples off it, and a jump left inside the crossfade is only
    # halved, not removed (a first pass halved it and every "after" tile still showed an edge). The jump is the largest
    # break in the second difference within +-6 samples; k becomes the first sample after it.
    # (the second difference peaks on BOTH samples around a step and argmax took the later one: use the step itself)
    lo = k - 6; d1 = np.abs(np.diff(mono[lo - 1:k + 8])); k = lo + int(np.argmax(d1))
    # 1) remove the STEP, which is what is heard (a broadband click): predict the sample after the skip from the two before
    # it, and relax the difference to zero over 3 ms (raised cosine). Exact continuity of value and slope at the joint,
    # no sample outside the 3 ms moves. Pitch-period splicing was tried first and left steps where the voice was in a
    # slow swing with no repeating cycle to match.
    T = int(0.003 * SR)
    if k < 3 or k + T > len(a): return False
    pred = 2 * a[k - 1] - a[k - 2]                                   # per channel
    c = pred - a[k]
    h = (0.5 + 0.5 * np.cos(np.pi * np.arange(T) / T))[:, None]   # 1 -> 0
    a[k:k + T] += c[None, :] * h
    return True

def step(mono, k):
    """Size of the step at a skip (after snapping), in units of the typical sample-to-sample curvature just before it."""
    lo = k - 6; d1 = np.abs(np.diff(mono[lo - 1:k + 8])); k = lo + int(np.argmax(d1))
    return abs(mono[k] - (2 * mono[k - 1] - mono[k - 2])) / (np.median(np.abs(np.diff(mono[k - 240:k - 3], 2))) + 1e-6)

def main():
    d, cfg = ws(); args = sys.argv
    th = float(args[args.index("--th") + 1]) if "--th" in args else 8.0
    out = args[args.index("--out") + 1] if "--out" in args else os.path.join(os.path.dirname(cfg["clips"][0]["path"]) + "_fixed")
    os.makedirs(out, exist_ok=True); report = {}
    import glob
    longs = sorted(glob.glob(args[args.index("--long") + 1])) if "--long" in args else []
    if longs and len(longs) != len(cfg["clips"]): sys.exit(f"--long matched {len(longs)} files for {len(cfg['clips'])} clips: narrow the glob")
    # grid concentration: how many of the big residual spikes sit on one 1024-sample phase, against the ~3/1024 that
    # chance puts there. Speech alone stays near 1x; buffer skips stack up on the grid (the Fable camera files: up to 100x+)
    conc = lambda sup, nb: sup / max(1.0, 3 * nb / 1024)
    cmp_rows = []
    for c in cfg["clips"]:
        if c["key"].startswith("m"): continue                      # inserted segments were mastered separately
        a = pcm(c["path"]); hits, ph, sup, nb = find(a.mean(1), th)
        before = [step(a.mean(1), k) for k, _ in hits]
        for _ in range(3):        # a skip can step over two samples: repair again only where a real step is left (> 6x)
            for k, _ in hits:
                if k > 300 and step(a.mean(1), k) > 6: repair(a, k)
        after = [step(a.mean(1), k) for k, _ in hits]; done = len(hits)
        report[c["key"]] = {"phase": ph, "support": sup, "big": nb,
                            "skips": [[round(k / SR, 4), round(s, 1), round(b, 1), round(f, 1)] for (k, s), b, f in zip(hits, before, after)]}
        print(f"{c['key']}: grid phase {ph} ({sup} of {nb} big spikes), {len(hits)} skips; step median "
              f"{np.median(before) if before else 0:.0f}x -> {np.median(after) if after else 0:.1f}x, over 10x after: {sum(f > 10 for f in after)}", flush=True)
        if longs:
            L = longs[cfg["clips"].index(c)]; lh, _, lsup, lnb = find(pcm(L).mean(1), th)
            cmp_rows.append((c["key"], conc(sup, nb), len(hits), conc(lsup, lnb), len(lh)))
            print(f"      long {os.path.basename(L)}: grid concentration {conc(lsup, lnb):.1f}x ({len(lh)} skips)  vs clip {conc(sup, nb):.1f}x", flush=True)
        if "--report" in args: continue
        wav = os.path.join(out, os.path.splitext(os.path.basename(c["path"]))[0] + "_fixed.wav")
        sf.write(wav, a, SR, subtype="FLOAT")
        dst = os.path.join(out, os.path.basename(c["path"]))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", c["path"], "-i", wav, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                        "-c:a", "flac", dst], check=True)
        os.remove(wav)
    json.dump(report, open(os.path.join(d, "skips.json"), "w"), indent=1)
    if cmp_rows:
        bad_clip = [r for r in cmp_rows if r[1] >= 5]; bad_long = [r for r in cmp_rows if r[3] >= 5]
        print(f"SKIPS  clips with skips (>= 5x on the grid): {len(bad_clip)} of {len(cmp_rows)}   long files: {len(bad_long)} of {len(cmp_rows)}")
        if bad_clip and len(bad_long) < len(bad_clip) / 3:
            print("  -> the long recordings are clean: rebuild the clips on their audio (restores what was dropped):\n"
                  "     pad_takes.py <ws> --long \"<same glob>\" --apply --all [--inset x,y,w,h], then transcribe.py, cutpoints.py")

if __name__ == "__main__":
    main()
