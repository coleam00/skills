"""Split a recorder canvas holding camera and screen side by side, or stacked, into a face file and a screen file.

Usage: uv run --project $S python split_wide.py <file> [--out-dir D] [--screen-dir D] [--face-side left|right|top|bottom]
                                                [--split-at Y] [--reframe WxH] [--backup] [--bubble 0.23] [--inset 0.8] [--cq 18]

One recording at 3840x1080 holds the camera full frame on one half and the presentation monitor on the other, so both
tracks share one clock: no sync step, no drift, and one record button (references/formats.md).
Writes, next to the source unless --out-dir:
  <stem>_face.mp4     the camera half + the audio. The whole edit pipeline runs on THIS file.
  <stem>_screen.mp4   the screen half, no audio. assemble.py --screen cuts it with the face's trims.
  <stem>_backup.mp4   (--backup) screen full frame + the face as a round bubble bottom right + audio: the plain
                      "slides with a face cam" version, so the video can still be edited by hand if the motion edit
                      is not used. Bubble ~23% of the width, centred on the measured face.
                      --inset S scales the slides to S and parks them top left on the dark background, so a deck
                      that uses its full width keeps every line clear of the bubble (on one deck the 23%
                      bubble covered the right-hand cards on 16 of 19 slides; --inset 0.8 --bubble 0.17 cleared them).
Stacked canvas (taller than wide, e.g. a 1080x1920 vertical canvas with the screen on top and the camera below):
detected automatically, --face-side top|bottom (default bottom). The seam between the two is found as the strongest
horizontal edge in the middle half of the frame and printed; --split-at Y overrides it. The face half is not 9:16, so pass
--reframe 1080x1920 to crop it to that aspect around the measured face and scale it up: the pipeline then sees an
ordinary vertical talking head (softer than native: a 1080x780 camera region is upscaled ~2.5x). --backup is side-by-side
only. Run it per clip; --screen-dir keeps the screen files out of the clip folder (init_workspace.py treats every
video in a folder as a clip).
One decode feeds all outputs; h264_nvenc when a GPU encoder works, else libx264. ~3x real time with NVENC.
Never touches the source.
"""
import os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import nvenc_ok, probe, run

BUBBLE_W = 0.23      # bubble diameter as a share of the frame width (a typical face-cam bubble)
MARGIN = 0.022       # gap from the right and bottom edges, share of width

def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default

def venc(cq):
    if nvenc_ok(): return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(cq), "-b:v", "0", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-crf", str(cq), "-preset", "medium", "-pix_fmt", "yuv420p"]

def face_box(path, hw, H, face_x0, face_y0=0):
    """Median haar face (cx, cy, h) in the face region (hw x H at face_x0, face_y0), sampled across the recording;
    a centred default if none found."""
    import cv2, numpy as np
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(path); dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(cap.get(cv2.CAP_PROP_FPS), 1); boxes = []
    for k in range(24):
        cap.set(cv2.CAP_PROP_POS_MSEC, (dur * (k + 0.5) / 24) * 1000); ok, f = cap.read()
        if not ok: continue
        f = f[face_y0:face_y0 + H, face_x0:face_x0 + hw]; sc = 0.5
        g = cv2.cvtColor(cv2.resize(f, None, fx=sc, fy=sc), cv2.COLOR_BGR2GRAY)
        fs = det.detectMultiScale(g, 1.08, 6, minSize=(60, 60))
        if len(fs): x, y, w, h = max(fs, key=lambda b: b[2]); boxes.append((x / sc + w / sc / 2, y / sc + h / sc / 2, h / sc))
    if not boxes: print("WARN no face found, bubble uses a centred default"); return hw / 2, H * 0.4, H * 0.3
    return tuple(float(v) for v in np.median(np.array(boxes), axis=0))

def boundary(path, W, H):
    """Row where a stacked canvas changes from one source to the other: the strongest horizontal edge in the middle
    half of the frame, averaged over 8 frames (the seam between screen and camera is the same row in every frame)."""
    import cv2, numpy as np
    cap = cv2.VideoCapture(path); n = cap.get(cv2.CAP_PROP_FRAME_COUNT); acc = np.zeros(H - 1)
    for k in range(8):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (k + 0.5) / 8)); ok, f = cap.read()
        if ok: acc += np.abs(np.diff(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(float), axis=0)).mean(axis=1)
    lo, hi = H // 4, H * 3 // 4
    return int(np.argmax(acc[lo:hi])) + lo + 1

def masks(D, out_dir):
    """Anti-aliased circle mask + a thin ring, drawn at 4x and downsampled."""
    from PIL import Image, ImageDraw
    m = os.path.join(out_dir, "_bubble_mask.png"); rg = os.path.join(out_dir, "_bubble_ring.png"); S = 4
    big = Image.new("L", (D * S, D * S), 0); ImageDraw.Draw(big).ellipse((0, 0, D * S - 1, D * S - 1), fill=255)
    big.resize((D, D), Image.LANCZOS).save(m)
    ring = Image.new("RGBA", (D * S, D * S), (0, 0, 0, 0)); ImageDraw.Draw(ring).ellipse((2, 2, D * S - 3, D * S - 3), outline=(96, 165, 250, 210), width=3 * S)
    ring.resize((D, D), Image.LANCZOS).save(rg)
    return m, rg

def main():
    a = sys.argv[1:]
    if not a or a[0].startswith("--"): sys.exit(__doc__)
    src = os.path.abspath(a[0]); info = probe(src); W, H = info["w"], info["h"]; cq = arg("--cq", 18)
    stacked = H > W or "--stacked" in a
    if stacked:
        side = arg("--face-side", "bottom")
        if side not in ("top", "bottom"): sys.exit("stacked canvas: --face-side top|bottom")
        if "--backup" in a: sys.exit("--backup is for side-by-side canvases only")
        cut = arg("--split-at", 0) or boundary(src, W, H)            # the seam is rarely at exactly half
        print(f"stacked canvas {W}x{H}: seam at y={cut} (override with --split-at)")
        top_h, bot_h = cut // 2 * 2, (H - cut) // 2 * 2
        if side == "bottom": rw, rh, fx, fy, sx, sy, sh = W, bot_h, 0, H - bot_h, 0, 0, top_h
        else: rw, rh, fx, fy, sx, sy, sh = W, top_h, 0, 0, 0, H - bot_h, bot_h
    else:
        if W < H * 3: print(f"WARN {W}x{H} does not look side by side (expected about 2x16:9, e.g. 3840x1080)")
        side = arg("--face-side", "left"); rw, rh = W // 2 // 2 * 2, H
        fx, sx = (0, W - rw) if side == "left" else (W - rw, 0); fy = sy = 0
    hw = rw
    out_dir = os.path.abspath(arg("--out-dir", os.path.dirname(src))); os.makedirs(out_dir, exist_ok=True)
    scr_dir = os.path.abspath(arg("--screen-dir", out_dir)); os.makedirs(scr_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src))[0]
    face, screen = os.path.join(out_dir, f"{stem}_face.mp4"), os.path.join(scr_dir, f"{stem}_screen.mp4")
    for o in (face, screen):
        if os.path.abspath(o) == src: sys.exit("output would overwrite the source")
    v = venc(cq)
    face_f = f"crop={rw}:{rh}:{fx}:{fy},setsar=1"
    if "--reframe" in a:                                           # crop the face region to the target aspect around the face
        tw, th = (int(x) for x in arg("--reframe", "1080x1920").lower().split("x"))
        cx, cy, fh = face_box(src, rw, rh, fx, fy)
        if tw / th < rw / rh: cw, ch = round(rh * tw / th / 2) * 2, rh
        else: cw, ch = rw, round(rw * th / tw / 2) * 2
        x0 = int(min(max(cx - cw / 2, 0), rw - cw)); y0 = int(min(max(cy - ch / 2, 0), rh - ch))
        face_f = f"crop={cw}:{ch}:{fx + x0}:{fy + y0},scale={tw}:{th}:flags=lanczos,setsar=1"
        print(f"reframe: {cw}x{ch} around face ({cx:.0f},{cy:.0f}) in the camera region -> {tw}x{th}"
              + (f"  (upscaled {tw / cw:.2f}x)" if tw > cw else ""))
    # ONE decode feeds every output: decoding the 3840-wide source is the slow part, so three passes cost ~3x
    fc = [f"[0:v]split={3 if '--backup' in a else 2}[a][b]" + ("[c]" if "--backup" in a else ""),
          f"[a]{face_f}[f]", f"[b]crop={rw}:{sh if stacked else rh}:{sx}:{sy},setsar=1[s]"]
    inputs = ["-i", src]; outs = ["-map", "[f]", "-map", "0:a:0?", *v, "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", face,
                                  "-map", "[s]", "-an", *v, "-movflags", "+faststart", screen]
    tmp = []
    if "--backup" in a:
        cx, cy, fh = face_box(src, hw, H, fx)
        D = round(hw * arg("--bubble", BUBBLE_W) / 2) * 2;   # --bubble: a smaller bubble when the slides use the corner
        m = round(hw * MARGIN); inset = arg("--inset", 1.0)
        side_px = min(round(fh * 2.3 / 2) * 2, H, hw)            # head and shoulders inside the circle
        cx0 = int(min(max(cx - side_px / 2, 0), hw - side_px)); cy0 = int(min(max(cy + fh * 0.12 - side_px / 2, 0), H - side_px))
        mk, rg = masks(D, out_dir); tmp = [mk, rg]; bx, by = hw - m - D, H - m - D
        backup = os.path.join(out_dir, f"{stem}_backup.mp4")
        inputs += ["-loop", "1", "-i", mk, "-loop", "1", "-i", rg]
        fc += [f"[c]split[c1][c2]", (f"[c1]crop={hw}:{H}:{sx}:0,scale={round(hw * inset / 2) * 2}:{round(H * inset / 2) * 2}:flags=lanczos,"
                f"pad={hw}:{H}:{m}:{m}:color=0x07090F,setsar=1[bs]" if inset < 1 else f"[c1]crop={hw}:{H}:{sx}:0,setsar=1[bs]"),
               f"[c2]crop={side_px}:{side_px}:{fx + cx0}:{cy0},scale={D}:{D}:flags=lanczos,format=yuva420p[bf]",
               f"[1:v]format=gray,scale={D}:{D}[bm]", "[bf][bm]alphamerge[bfm]", f"[bs][bfm]overlay={bx}:{by}:shortest=1[o1]",
               f"[o1][2:v]overlay={bx}:{by}:shortest=1,format=yuv420p[bo]"]
        outs += ["-map", "[bo]", "-map", "0:a:0?", *v, "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", backup]
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(fc), *outs])
    for f in tmp: os.remove(f)
    print("face  ", face); print("screen", screen)
    if "--backup" in a: print("backup", backup, f"(bubble {D}px at {bx},{by}; face crop {side_px}px around {cx:.0f},{cy:.0f})")
    print(f"next: init_workspace.py \"{face}\" (one recording) or \"{out_dir}\" (after splitting every clip into it); "
          "assemble.py <ws> --screen <screen folder> only if the screen track belongs in the video")

if __name__ == "__main__":
    main()
