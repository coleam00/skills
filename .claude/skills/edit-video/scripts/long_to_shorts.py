"""Cut vertical Shorts' sources out of a finished long-form edit that has separate camera and screen tracks.

Usage: uv run --project $S python long_to_shorts.py <ws> --tag v3 --short s1=14.25-48.75 [--short s2=328.3-335.9,358.2-404.9]
                                                     [--band 1080x760] [--nudge 0] [--out <ws>/shorts]

Times are seconds on the long-form OUTPUT timeline of <tag> (cut/clean_<tag>.mp4 and cut/screen_<tag>.mp4, the
validated cut, so the joins, splices and level work are already done). Several spans make one Short (joined in order).
Pick spans that start and end on the cut's own segment boundaries where you can (timeline_<tag>.json out_start /
out_end); a span that starts mid-take gets its exact in point later from align.py in the Short's workspace.

Per Short <name>, under <out>/src/<name>/:
  faces/<name>-face NN.mkv    the camera as a <band> band (default 1080x760) cropped at NATIVE pixels around the face
                              (never upscaled: a 1080-wide crop of a 1920x1080 camera stays sharp), PCM audio
  screens/<name>-screen NN.mkv  the full-resolution screen track for the same span, carrying the same audio, so
                              assemble.py --screen syncs it at lag 0
  faces/layout.json           {"mode": "stacked", 1080x1920, face at the bottom}: init_workspace.py reads it
  check_<name>.png            the band's first frame with a centre line: READ it; if the face is off centre, re-run
                              with --nudge <px> (positive moves the crop right). The Haar box from faces.json sits
                              ~50 px off centre on some faces (Fable 11/13).
Then, per Short (each is its own workspace; see references/shorts-from-long.md):
  init_workspace.py <out>/src/<name>/faces --out <out>/<name>
  transcribe.py, cutpoints.py, pauses.py (usually nothing left: the long-form already removed pauses)
  assemble.py <out>/<name> --no-punch --screen <out>/src/<name>/screens --screen-native
  validate_cut.py, captions.py (fixes: copy the long-form's caption_fixes.json), the B-roll page in the stacked layout
  (hf/screenband.py shows the live screen in the graphics band), render, finalize.py, video_review.py per Short.
The long-form workspace and its files are only read.
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import load, probe, ws


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: sys.exit(r.stderr[-1500:])


def spans_of(v):
    out = []
    for part in v.split(","):
        a, b = part.split("-"); out.append((float(a), float(b)))
    return out


def main():
    d, cfg = ws(); a = sys.argv
    tag = a[a.index("--tag") + 1] if "--tag" in a else "v1"
    bw, bh = (int(x) for x in (a[a.index("--band") + 1] if "--band" in a else "1080x760").split("x"))
    nudge = int(a[a.index("--nudge") + 1]) if "--nudge" in a else 0
    out = os.path.abspath(a[a.index("--out") + 1]) if "--out" in a else os.path.join(d, "shorts")
    shorts = [x.split("=", 1) for i, x in enumerate(a) if i and a[i - 1] == "--short"]
    if not shorts: sys.exit(__doc__)
    clean = os.path.join(d, "cut", f"clean_{tag}.mp4")
    scr = os.path.join(d, (cfg.get("screen_cuts") or {}).get(tag, f"cut/screen_{tag}.mp4"))
    if not os.path.exists(clean): sys.exit(f"no {clean}: assemble the long-form first")
    if not os.path.exists(scr): sys.exit(f"no screen track {scr}: this is for long-forms built with assemble.py --screen")
    tl = load(d, "cut", f"timeline_{tag}.json"); faces = load(d, "faces.json") or {}
    cw, ch = probe(clean)["w"], probe(clean)["h"]
    if bw > cw or bh > ch: sys.exit(f"band {bw}x{bh} is bigger than the camera {cw}x{ch}: it would be upscaled")
    fps = cfg["fps"]
    for name, val in shorts:
        sp = spans_of(val); fd = os.path.join(out, "src", name, "faces"); sd = os.path.join(out, "src", name, "screens")
        os.makedirs(fd, exist_ok=True); os.makedirs(sd, exist_ok=True)
        total = 0.0
        for i, (t0, t1) in enumerate(sp, 1):
            seg = next((s for s in tl if s["out_start"] - 1e-3 <= t0 < s["out_end"]), tl[0])
            f = faces.get(seg["clip"]) or {"cx": cw / 2}
            x0 = max(0, min(cw - bw, int(round(f["cx"] - bw / 2 + nudge))))
            fo = os.path.join(fd, f"{name}-face {i:02d}.mkv"); so = os.path.join(sd, f"{name}-screen {i:02d}.mkv")
            cut = ["-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}"]
            run(["ffmpeg", "-v", "error", "-y", *cut, "-i", clean, "-vf", f"crop={bw}:{bh}:{x0}:0", "-c:v", "libx264", "-crf", "12",
                 "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "pcm_s16le", "-ar", "48000", fo])
            run(["ffmpeg", "-v", "error", "-y", *cut, "-i", scr, *cut, "-i", clean, "-map", "0:v:0", "-map", "1:a:0",
                 "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(fps),
                 "-c:a", "pcm_s16le", "-ar", "48000", so])
            total += t1 - t0
            print(f"{name} part {i}: {t0:.2f}-{t1:.2f} ({t1 - t0:.1f} s, starts in {seg['key']})  crop x={x0} of {cw}  -> {os.path.basename(fo)}")
        json.dump({"mode": "stacked", "w": 1080, "h": 1920, "face_side": "bottom", "seam": 1920 - bh},
                  open(os.path.join(fd, "layout.json"), "w"), indent=1)
        # three frames across the first part, not one: a single frame caught the speaker leaning and invited a wrong
        # --nudge (MongoDB Short 2, 11/14). Judge the middle of the three.
        chk = os.path.join(out, f"check_{name}.png"); p1 = os.path.join(fd, f"{name}-face 01.mkv"); d1 = probe(p1)["dur"]
        tiles = []
        for k, tt in enumerate((0.5, d1 / 2, max(0.5, d1 - 1.0))):
            tf = os.path.join(out, f"_chk_{name}_{k}.png"); tiles.append(tf)
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{tt:.2f}", "-i", p1, "-frames:v", "1",
                 "-vf", f"drawbox=x={bw // 2 - 1}:y=0:w=2:h={bh}:color=red@0.8:t=fill,scale=540:-2", tf])
        run(["ffmpeg", "-v", "error", "-y", *sum((["-i", t_] for t_ in tiles), []), "-filter_complex", "hstack=inputs=3", chk])
        for t_ in tiles: os.remove(t_)
        flag = "" if 25 <= total <= 62 else "   WARN outside the usual 30-60 s for a Short"
        print(f"{name}: {total:.1f} s in {len(sp)} part(s). READ {chk} (start, middle, end: face centred on the red line?){flag}")
    print(f"\nNext, per Short: init_workspace.py {out}/src/<name>/faces --out {out}/<name>, then the steps in "
          f"references/shorts-from-long.md (assemble.py with --screen {out}/src/<name>/screens --screen-native).")


if __name__ == "__main__":
    main()
