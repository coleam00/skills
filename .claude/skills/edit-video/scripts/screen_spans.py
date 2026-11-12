"""Find where a recorded screen leaves its "home" app (the slides or diagram the talk is taught from) and goes to the
product (a browser, an editor, a terminal): the spans an animated insert replaces (references/screen-inserts.md).

Usage: python screen_spans.py <ws> --ref <seconds> --region x,y,w,h [--tag v1] [--every 0.5] [--thresh 12]

- --ref: a time in the cut screen track (cut/screen_<tag>.mp4) that shows the home app.
- --region: a part of the frame that only the home app draws and that stays the same while it is up (its own toolbar
  or tool palette), in source pixels; read one frame to pick it. Not a generic title or tab bar: an editor's dark title
  bar matched a diagram app's dark tab bar and two VS Code spans read as "home". Content changes inside the slide or
  diagram must not change this region either, or every new slide reads as "away".
Prints every AWAY run in cut time with the nearest picture joins (the recorded screen switches at the take joins, not
at the words, so an insert snaps to them) and writes check/screen_spans_<tag>.json. Check the runs on a contact
sheet: a dark product theme can pass for a dark slide, which is why the comparison is on the chrome, in colour.
"""
import json, os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import ws, save, load

def main():
    d, cfg = ws(); a = sys.argv
    tag = a[a.index("--tag") + 1] if "--tag" in a else "v1"
    if "--ref" not in a or "--region" not in a: sys.exit(__doc__)
    ref_t = float(a[a.index("--ref") + 1]); every = float(a[a.index("--every") + 1]) if "--every" in a else 0.5
    thresh = float(a[a.index("--thresh") + 1]) if "--thresh" in a else 12.0
    rx, ry, rw, rh = [int(v) for v in a[a.index("--region") + 1].split(",")]
    src = os.path.join(d, (cfg.get("screen_cuts") or {}).get(tag, f"cut/screen_{tag}.mp4"))
    if not os.path.exists(src): sys.exit(f"no screen track {src}: run assemble.py <ws> --screen <folder> --tag {tag} first")
    sw = max(1, rw // 4) // 2 * 2; sh = max(2, rh // 4) // 2 * 2       # quarter size is plenty to tell two UIs apart
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps=1/{every},crop={rw}:{rh}:{rx}:{ry},scale={sw}:{sh}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, sh, sw, 3).astype(np.float32)
    ref = fr[min(len(fr) - 1, int(round(ref_t / every)))]
    diff = np.abs(fr - ref).mean(axis=(1, 2, 3)); home = diff < thresh
    tl = load(d, "cut", f"timeline_{tag}.json") or []
    joins = [s["v_out_start"] for s in tl[1:]]
    near = lambda t: min(joins, key=lambda j: abs(j - t)) if joins else None
    runs, i = [], 0
    while i < len(home):
        if home[i]: i += 1; continue
        j = i
        while j < len(home) and not home[j]: j += 1
        s, e = i * every, j * every
        runs.append({"start": round(s, 2), "end": round(e, 2), "join_in": near(s), "join_out": near(e)}); i = j
    for r in runs:
        ji, jo = r["join_in"], r["join_out"]
        print(f"AWAY {r['start']:8.2f}-{r['end']:8.2f} ({r['end'] - r['start']:5.1f} s)   nearest joins {ji if ji is None else f'{ji:.2f}'} / {jo if jo is None else f'{jo:.2f}'}")
    print(f"{len(runs)} away span(s), {sum(r['end'] - r['start'] for r in runs):.1f} s of {len(home) * every:.1f} s; "
          f"home/away split at diff {thresh} (home median {np.median(diff[home]) if home.any() else float('nan'):.1f}, "
          f"away median {np.median(diff[~home]) if (~home).any() else float('nan'):.1f})")
    save({"tag": tag, "ref": ref_t, "region": [rx, ry, rw, rh], "every": every, "away": runs}, d, "check", f"screen_spans_{tag}.json")

if __name__ == "__main__":
    main()
