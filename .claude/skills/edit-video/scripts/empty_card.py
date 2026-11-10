"""Find stretches where the 16:9 face-panel layout shows an EMPTY card: the panel is up, the card has nothing on it.

Usage: python empty_card.py <video.mp4> [--fps 3] [--min 1.0]   (run it on the 6 fps / 3 fps preview)
       python empty_card.py <video.mp4> --ws <ws> [--min 2.0]  (stacked layout: the graphics band instead of the card)

A scene that enters before its first spoken word leaves the viewer looking at a blank card (one long-form cut
had 14 s of an empty card and several 2-5 s blanks). Start the scene ~0.5 s before its first
element instead. Sparse scenes (one small window, a single chip) can show up here too: look at each before changing it.
Geometry is the engine's 1920x1080 panel layout (card 42,111 1524x858; panel 1609,360 269x359).
--ws <ws> with a stacked layout (config.json "layout") checks the graphics band above (or below) the captions
instead: the face is always in its own band there, so an empty graphics band reads as unfinished; nothing over
~2 s may be empty (EMPTY BAND).
"""
import subprocess, sys
import numpy as np

def main():
    if any(x in ("-h", "--help") for x in sys.argv[1:]) or len(sys.argv) < 2: sys.exit(print(__doc__.strip()))
    a = sys.argv; v = a[1]
    fps = float(a[a.index("--fps") + 1]) if "--fps" in a else 3.0
    mn = float(a[a.index("--min") + 1]) if "--min" in a else 1.0
    G = None
    if "--ws" in a:
        import json, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from common import stacked
        G = stacked(json.load(open(os.path.join(a[a.index("--ws") + 1], "config.json"), encoding="utf-8")))
        if not G: sys.exit("--ws: this workspace has no stacked layout; run without --ws for the 16:9 panel layout")
    if G:   # the graphics band, between the canvas edge and the captions (captions are always on, so they are excluded)
        W, H = 270, round(270 * G["H"] / G["W"]); k = G["W"] / W
        y0, y1 = (40, G["cap_top"] - 10) if G["side"] == "bottom" else (G["cap_top"] + G["cap_h"] + 10, G["H"] - 40)
        cx0, cx1, cy0, cy1 = int(40 / k), int((G["W"] - 40) / k), int(y0 / k), int(y1 / k)
    else:
        W, H = 480, 270; k = 1920 / W
        cx0, cx1, cy0, cy1 = int(70 / k), int(1540 / k), int(140 / k), int(940 / k)
        px0, px1, py0, py1 = int(1609 / k), int(1878 / k), int(360 / k), int(719 / k)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", v, "-vf", f"fps={fps},scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)
    runs, cur = [], None
    label = "EMPTY BAND" if G else "EMPTY CARD"
    for i, f in enumerate(fr):
        card = f[cy0:cy1, cx0:cx1]
        empty = np.abs(np.diff(card, axis=1)).mean() < 1.2 and card.mean() < 60 and (G is not None or f[py0:py1, px0:px1].std() > 25)
        t = i / fps
        if empty and cur is None: cur = t
        if not empty and cur is not None:
            if t - cur >= mn: runs.append((cur, t))
            cur = None
    if cur is not None and len(fr) / fps - cur >= mn: runs.append((cur, len(fr) / fps))
    for s, e in runs: print(f"  {label} {s:7.1f}-{e:7.1f} ({e - s:.1f}s)")
    print(f"{len(runs)} {label.lower()} stretches of {mn}s+")

if __name__ == "__main__":
    main()
