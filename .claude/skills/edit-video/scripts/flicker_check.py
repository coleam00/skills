"""Find flicker the eye catches: small areas of a frame that go bright-dark-bright across consecutive frames.

uv run --project $S python $S/flicker_check.py <video> [--crop x:y:w:h] [--thr 8] [--limit 0.0008] [--top 12]

A pixel "reverses" at frame t when it moves up then down (or down then up) by at least --thr of 255 on both steps.
A flickering pixel reverses again and again; one reversal is just a dissolve or an object passing, so the score is the
share of pixels with at least --n reversals inside the last --win frames. Reports each second's worst frame and fails when
any frame exceeds --limit. Measure a known flickering render first when you change a setting: a check that never fails proves nothing.
"""
import argparse, subprocess, sys
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("video"); ap.add_argument("--crop"); ap.add_argument("--thr", type=float, default=8.0)
ap.add_argument("--limit", type=float, default=0.0005); ap.add_argument("--n", type=int, default=3); ap.add_argument("--win", type=int, default=12); ap.add_argument("--top", type=int, default=12)
ap.add_argument("--w", type=int, default=480); ap.add_argument("--ss", type=float); ap.add_argument("--t", type=float)
a = ap.parse_args()

probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate", "-of", "csv=p=0", a.video], capture_output=True, text=True).stdout.strip().split(",")
vw, vh = int(probe[0]), int(probe[1]); n, d = probe[2].split("/"); fps = int(n) / int(d)
cw, ch = vw, vh; filt = []
if a.crop:
    x, y, cw, ch = map(int, a.crop.split(":")); filt.append(f"crop={cw}:{ch}:{x}:{y}")
W = a.w; H = round(W * ch / cw / 2) * 2
filt += [f"scale={W}:{H}:flags=area", "format=gray"]
cmd = ["ffmpeg", "-v", "error"]
if a.ss is not None: cmd += ["-ss", str(a.ss)]
cmd += ["-i", a.video]
if a.t is not None: cmd += ["-t", str(a.t)]
cmd += ["-vf", ",".join(filt), "-f", "rawvideo", "-"]
p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
size = W * H; prev = cur = None; scores = []; means = []; hist = []; acc = np.zeros((H, W), np.int16)
while True:
    b = p.stdout.read(size)
    if len(b) < size: break
    f = np.frombuffer(b, np.uint8).reshape(H, W).astype(np.int16)
    means.append(float(f.mean()))
    if cur is not None and prev is not None:
        d0, d1 = cur - prev, f - cur
        rev = ((d0 > a.thr) & (d1 < -a.thr)) | ((d0 < -a.thr) & (d1 > a.thr))
        acc += rev; hist.append(rev)
        if len(hist) > a.win: acc -= hist.pop(0)
        scores.append(float((acc >= a.n).mean()))
    prev, cur = cur, f
p.wait()
s = np.array(scores) if scores else np.zeros(1); t0 = a.ss or 0.0
secs = {}
for i, v in enumerate(s):
    k = int(t0 + (i + 1) / fps); secs[k] = max(secs.get(k, 0.0), float(v))
bad = int((s > a.limit).sum())
print(f"{len(s)} frames, thr {a.thr}, limit {a.limit}: {bad} frames over; max {s.max():.5f}, p99 {np.percentile(s, 99):.5f}, median {np.median(s):.6f}")
for k, v in sorted(secs.items(), key=lambda kv: -kv[1])[:a.top]:
    print(f"  {int(k // 60)}:{int(k % 60):02d}  worst {v:.5f}")
sys.exit(1 if bad else 0)
