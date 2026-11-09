"""Frame grids for visual review. The only way to actually SEE a render: read the PNGs this writes.

Usage:
  python review.py <video> <out.png> t1 t2 ...          # frames at given times
  python review.py <video> <out.png> a:b:step           # a range
  python review.py <video> <out.png> --beats <ws> <name> # auto: every scene change (+0.15 s and +1.2 s) and every
                                                         # picture cut (-2 / +2 frames) from the HyperFrames timeline
Options: --cols 6 --w 240 (thumb width). Keep <= 18 frames per sheet so each frame stays legible.
"""
import io, json, os, re, subprocess, sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eye_strip import font

def beat_times(d, name):
    html = open(os.path.join(d, "hf", name, "index.html"), encoding="utf-8").read()
    ts = [float(t) for sid, t in re.findall(r"tl\.set\('#(\w+)',\{opacity:1\},([\d.]+)\)", html) if sid != "edge"]  # scene shown
    ts += [float(t) for t in re.findall(r"tl\.fromTo\('#(?:facewrap|full)',[^;]*?,([\d.]+)\);", html)]  # layout moves
    tl = json.load(open(os.path.join(d, "cut", sorted(f for f in os.listdir(os.path.join(d, "cut")) if f.startswith("timeline_"))[-1])))
    out = []
    for t in sorted(set(ts)): out += [t + 0.15, t + 1.2]
    for s in tl[1:]: out += [s["v_out_start"] - 0.035, s["v_out_start"] + 0.035]
    return sorted({round(x, 2) for x in out if x > 0})

def main():
    a = sys.argv[1:]; vid, out = a[0], a[1]; rest = a[2:]
    cols, tw = 6, 240
    if "--cols" in rest: i = rest.index("--cols"); cols = int(rest[i + 1]); del rest[i:i + 2]
    if "--w" in rest: i = rest.index("--w"); tw = int(rest[i + 1]); del rest[i:i + 2]
    if "--beats" in rest: i = rest.index("--beats"); ts = beat_times(rest[i + 1], rest[i + 2])
    else:
        ts = []
        for r in rest:
            if ":" in r:
                x, y, st = map(float, r.split(":")); v = x
                while v <= y + 1e-6: ts.append(round(v, 3)); v += st
            else: ts.append(float(r))
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", vid], capture_output=True, text=True).stdout.strip().split(",")
    W, H = int(probe[0]), int(probe[1]); th = int(tw * H / W); F = font(16)
    for part in range(0, len(ts), 18):
        chunk = ts[part:part + 18]; rows = (len(chunk) + cols - 1) // cols
        sh = Image.new("RGB", (cols * (tw + 6), rows * (th + 24)), (0, 0, 0)); dr = ImageDraw.Draw(sh)
        for k, t in enumerate(chunk):
            b = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", vid, "-frames:v", "1", "-vf", f"scale={tw}:{th}", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
            if not b: continue
            x, y = (k % cols) * (tw + 6), (k // cols) * (th + 24)
            sh.paste(Image.open(io.BytesIO(b)).convert("RGB"), (x, y + 22)); dr.text((x + 2, y + 2), f"{t:.2f}s", font=F, fill=(255, 220, 120))
        o = out if part == 0 else out.replace(".png", f"_{part // 18 + 1}.png")
        sh.save(o); print("wrote", o, len(chunk), "frames")

if __name__ == "__main__":
    main()
