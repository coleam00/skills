"""Create the edit workspace for a video or a folder of clips.

Usage: python init_workspace.py <video-file | folder-of-clips> [--out <workspace>] [--no-sync]

- Folder: every video file in it is a clip, ordered by the number in its name (1.mkv, 2.mkv, ... or take_03.mp4).
- Single file: one long source; cutpoints.py later splits it into segments at long pauses.
Creates <input>/_edit (or <file-dir>/_edit_<stem>) with config.json, syncs the skill's one shared Python environment
(scripts/.venv, from scripts/pyproject.toml), and prints the detected format. Never touches the source files.
"""
import glob, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import probe, save

VIDEO_EXT = (".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi")

def order_key(path):
    nums = re.findall(r"\d+", os.path.basename(path))
    return (int(nums[0]) if nums else 1 << 30, os.path.basename(path).lower())

def main():
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    src = os.path.abspath(args[0]); out = None
    if "--out" in args: out = os.path.abspath(args[args.index("--out") + 1])
    if os.path.isdir(src):
        clips = sorted([f for f in glob.glob(os.path.join(src, "*")) if f.lower().endswith(VIDEO_EXT)], key=order_key)
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
    prev = os.path.join(out, "config.json")
    if os.path.exists(prev):  # keep any decisions already recorded (deliverables, brand, script)
        old = json.load(open(prev, encoding="utf-8")); cfg = {**old, **{k: cfg[k] for k in ("source", "mode", "w", "h", "fps", "orientation", "clips")}}
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
    for c in cfg["clips"]: print(f"   {c['key']}  {c['dur']:7.2f}s  {os.path.basename(c['path'])}{'' if c['audio'] else '  (NO AUDIO)'}")
    if odd: print("WARN clips with a different size/fps (they will be conformed):", odd)

if __name__ == "__main__":
    main()
