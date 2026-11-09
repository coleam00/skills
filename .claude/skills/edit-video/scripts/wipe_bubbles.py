"""Bubble crops across every wipe: from 0.4 s before the last word to past the picture cut, 0.067 s apart, one row per join.
Usage: python wipe_bubbles.py <ws> <tag>   (after transitions.py render; reads <ws>/transitions_<tag>.log, so run render as
  `transitions.py <ws> render --tag <tag> > <ws>/transitions_<tag>.log`). Read EVERY row: eyes on the lens in every frame.
Reads the wipe list from transitions_<tag>.log ("speech A | B ... wipe+whoosh @ T"). One row per join -> check/wipe_bubbles_<tag>.png"""
import io, json, re, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw

if any(a in ("-h", "--help") for a in sys.argv[1:]) or len(sys.argv) < 3: sys.exit(print(__doc__.strip()))
WS = Path(sys.argv[1]); tag = sys.argv[2]
vid = WS / "cut" / f"transitions_{tag}.mp4"
cx, cy, r = json.loads((WS / "config.json").read_text())["bubble"]
rows = []
for line in (WS / f"transitions_{tag}.log").read_text().splitlines():
    m = re.search(r"(\S+) -> (\S+): speech ([\d.]+) \| ([\d.]+).*@ ([\d.]+)", line)
    if not m: continue
    a, b, t = float(m[3]), float(m[4]), float(m[5])
    ts = [a - 0.4 + k * 0.067 for k in range(int((b + 0.1 - (a - 0.4)) / 0.067) + 1)]
    S = 120; row = Image.new("RGB", (150 + len(ts) * (S + 2), S + 16), "white"); d = ImageDraw.Draw(row)
    d.text((3, 40), f"{m[1]}->{m[2]}\nmid {t:.2f}", fill="black")
    for i, tt in enumerate(ts):
        png = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{tt:.3f}", "-i", str(vid), "-frames:v", "1", "-vf",
                              f"crop={2*r}:{2*r}:{cx-r}:{cy-r},scale={S}:{S}", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
        x = 150 + i * (S + 2); row.paste(Image.open(io.BytesIO(png)).convert("RGB"), (x, 16))
        lab = "MID" if abs(tt - t) < 0.04 else ("w" if tt <= a else ("" if tt < b else "next"))
        d.text((x + 2, 2), f"{tt:.2f} {lab}", fill="red" if lab == "MID" else "black")
    rows.append(row)
W_ = max(r_.width for r_ in rows)
sheet = Image.new("RGB", (W_, sum(r_.height for r_ in rows)), "white"); y = 0
for r_ in rows: sheet.paste(r_, (0, y)); y += r_.height
out = WS / "check" / f"wipe_bubbles_{tag}.png"; sheet.save(out); print("wrote", out, len(rows), "rows")
