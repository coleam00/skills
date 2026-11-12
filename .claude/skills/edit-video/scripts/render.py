"""Lint, inspect and render a HyperFrames project.

Usage: python render.py <ws> <name> [--quality draft|standard|high] [--out file.mp4] [--skip-inspect] [--chunk-secs 240] [--only 0,2] [--fps 6]
- --fps 6: a review preview of a long page at a tenth of the frames (a 21-minute page in ~10 minutes, not ~70);
  read it with review.py like any render. Never the deliverable: finalize renders at the source fps.
- lint must report 0 errors (warnings about file size / known z-index are fine)
- inspect: prints only errors/warnings, minus noise that is intentional by design (hand-drawn marks wobbling a few
  px outside their box). Off-canvas info from retracted panels is not shown.
- Pages longer than --chunk-secs (default 240) render in chunks: one HyperFrames job of ~75,000 frames (a 21-minute
  page) captured every frame and then stalled ("capture_disk stalled ... stuck at 74915", 71 min
  lost), while 4-minute pages render reliably. Each chunk is a copy of the page whose own timeline drives the original
  one from the chunk's start time, with its slice of every media file; the chunk videos are joined without
  re-encoding and the clean cut's audio is laid over the whole length, so no chunk boundary can touch the sound.
  --only 0,2 re-renders those chunks after a fix and keeps the rest (same --chunk-secs, same page length).
Renders at the source fps. Prints the render time.
"""
import glob, os, re, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ws

HF = "hyperframes@" + os.environ["HYPERFRAMES_VERSION"] if os.environ.get("HYPERFRAMES_VERSION") else "hyperframes"
# Pin the renderer for a project in progress: a release published mid-project can 404 (ETARGET) or render differently.

def sh(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout + r.stderr

def render_one(proj, fps, qual, out):
    """One HyperFrames render. An earlier file at the same path made a failed render look like success: on Windows the
    renderer's final move cannot replace an existing file, and this only checked that the path existed (once:
    two full-length runs, ~2 h, each "rendered" and left the previous 4-minute section). Remove it; keep the log."""
    t0 = time.time()
    if os.path.exists(out): os.remove(out)
    r = sh(f'npx -y {HF} render . --fps {fps} --quality {qual} --output "{out}"', cwd=proj)
    open(out[:-4] + ".log", "w", encoding="utf-8").write(r)
    if not os.path.exists(out) or os.path.getmtime(out) < t0: sys.exit(f"render failed ({out}):\n" + r[-2000:])
    return time.time() - t0

def chunked(proj, name, fps, qual, out, D, secs, only=None):
    html = open(os.path.join(proj, "index.html"), encoding="utf-8").read()
    dur = re.search(r'data-composition-id="[^"]+"[^>]*data-duration="([\d.]+)"', html).group(1)
    media = sorted(set(re.findall(r'src="([^"]+\.(?:mp4|mov|webm))"', html)))
    nf = round(D * fps); per = round(secs * fps); edges = list(range(0, nf, per)) + [nf]
    if nf - edges[-2] < fps * 5: edges.pop(-2)                    # no sliver of a last chunk
    root = os.path.join(os.path.dirname(proj), f"{name}_chunks"); os.makedirs(root, exist_ok=True)
    parts = []
    for k, (f0, f1) in enumerate(zip(edges, edges[1:])):
        a, b = f0 / fps, f1 / fps; cd = os.path.join(root, f"c{k:02d}"); os.makedirs(cd, exist_ok=True)
        if only is not None and k not in only:          # --only: re-render the listed chunks, keep the others' renders
            po = os.path.join(cd, "out", "chunk.mp4")
            if not os.path.exists(po): sys.exit(f"chunk {k} has no earlier render to keep: {po}")
            print(f"  chunk {k}: kept", flush=True); parts.append(po); continue
        for f in os.listdir(proj):                                  # small assets (and their folders): copy; media: this chunk's slice
            p = os.path.join(proj, f)
            if os.path.isfile(p) and f not in media and f != "index.html": shutil.copy2(p, os.path.join(cd, f))
            elif os.path.isdir(p) and f not in ("out", "node_modules") and not f.endswith("_chunks"):
                shutil.copytree(p, os.path.join(cd, f), dirs_exist_ok=True)   # left out, every <img> in it rendered blank
        for m in media:
            run_ = ["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.6f}", "-i", os.path.join(proj, m), "-t", f"{b - a + 1 / fps:.6f}",
                    "-c:v", "libx264", "-crf", "10", "-preset", "veryfast", "-r", str(fps), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                    os.path.join(cd, m)]
            subprocess.run(run_, check=True)
        h = html.replace(f'data-duration="{dur}"', f'data-duration="{b - a:.3f}"')
        # the chunk's own paused timeline plays the original one from time a: tl is never seeked by the renderer directly
        drive = (f'tl.pause();const __chunk=gsap.timeline({{paused:true}});'
                 f'__chunk.fromTo(tl,{{time:{a:.6f}}},{{time:{b:.6f},duration:{b - a:.6f},ease:"none",immediateRender:false}},0);')
        h, n = re.subn(r'window\.__timelines\["([^"]+)"\]=tl;', lambda mm: drive + f'window.__timelines["{mm.group(1)}"]=__chunk;', h)
        if n != 1: sys.exit(f"chunk {k}: expected one timeline registration, found {n}")
        open(os.path.join(cd, "index.html"), "w", encoding="utf-8").write(h)
        po = os.path.join(cd, "out", f"chunk.mp4"); os.makedirs(os.path.dirname(po), exist_ok=True)
        el = render_one(cd, fps, qual, po)
        got = float(sh(f'ffprobe -v error -show_entries format=duration -of csv=p=0 "{po}"'))
        print(f"  chunk {k}: {a:8.2f}-{b:8.2f}s rendered in {el:.0f}s ({got:.2f}s)", flush=True); parts.append(po)
    lst = os.path.join(root, "concat.txt"); open(lst, "w").write("".join(f"file '{p.replace(os.sep, '/')}'\n" for p in parts))
    vid = os.path.join(root, "video.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-map", "0:v:0", "-c", "copy", vid], check=True)
    m0 = os.path.join(proj, media[0]) if media else None             # the page's audio is the clean cut's (face.mp4)
    if os.path.exists(out): os.remove(out)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", vid, "-i", m0, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{D:.6f}", "-movflags", "+faststart", out], check=True)

def main():
    d, cfg = ws(); name = sys.argv[2]; a = sys.argv
    qual = a[a.index("--quality") + 1] if "--quality" in a else "standard"
    secs = float(a[a.index("--chunk-secs") + 1]) if "--chunk-secs" in a else 240.0
    proj = os.path.join(d, "hf", name)
    out = os.path.abspath(a[a.index("--out") + 1]) if "--out" in a else os.path.join(proj, "out", f"{name}_{qual}.mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    # a missing image renders as an empty box with lint and inspect both passing: check every local src first
    html = open(os.path.join(proj, "index.html"), encoding="utf-8").read()
    missing = sorted({s for s in re.findall(r'src="([^"]+)"', html) if "://" not in s and not s.startswith("data:")
                      and not os.path.exists(os.path.join(proj, s))})
    if missing: sys.exit(f"missing assets in {proj}: {missing}")
    lint = sh(f'npx -y {HF} lint "{proj}"')
    errs = re.findall(r"✗.*", lint); summary = re.findall(r"◇.*", lint)
    print("lint:", summary[-1] if summary else lint[-300:])
    for e in errs: print("  ", e)
    if errs: sys.exit("fix lint errors first")
    if "--skip-inspect" not in a:
        ins = sh(f'npx -y {HF} inspect "{proj}" --samples 60')
        bad = [l for l in ins.splitlines() if re.match(r"\s*(✗|⚠)", l) and "mark" not in l and "path:nth-of-type" not in l]
        print("inspect:", "clean" if not bad else f"{len(bad)} findings")
        for l in bad[:15]: print("  ", l.strip()[:220])
    html = open(os.path.join(proj, "index.html"), encoding="utf-8").read()
    D = float(re.search(r'data-composition-id="[^"]+"[^>]*data-duration="([\d.]+)"', html).group(1))
    t0 = time.time(); fps = int(a[a.index("--fps") + 1]) if "--fps" in a else cfg["fps"]
    only = {int(x) for x in a[a.index("--only") + 1].split(",")} if "--only" in a else None
    if D > secs * 1.25: chunked(proj, name, fps, qual, out, D, secs, only)
    else: render_one(proj, fps, qual, out)
    print(f"rendered {out} in {time.time() - t0:.0f}s")

if __name__ == "__main__":
    main()
