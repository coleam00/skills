"""Eye-region frame strips at every segment boundary (last 0.5 s of each tail, first 0.4 s of each head;
a head after a split edit starts where its picture really starts, video_out's lead earlier).

Usage: uv run --project $S python eye_strip.py <ws> [--band y0:y1] [--only <segment>] [--tail <secs>]
Writes <ws>/check/eyes_<segment>.png (every 2nd frame, timestamped, cut point marked). Read them: if the speaker
looks down/away before the out point, set "video_out" for that segment in overrides.json to the last frame with
eyes on the lens; assemble.py turns it into a split edit (audio continues, picture cuts early to the next take).
If the eyes are already away for the whole 0.5 s, widen that one strip to find the last good frame:
--only c02_s01 --tail 3 (about 36 frames over the last 3 s; writes eyes_<segment>_tail_wide.png).
"""
import os, subprocess, sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import find_font, load, p, ws

def font(sz):
    f = find_font()
    return ImageFont.truetype(f, sz) if f else ImageFont.load_default()

def main():
    d, cfg = ws(); W, H, fps = cfg["w"], cfg["h"], cfg["fps"]
    faces = load(d, "faces.json")
    if faces is None:   # eye strips run before assemble.py: measure the faces here (same file assemble.py reads)
        from assemble import measure_faces
        from common import save
        faces = measure_faces(d, cfg, load(d, "cuts.json")["segments"]); save(faces, d, "faces.json")
    F = font(16)
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    tail = float(sys.argv[sys.argv.index("--tail") + 1]) if "--tail" in sys.argv else 0.5
    step = max(2, round(tail * fps / 36)) if tail > 0.5 else 2
    ov = load(d, "overrides.json", default={}) or {}
    segs = load(d, "cuts.json")["segments"]
    for k, s in enumerate(segs):
        if only and s["key"] != only: continue
        # a split edit on the previous segment starts THIS picture early by the same lead: show the real picture in
        prev = segs[k - 1] if k else None
        lead = max(0.0, prev["out"] - ov.get("video_out", {}).get(prev["key"], prev["out"])) if prev else 0.0
        fc = faces.get(s["clip"])
        cy = int(fc["cy"] - fc["h"] * 0.12) if fc else int(H * 0.36)
        # crop to the eyes of the measured face (a fixed share of the frame made 16:9 eyes a few pixels tall)
        cw = min(W, int(fc["w"] * 1.5)) if fc else int(W * 0.6); bh = min(H, int(fc["h"] * 0.42)) if fc else int(H * 0.14)
        y0 = max(0, min(H - bh, cy - bh // 2)); x0 = int((fc["cx"] if fc else W / 2) - cw / 2); x0 = max(0, min(W - cw, x0))
        wins = [("tail_wide" if tail > 0.5 else "tail", s["out"] - tail, s["out"] + 0.1, s["out"], step)]
        if tail <= 0.5: wins.append(("head", s["in"] - lead - 0.05, s["in"] - lead + 0.4, s["in"] - lead, 2))
        for tag, t0, t1, mark, n in wins:
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t0):.3f}", "-t", f"{t1 - max(0, t0):.3f}", "-i", s["path"], "-vf",
                                  f"select='not(mod(n\\,{n}))',crop={cw}:{bh}:{x0}:{y0},scale=320:{int(320 * bh / cw)}", "-vsync", "0",
                                  "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
            th = int(320 * bh / cw)
            if not raw: continue
            fr = np.frombuffer(raw, np.uint8).reshape(-1, th, 320, 3); cols = 6
            sh = Image.new("RGB", (cols * 324, ((len(fr) + cols - 1) // cols) * (th + 22)), (0, 0, 0)); dr = ImageDraw.Draw(sh)
            for i, f in enumerate(fr):
                tt = max(0, t0) + i * n / fps; x, y = (i % cols) * 324, (i // cols) * (th + 22)
                sh.paste(Image.fromarray(f), (x, y + 20)); hit = i == int(np.argmin([abs(max(0, t0) + j * n / fps - mark) for j in range(len(fr))]))
                dr.text((x + 2, y + 2), f"{tt:.3f}{' CUT' if hit else ''}", font=F, fill=(255, 80, 80) if hit else (230, 230, 230))
            sh.save(p(d, "check", f"eyes_{s['key']}_{tag}.png"))
    print("wrote", os.path.join(d, "check"), "eyes_*.png")

if __name__ == "__main__":
    main()
