"""Create the edit workspace for a video or a folder of clips.

Usage: python init_workspace.py <video-file | folder-of-clips> [--out <workspace>] [--match "<glob>"] [--no-sync]

- Folder: every video file in it is a clip, ordered by the numbers in its name (1.mkv, 2.mkv, ... take_03.mp4, or a
  recorder's date-time stamp). --match keeps only the files whose name matches the glob: a recorder that writes the
  camera, the screen and a composite per take into one folder needs --match "*-face *" (or whatever names its camera
  files), and assemble.py --screen <that folder> then finds each take's screen file by name.
- Single file: one long source; cutpoints.py later splits it into segments at long pauses.
Creates <input>/_edit (or <file-dir>/_edit_<stem>) with config.json, syncs the skill's one shared Python environment
(scripts/.venv, from scripts/pyproject.toml), and prints the detected format. Never touches the source files.
"""
import fnmatch, glob, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import probe, save

VIDEO_EXT = (".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi")

def order_key(path):
    # every number, not just the first: in "Cam 2026-11-10 10-24-12" the first is the year, the same for every take
    nums = re.findall(r"\d+", os.path.basename(path))
    return (tuple(int(n) for n in nums) if nums else (1 << 30,), os.path.basename(path).lower())

def main():
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    src = os.path.abspath(args[0]); out = None
    if "--out" in args: out = os.path.abspath(args[args.index("--out") + 1])
    if os.path.isdir(src):
        pat = args[args.index("--match") + 1] if "--match" in args else "*"
        clips = sorted([f for f in glob.glob(os.path.join(src, "*")) if f.lower().endswith(VIDEO_EXT)
                        and fnmatch.fnmatch(os.path.basename(f).lower(), pat.lower())], key=order_key)
        out = out or os.path.join(src, "_edit")
    else:
        clips = [src]; out = out or os.path.join(os.path.dirname(src), "_edit_" + os.path.splitext(os.path.basename(src))[0])
    if not clips: sys.exit(f"No video files in {src}")
    infos = [probe(c) for c in clips]
    w, h, fps = infos[0]["w"], infos[0]["h"], infos[0]["fps"]
    odd = [os.path.basename(c) for c, i in zip(clips, infos) if (i["w"], i["h"], i["fps"]) != (w, h, fps)]
    os.makedirs(out, exist_ok=True)
    cfg = {"source": src, "mode": "clips" if len(clips) > 1 else "single", "w": w, "h": h, "fps": fps,
           "orientation": "vertical" if h > w else "horizontal",
           "clips": [{"key": f"c{k + 1:02d}", "path": c, "dur": round(i["dur"], 3), "audio": i["audio"]} for k, (c, i) in enumerate(zip(clips, infos))]}
    # split_wide.py leaves layout.json beside stacked face files: the cut is the camera band, the output a taller canvas
    lj = os.path.join(src if os.path.isdir(src) else os.path.dirname(src), "layout.json")
    if os.path.exists(lj):
        cfg["layout"] = json.load(open(lj, encoding="utf-8")); cfg["orientation"] = "vertical" if cfg["layout"]["h"] > cfg["layout"]["w"] else "horizontal"
    prev = os.path.join(out, "config.json")
    if os.path.exists(prev):  # keep any decisions already recorded (deliverables, brand, script)
        old = json.load(open(prev, encoding="utf-8")); cfg = {**old, **{k: cfg[k] for k in ("source", "mode", "w", "h", "fps", "orientation", "clips", "layout") if k in cfg}}
    save(cfg, out, "config.json")
    # One shared env for every edit: a uv project per workspace costs gigabytes and thousands of files per video.
    # --inexact keeps optional extras (cuda, align) that were installed earlier
    if "--no-sync" not in args:
        try:
            r = subprocess.run(["uv", "sync", "-q", "--inexact", "--project", HERE], capture_output=True, text=True)
            if r.returncode: print("WARN uv sync failed:", r.stderr[-800:])
        except FileNotFoundError:
            print("WARN uv not found: install it (https://docs.astral.sh/uv/) or run the scripts with your own Python env")
    print(f"workspace {out}")
    print(f"format    {w}x{h} @ {fps} fps  ({cfg['orientation']})  mode={cfg['mode']}  clips={len(clips)}")
    if cfg.get("layout"): L = cfg["layout"]; print(f"layout    {L['mode']}: the {w}x{h} camera band at native size in a {L['w']}x{L['h']} canvas, face {L.get('face_side', 'bottom')} (layout.json)")
    for c in cfg["clips"]: print(f"   {c['key']}  {c['dur']:7.2f}s  {os.path.basename(c['path'])}{'' if c['audio'] else '  (NO AUDIO)'}")
    if odd: print("WARN clips with a different size/fps (they will be conformed):", odd)
    names = " ".join(os.path.basename(c).lower() for c in clips)
    if "--match" not in args and any(k in names for k in ("face", "cam")) and "screen" in names:
        print('WARN camera AND screen files in one folder became clips: re-run with --match "<camera file glob>"')

if __name__ == "__main__":
    main()
