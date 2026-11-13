"""The plain talk version: the recorded slides full frame, the speaker in a round bubble bottom right, no B-roll.

Usage: uv run --project $S python screen_bubble.py <ws> --tag a1 [--inset 0.76] [--card "Up next: ..."] [--card-secs 6]
Needs `assemble.py <ws> --no-punch --screen ... --tag <tag>` first (a punch-in would change the bubble's framing at
every cut). Writes <ws>/cut/transitions_<tag>.mp4, so `export_final.py <ws> <tag> <dest> <Name>` finishes it
(hold + fade, -14 LUFS, sync check, .srt).
With scene-change wipes: run `transitions.py <ws> render --tag <tag>` first; this script then uses its wiped screen
cut and its face cut (live, HELD, live at each wipe) instead of the plain ones, and records the face box in
config.json "face_box" for `wipe_bubbles.py`.

- Bubble: the engine's geometry (r = 11.5% of the width, 2.2% margin, head and shoulders from faces.json), the same
  4 px light-blue ring and shadow as PIP/SCREEN in the B-roll page, so both versions of a video match.
- A segment with no screen file of its own (an inserted segment) plays its own picture full frame and the bubble
  hides over it: the insert already has its own face and screen.
- --secs N: render only the first N seconds (a layout check) to cut/preview_<tag>.mp4, never the deliverable's name.
- --panel: the face as a portrait 3:4 panel vertically centred on the right, about a
  quarter smaller than the old bubble, and the slides card as wide as the space left of it (no --inset needed).
  Less empty space top and right than a circle in the corner.
- --inset S: for a deck that uses its full width (a bubble over full-frame slides covered cards, terminals and URLs
  on 14 of 21 slides of one deck). The slides become a rounded card at S of the frame on the brand's navy
  gradient, left and vertically centred, and the bubble (r = 10% of the width) sits in the free corner beside it.
  Check: overlay the bubble on every slide's PDF render first; if it covers text, use --inset.
- --card: a lower-third line ("Up next: ..."), centred in the space left of the bubble (centred on the frame it ran into it),
  ending as the first inserted segment starts (references/transitions.md, Lower-third card)."""
import json, os, statistics, subprocess, sys
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import find_font, load, nvenc_ok, p, run, save, ws

SS = 4   # supersampling for the antialiased mask and ring

def nvenc():
    """An intermediate (export_final re-encodes it): NVENC when it works here, else libx264."""
    return nvenc_ok()

def arg(args, k, d=None): return args[args.index(k) + 1] if k in args else d

def covered(d, scr, x, y, w, h, W, H, n=8):
    """Warn when the bubble would sit on screen content: the share of sharp-edged pixels (text, UI lines) inside its
    box, sampled over the screen cut. A document column or a full-width deck under a corner bubble was only caught by
    reading the frames; this says so before the render."""
    import cv2, numpy as np
    cap = cv2.VideoCapture(os.path.join(d, scr)); N = cap.get(cv2.CAP_PROP_FRAME_COUNT); worst = 0.0
    for k in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(N * (k + 0.5) / n)); ok, f = cap.read()
        if not ok: continue
        f = cv2.resize(f, (W, H)); g = cv2.cvtColor(f[int(y):int(y + h), int(x):int(x + w)], cv2.COLOR_BGR2GRAY)
        e = cv2.Canny(g, 80, 200) > 0; gh, gw = e.shape
        # share of an 8x8 grid of cells holding edges: a few lines of small text fill few pixels but many cells
        cells = [e[i * gh // 8:(i + 1) * gh // 8, j * gw // 8:(j + 1) * gw // 8].mean() > 0.01 for i in range(8) for j in range(8)]
        worst = max(worst, sum(cells) / 64)
    if worst > 0.12:
        print(f"WARN the face covers screen content: {worst:.0%} of its box holds text or UI edges in some frames. Read "
              f"the frames; use --panel or --inset 0.75 if text sits under it")
    return worst

def main():
    d, cfg = ws(); args = sys.argv
    tag = arg(args, "--tag", "a1"); W, H, fps = cfg["w"], cfg["h"], cfg["fps"]
    tl = load(d, "cut", f"timeline_{tag}.json"); faces = load(d, "faces.json") or {}
    scr = (cfg.get("screen_cuts") or {}).get(tag)
    if not scr: sys.exit(f"no screen cut for {tag}: run assemble.py <ws> --no-punch --screen <folder> --tag {tag}")
    # transitions.py render (separate files) leaves a wiped screen cut and a face cut with the live, HELD, live switch
    face_in = f"cut/clean_{tag}.mp4"; wc = (cfg.get("wiped_cuts") or {}).get(tag)
    if wc and all(os.path.exists(p(d, x)) for x in wc.values()):
        if min(os.path.getmtime(p(d, x)) for x in wc.values()) >= os.path.getmtime(p(d, face_in)):
            scr, face_in = wc["screen"], wc["face"]; print(f"using the transitions render: {scr} + {face_in}")
        else: print(f"WARN {wc['face']} is older than {face_in}: re-run transitions.py <ws> render --tag {tag}; using plain cuts")
    if any(abs(s.get("zoom", 1) - 1) > 1e-3 for s in tl): print("WARN this cut has punch-ins; the bubble framing will jump at cuts (use --no-punch)")
    # bubble: same numbers as engine.Track._bubble_geometry, from the median face of the clips that have a screen file
    own = [s for s in tl if not s["clip"].startswith("m")]
    fs = [faces[s["clip"]] for s in own if s["clip"] in faces]
    med = {k: statistics.median(f[k] for f in fs) for k in ("cx", "cy", "h")}
    bl = cfg.get("bubble_layout", {}); inset = float(arg(args, "--inset", 0) or 0); panel = "--panel" in args
    m = round(W * 0.022); SH = 18                                   # margin; panel corner radius (engine.py uses the same)
    if panel:   # the face PANEL: portrait 3:4, vertically centred on the right, the engine's numbers
        pl = cfg.get("panel_layout", {})
        fw = pl.get("w", round(W * 0.14)); fh = pl.get("h", round(fw * 4 / 3)); fx, fy = W - m - fw, (H - fh) // 2
        sch = pl.get("src_h", min(H, med["h"] * 2.25)); scw = sch * fw / fh
        scx = min(max(pl.get("src_cx", med["cx"]), scw / 2), W - scw / 2); scy = min(max(pl.get("src_cy", med["cy"] + med["h"] * 0.12), sch / 2), H - sch / 2)
        crop = (scw, sch, scx - scw / 2, scy - sch / 2)
        if not inset: inset = (fx - 2 * m) / W                     # the slides fill everything left of the panel
        print(f"face panel {fw}x{fh} at ({fx},{fy}); source {scw:.0f}x{sch:.0f} at ({scx:.0f},{scy:.0f})")
    else:
        r = bl.get("r", round(W * (0.099 if inset else 0.115)))
        cx, cy = bl.get("cx", W - m - r), bl.get("cy", H - m - r); fw = fh = 2 * r; fx, fy = cx - r, cy - r
        sr = bl.get("src_r", med["h"] * 1.18); scx = bl.get("src_cx", med["cx"]); scy = bl.get("src_cy", med["cy"] + med["h"] * 0.14)
        sr = min(sr, scx, W - scx, scy, H - scy)                   # the source circle must sit inside the camera frame
        crop = (2 * sr, 2 * sr, scx - sr, scy - sr)
        print(f"bubble r={r} at ({cx},{cy}); source circle r={sr:.0f} at ({scx:.0f},{scy:.0f})")
    if inset:   # the slide card: left margin = face margin, vertically centred, must end left of the face
        cw_, ch_ = round(W * inset / 2) * 2, round(H * inset / 2) * 2; x0, y0 = m, (H - ch_) // 2
        if x0 + cw_ > fx - 4: sys.exit(f"--inset {inset} is too wide: the card ends at {x0 + cw_}, the face starts at {fx}")
    if not inset: covered(d, scr, fx, fy, fw, fh, W, H)
    pad = 40
    shape = (lambda dr, box, **k: dr.rounded_rectangle(box, SH * SS, **k)) if panel else (lambda dr, box, **k: dr.ellipse(box, **k))
    mask = Image.new("L", (fw * SS, fh * SS), 0); shape(ImageDraw.Draw(mask), (0, 0, fw * SS - 1, fh * SS - 1), fill=255)
    mask.resize((fw, fh), Image.LANCZOS).save(p(d, "cut", "_bubble_mask.png"))
    RW, RH = fw + 2 * pad, fh + 2 * pad; ring = Image.new("RGBA", (RW * SS, RH * SS), (0, 0, 0, 0))
    sh = Image.new("RGBA", ring.size, (0, 0, 0, 0)); shape(ImageDraw.Draw(sh), (pad * SS, (pad + 12) * SS, (pad + fw) * SS, (pad + fh + 12) * SS), fill=(0, 0, 0, 140))
    sh = sh.filter(ImageFilter.GaussianBlur(18 * SS)); hole = Image.new("L", ring.size, 255)
    shape(ImageDraw.Draw(hole), (pad * SS, pad * SS, (pad + fw) * SS, (pad + fh) * SS), fill=0)
    sh.putalpha(Image.composite(sh.getchannel("A"), Image.new("L", ring.size, 0), hole))   # shadow only outside the face
    ring = Image.alpha_composite(ring, sh)
    shape(ImageDraw.Draw(ring), ((pad - 4) * SS, (pad - 4) * SS, (pad + fw + 4) * SS, (pad + fh + 4) * SS), outline=(96, 165, 250, 217), width=(3 if panel else 4) * SS)
    ring.resize((RW, RH), Image.LANCZOS).save(p(d, "cut", "_bubble_ring.png"))
    cfg.setdefault("face_box", {})[tag] = [int(fx), int(fy), int(fw), int(fh)]; save(cfg, d, "config.json")   # wipe_bubbles.py crops it
    r = fw / 2; cx = fx + r                                         # the card text centres left of the face (below)
    # the bubble hides over segments that have no screen file of their own (an inserted segment): a hard cut, like the picture
    hide = [(s["v_out_start"], s["v_out_end"]) for s in tl if s["clip"].startswith("m")]
    off = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in hide) or "0"
    en = f"enable='not({off})'"
    extra = []
    if inset:
        g = Image.new("RGB", (W, H)); px = g.load(); stops = [(0, (7, 9, 15)), (0.52, (20, 36, 83)), (1, (8, 10, 19))]   # style.py #stage
        for yy in range(H):
            v = yy / (H - 1); (a, ca), (b, cb) = next(((stops[i], stops[i + 1]) for i in range(2) if stops[i][0] <= v <= stops[i + 1][0]))
            k = (v - a) / (b - a); col = tuple(round(ca[j] + (cb[j] - ca[j]) * k) for j in range(3))
            for xx in range(W): px[xx, yy] = col
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle((x0, y0 + 18, x0 + cw_, y0 + ch_ + 18), 18, fill=(0, 0, 0, 120))
        g = Image.alpha_composite(g.convert("RGBA"), sh.filter(ImageFilter.GaussianBlur(25))); g.convert("RGB").save(p(d, "cut", "_inset_bg.png"))
        cm = Image.new("L", (cw_ * SS, ch_ * SS), 0); ImageDraw.Draw(cm).rounded_rectangle((0, 0, cw_ * SS - 1, ch_ * SS - 1), 18 * SS, fill=255)
        cm.resize((cw_, ch_), Image.LANCZOS).save(p(d, "cut", "_inset_mask.png"))
        bd = Image.new("RGBA", ((cw_ + 4) * SS, (ch_ + 4) * SS), (0, 0, 0, 0))
        ImageDraw.Draw(bd).rounded_rectangle((0, 0, (cw_ + 4) * SS - 1, (ch_ + 4) * SS - 1), 20 * SS, outline=(148, 163, 184, 70), width=2 * SS)
        bd.resize((cw_ + 4, ch_ + 4), Image.LANCZOS).save(p(d, "cut", "_inset_border.png"))
        extra = ["-loop", "1", "-i", "cut/_inset_bg.png", "-loop", "1", "-i", "cut/_inset_mask.png", "-loop", "1", "-i", "cut/_inset_border.png"]
        print(f"inset card {cw_}x{ch_} at ({x0},{y0})")
    f = [f"[0:v]fps={fps},format=yuv420p,split=2[scr][scrfull]"]
    if inset:
        f += [f"[4:v]fps={fps},format=yuv420p[ibg]", f"[scr]scale={cw_}:{ch_}:flags=lanczos,format=rgba[sc]", "[5:v]format=gray[im]", "[sc][im]alphamerge[scm]",
              f"[ibg][scm]overlay=x={x0}:y={y0}:shortest=1[i1]", f"[i1][6:v]overlay=x={x0 - 2}:y={y0 - 2}[i2]",
              f"[i2][scrfull]overlay=enable='{off}'[bg]"]   # an inserted segment plays full frame
    else: f += ["[scrfull]nullsink", "[scr]null[bg]"]
    f += [
         f"[1:v]fps={fps},crop={crop[0]:.0f}:{crop[1]:.0f}:{crop[2]:.0f}:{crop[3]:.0f},scale={fw}:{fh}:flags=lanczos,format=rgba[fc]",
         "[2:v]format=gray[mk]", "[fc][mk]alphamerge[fb]",
         f"[bg][fb]overlay=x={fx}:y={fy}:{en}[b1]",
         f"[b1][3:v]overlay=x={fx - pad}:y={fy - pad}:{en}[b2]"]
    last = "b2"
    card = arg(args, "--card")
    if card:
        first_mid = next(s for s in tl if s["clip"].startswith("m"))
        t1 = first_mid["v_out_start"]; t0 = t1 - float(arg(args, "--card-secs", 6))
        font = find_font(bold=True)
        import shutil
        open(p(d, "cut", "_card.txt"), "w", encoding="utf-8").write(card)
        if font: shutil.copy(font, p(d, "cut", "_card_font.ttf"))
        alpha = f"if(lt(t,{t0 + 0.25:.3f}),(t-{t0:.3f})/0.25,if(gt(t,{t1 - 0.2:.3f}),({t1:.3f}-t)/0.2,1))"
        size = int(H * 0.030)
        f.append(f"[{last}]drawtext=fontfile=cut/_card_font.ttf:textfile=cut/_card.txt:fontsize={size}:fontcolor=white:box=1:boxcolor=black@0.85:"
                 f"boxborderw={int(size * 0.55)}:x=({cx - r - 20}-text_w)/2:y=h-text_h-{int(H * 0.075)}:alpha='{alpha}':enable='between(t,{t0:.3f},{t1:.3f})'[b3]")
        last = "b3"; print(f"card '{card}' {t0:.2f} -> {t1:.2f}")
    f.append(f"[{last}]format=yuv420p[vout]")
    # a --secs layout check must never take the deliverable's name: transitions.py render picks transitions_<tag> up
    out = p(d, "cut", f"preview_{tag}.mp4" if "--secs" in args else f"transitions_{tag}.mp4")
    cwd = os.getcwd(); os.chdir(d)
    try:
        run(["ffmpeg", "-v", "error", "-y", "-i", scr, "-i", face_in, "-loop", "1", "-i", "cut/_bubble_mask.png",
             "-loop", "1", "-i", "cut/_bubble_ring.png", *extra, "-filter_complex", ";".join(f), "-map", "[vout]", "-map", "1:a",
             "-shortest", *(["-t", arg(args, "--secs")] if "--secs" in args else []), *(["-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "15", "-b:v", "0"] if nvenc() else ["-c:v", "libx264", "-crf", "16", "-preset", "medium"]), "-r", str(fps), "-pix_fmt", "yuv420p", "-c:a", "copy",
             "-movflags", "+faststart", out])
    finally: os.chdir(cwd)
    print(f"-> {out}  (bubble hidden over {len(hide)} inserted segment(s))")

if __name__ == "__main__":
    main()
