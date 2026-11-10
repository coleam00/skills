"""Where the face is in the CUT, every half second: cut/facetrack_<tag>.json.

Usage: uv run --project $S python face_track.py <ws> [--tag v1] [--step 0.5]

faces.json is one box per clip in source pixels, so it knows nothing about the punch-in alternation or the speaker
moving during a take. The face panel crops the cut, and a fixed crop put the face off centre in some spans. engine.Track reads this file and keeps the
panel on the face: each shrink lands on where the face is, and the crop follows it while the panel is up.

Output: {"step": s, "track": [[t, cx, cy, h], ...]} in cut pixels, gaps filled from the neighbours, median-smoothed.
"""
import os, sys
import cv2
import numpy as np
from common import load, save, ws

def main():
    d, cfg = ws(); a = sys.argv
    tag = a[a.index("--tag") + 1] if "--tag" in a else "v1"
    step = float(a[a.index("--step") + 1]) if "--step" in a else 0.5
    src = os.path.join(d, "cut", f"clean_{tag}.mp4")
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(src); fps = cap.get(cv2.CAP_PROP_FPS); n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W = cap.get(cv2.CAP_PROP_FRAME_WIDTH); sc = 640 / W; every = max(1, round(step * fps)); raw = []
    for i in range(n):
        if i % every:
            if not cap.grab(): break
            continue
        ok, f = cap.read()
        if not ok: break
        g = cv2.cvtColor(cv2.resize(f, None, fx=sc, fy=sc), cv2.COLOR_BGR2GRAY)
        fs = det.detectMultiScale(g, 1.08, 6, minSize=(60, 60))
        if len(fs):
            x, y, w, h = max(fs, key=lambda b: b[2]); raw.append([i / fps, (x + w / 2) / sc, (y + h / 2) / sc, h / sc])
        else:
            raw.append([i / fps, None, None, None])
    ok = [r for r in raw if r[1] is not None]
    if not ok: sys.exit("no face found in the cut")
    t_ok = np.array([r[0] for r in ok]); cols = np.array([r[1:] for r in ok])
    t_all = np.array([r[0] for r in raw])
    filled = np.stack([np.interp(t_all, t_ok, cols[:, k]) for k in range(3)], axis=1)
    k = 5; pad = np.pad(filled, ((k // 2, k // 2), (0, 0)), mode="edge")
    smooth = np.stack([np.median(pad[j:j + k], axis=0) for j in range(len(filled))])
    track = [[round(float(t), 3)] + [round(float(v), 1) for v in row] for t, row in zip(t_all, smooth)]
    save({"step": step, "track": track}, d, "cut", f"facetrack_{tag}.json")
    print(f"facetrack_{tag}.json: {len(track)} samples, face found in {len(ok)} ({100 * len(ok) / len(raw):.0f}%), "
          f"cx {np.percentile(cols[:, 0], 5):.0f}-{np.percentile(cols[:, 0], 95):.0f}, cy {np.percentile(cols[:, 1], 5):.0f}-{np.percentile(cols[:, 1], 95):.0f}")

if __name__ == "__main__":
    main()
