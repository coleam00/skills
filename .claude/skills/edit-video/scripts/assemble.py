"""Assemble the clean cut from cuts.json: trims, split edits, alternating punch-in, micro-fades, loudness.

Usage: uv run --project $S python assemble.py <ws> [--no-punch] [--level] [--tag v1]
- Level (--level): gain every segment to the median segment loudness before the final loudnorm. Use it when clips
  come from different sessions or include a pre-mastered insert (an ad read, an intro); check per-segment LUFS after.
- Punch-in: the face size is measured per clip (faces.json, written here on first run) and every cut alternates
  between a wide and a tight framing whose face widths differ by ~10%, so jump cuts read as deliberate.
- Split edits: overrides.json "video_out" ends a segment's picture early; the next segment's picture starts early by
  the same amount, audio unchanged.
- Screen (--screen [file|folder]): a side-by-side recording split by split_wide.py has a screen file per face file.
  The screen track is cut with exactly the same picture trims (no punch-in) into cut/screen_<tag>.mp4, video only,
  and config.json "screen_cuts" records it so the B-roll page can show it (engine SCREEN mode). With no value, each
  clip's screen file is found by swapping "_face." for "_screen." (or "-face " for "-screen ", separate recorder outputs)
  in its name; a folder is searched the same way. Separate files are synced by their audio (screen_lag); a clip with no
  screen file (an inserted segment) shows its own picture.
Writes <ws>/cut/clean_<tag>.mp4 (no captions) and <ws>/cut/timeline_<tag>.json, which maps every segment to the
output timeline (out_start/out_end for audio, v_out_start for the picture cut). Everything downstream reads these.
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load, p, q, run, save, ws

PUNCH_STEP = 1.10   # ~10% face-size step between alternating takes: visible as a cut, not as a zoom
FADE_IN, FADE_OUT = 0.008, 0.015   # seconds; kills clicks at sample-level discontinuities

def measure_faces(d, cfg, segs):
    import cv2
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    out = {}
    for c in cfg["clips"]:
        mine = [s for s in segs if s["clip"] == c["key"]]
        if not mine: continue
        cap = cv2.VideoCapture(c["path"]); boxes = []; sc = 540 / max(cfg["w"], cfg["h"]) * 2
        for s in mine:
            t = s["in"] + 0.3
            while t < s["out"] - 0.3 and len(boxes) < 40:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, f = cap.read(); t += 0.6
                if not ok: continue
                g = cv2.cvtColor(cv2.resize(f, None, fx=sc, fy=sc), cv2.COLOR_BGR2GRAY)
                fs = det.detectMultiScale(g, 1.08, 6, minSize=(int(60 * sc * 2), int(60 * sc * 2)))
                if len(fs): x, y, w, h = max(fs, key=lambda b: b[2]); boxes.append((x / sc, y / sc, w / sc, h / sc))
        if boxes:
            import numpy as np
            b = np.median(np.array(boxes), axis=0)
            out[c["key"]] = {"x": float(b[0]), "y": float(b[1]), "w": float(b[2]), "h": float(b[3]), "cx": float(b[0] + b[2] / 2), "cy": float(b[1] + b[3] / 2)}
    return out

def screen_path(face_path, val):
    """The screen file that belongs to a face clip, or None for a clip that has none (an inserted segment: its own
    picture fills the screen track). split_wide.py names them <stem>_face / <stem>_screen; separate recorder outputs
    are often "<prefix>-face <date>" / "<prefix>-screen <date>"."""
    base = os.path.basename(face_path)
    name = base.replace("_face.", "_screen.") if "_face." in base else base.replace("-face ", "-screen ") if "-face " in base else None
    if val and os.path.isfile(val): return val
    folder = val if val and os.path.isdir(val) else os.path.dirname(face_path)
    if name and os.path.exists(os.path.join(folder, name)): return os.path.join(folder, name)
    return None

def screen_lag(face, screen, secs=45, sr=8000):
    """Seconds the screen file starts after the face file (negative: before). Separate recordings (a camera file
    and a screen file per take) start up to ~0.8 s apart, different every take (measured -0.37 to +0.82 s), so each pair is measured
    by cross-correlating the mic audio both files carry. One wide canvas (split_wide.py) measures 0."""
    import numpy as np
    def pcm(f):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-t", str(secs), "-i", f, "-map", "0:a:0", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                             capture_output=True).stdout
        return np.frombuffer(raw, np.int16).astype(np.float32)
    a, b = pcm(face), pcm(screen)
    if len(a) < sr or len(b) < sr: print(f"WARN no audio to sync {os.path.basename(screen)}: assuming 0 s"); return 0.0
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    c = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    k = int(np.argmax(c)); k = k - n if k > n // 2 else k
    corr = c.max() / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)
    if corr < 0.5: print(f"WARN weak audio match ({corr:.2f}) for {os.path.basename(screen)}: check its sync by eye")
    return k / sr

def cut_screen(d, cfg, tl, tag, args):
    """Cut the screen track with the picture trims of the face cut, so it lines up frame for frame with clean_<tag>.
    Each screen file is shifted by its measured lag (config.json "screen_lags", cached by file name)."""
    W, H, fps = cfg["w"], cfg["h"], cfg["fps"]; i = args.index("--screen")
    val = args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("--") else None
    lags = cfg.setdefault("screen_lags", {})
    if val: cfg["screen_from"] = os.path.abspath(val)      # transitions.py detect compares these screen files, not the faces
    srcs, fv = [], []
    for s in tl:
        sp = screen_path(s["path"], val) or s["path"]
        if sp not in srcs: srcs.append(sp)
        if sp != s["path"] and os.path.basename(sp) not in lags:
            lags[os.path.basename(sp)] = round(screen_lag(s["path"], sp), 4)
            print(f"  screen lag {os.path.basename(sp)}: {lags[os.path.basename(sp)]:+.3f} s")
    for n_, s in enumerate(tl):
        sp = screen_path(s["path"], val) or s["path"]; n = srcs.index(sp)
        lag = lags.get(os.path.basename(sp), 0.0) if sp != s["path"] else 0.0
        a, b = s["v_in"] - lag, s["v_out"] - lag
        pad = f",tpad=start_duration={-a:.6f}:start_mode=clone" if a < 0 else ""   # screen file started after this head
        fv.append(f"[{n}:v]trim=start={max(0, a):.6f}:end={b:.6f},setpts=PTS-STARTPTS{pad},fps={fps},"
                  f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{n_}]")
    save(cfg, d, "config.json")
    filt = ";".join(fv) + ";" + "".join(f"[v{i_}]" for i_ in range(len(tl))) + f"concat=n={len(tl)}:v=1:a=0[vc]"
    out = p(d, "cut", f"screen_{tag}.mp4"); inputs = []
    for sp in srcs: inputs += ["-i", sp]
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", filt, "-map", "[vc]", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
         "-r", str(fps), "-pix_fmt", "yuv420p", "-movflags", "+faststart", out])
    cfg.setdefault("screen_cuts", {})[tag] = os.path.relpath(out, d).replace("\\", "/"); save(cfg, d, "config.json")
    vd = tl[-1]["v_out_end"]; print(f"screen -> {out}  ({vd:.2f}s picture, same trims as the face)")

def main():
    d, cfg = ws(); args = sys.argv
    tag = args[args.index("--tag") + 1] if "--tag" in args else "v1"
    W, H, fps = cfg["w"], cfg["h"], cfg["fps"]
    segs = load(d, "cuts.json")["segments"]; ov = load(d, "overrides.json", default={}) or {}
    faces = load(d, "faces.json")
    if faces is None:
        faces = measure_faces(d, cfg, segs); save(faces, d, "faces.json")
    # zooms: alternate wide/tight face widths; pick the parity with the most even steps
    punch = "--no-punch" not in args and len(faces) > 0
    own = [f["w"] for k, f in faces.items() if not k.startswith("m")] or [f["w"] for f in faces.values()]
    base = sorted(own)[len(own) // 2] if faces else 1
    zs = [1.0] * len(segs)
    if punch:
        # alternate wide / tight framings. An inserted, already-finished segment (m01 from insert_segment.py) is never
        # punched (its own framing measured as a small face once and got zoom 3.4, cropping the whole insert), so it is
        # pinned at 1.0 and each run of takes between inserts picks its own parity, scored against the pinned
        # neighbours too: pinning the insert after the search left it at the same framing as the take beside it.
        z = lambda s, tight_: max(1.0, (base * (PUNCH_STEP if tight_ else 1.0)) / faces.get(s["clip"], {"w": base})["w"])
        ins = [s["clip"].startswith("m") for s in segs]
        zs = [1.0] * len(segs); i = 0
        while i < len(segs):
            if ins[i]: i += 1; continue
            j = i
            while j < len(segs) and not ins[j]: j += 1
            best = None
            for par in (0, 1):
                trial = list(zs); trial[i:j] = [z(segs[k], (k - i + par) % 2) for k in range(i, j)]
                lo, hi = max(0, i - 1), min(len(segs) - 1, j)
                score = min((abs(trial[k] - trial[k + 1]) for k in range(lo, hi)), default=1)
                if best is None or score > best[0]: best = (score, trial)
            zs = best[1]; i = j
        for i in range(len(segs) - 1):
            if abs(zs[i] - zs[i + 1]) < 0.05: print(f"  WARN same framing at the {segs[i]['key']} -> {segs[i + 1]['key']} join (zoom {zs[i]:.3f} / {zs[i + 1]:.3f}): a jump cut")
    tl = []
    for s in segs:
        a_in, a_out = q(s["in"], fps), q(s["out"], fps)
        v_out = q(min(a_out, ov.get("video_out", {}).get(s["key"], a_out)), fps)
        tl.append({"key": s["key"], "clip": s["clip"], "path": s["path"], "a_in": a_in, "a_out": a_out, "v_in": a_in, "v_out": v_out})
    for i in range(len(tl) - 1):
        dlt = tl[i]["a_out"] - tl[i]["v_out"]
        if dlt > 0: tl[i + 1]["v_in"] = q(max(0, tl[i + 1]["a_in"] - dlt), fps)
    tl[-1]["v_out"] = tl[-1]["a_out"]
    t = vt = 0.0
    for s, z in zip(tl, zs):
        s["zoom"] = round(z, 4)
        s["out_start"] = round(t, 4); t += s["a_out"] - s["a_in"]; s["out_end"] = round(t, 4)
        s["v_out_start"] = round(vt, 4); vt += s["v_out"] - s["v_in"]; s["v_out_end"] = round(vt, 4)
    # --level: clips recorded in different sessions (mic gain, distance) or a pre-mastered insert (an ad read
    # already at -14 LUFS) differ by several dB, and the single loudnorm below cannot fix a level jump at a join.
    # Measure each segment's integrated loudness in its source and gain it to the median first (clamped +-14 dB: a mastered insert sits ~11 dB over raw mic audio).
    gains = [0.0] * len(tl)
    if "--level" in args:
        import re, statistics
        meas = []
        for s in tl:
            r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", f"{s['a_in']:.3f}", "-t", f"{s['a_out'] - s['a_in']:.3f}", "-i", s["path"],
                                "-map", "0:a:0", "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
            v = re.findall(r"I:\s+(-?[\d.]+) LUFS", r); meas.append(float(v[-1]) if v and s["a_out"] - s["a_in"] >= 3 else None)
        ref = statistics.median([m for m in meas if m is not None])
        gains = [None if m is None else max(-14.0, min(14.0, ref - m)) for m in meas]
        # a segment too short to measure (a spliced remainder: c02_s01b) takes its own clip's gain, or the splice
        # stepped the level by up to a dB mid-sentence (one take, two gains)
        for i, s in enumerate(tl):
            if gains[i] is None:
                sib = [g for t_, g in zip(tl, gains) if t_["clip"] == s["clip"] and g is not None]
                gains[i] = statistics.median(sib) if sib else 0.0
        for s, m, g in zip(tl, meas, gains): print(f"  level {s['key']:9} {m if m is not None else 'n/a':>6} LUFS  gain {g:+.1f} dB")
    for s, g in zip(tl, gains): s["gain_db"] = round(g, 2)
    inputs, fv, fa = [], [], []
    srcs = []
    for s in tl:
        if s["path"] not in srcs: srcs.append(s["path"])
    for sp in srcs: inputs += ["-i", sp]
    for i, s in enumerate(tl):
        n = srcs.index(s["path"]); z = s["zoom"]; fc = faces.get(s["clip"], {"cx": W / 2, "cy": H * 0.38, "h": H * 0.3})
        zf = ""
        if z > 1.0001:
            cw, ch = round(W / z / 2) * 2, round(H / z / 2) * 2
            cx = int(min(max(fc["cx"] - cw / 2, 0), W - cw)); cy = int(min(max(fc["cy"] - ch * 0.37, 0), H - ch))
            zf = f",crop={cw}:{ch}:{cx}:{cy},scale={W}:{H}:flags=lanczos"
        # A trim past the end of a stream (a tail placed at the clip's end, where the audio stops a few ms before the
        # video) would make that segment short and shift everything after it: pad, then cut to the exact length.
        dv = s["v_out"] - s["v_in"]; ad = s["a_out"] - s["a_in"]
        fv.append(f"[{n}:v]trim=start={s['v_in']:.6f}:end={s['v_out']:.6f},setpts=PTS-STARTPTS,fps={fps},scale={W}:{H}{zf},setsar=1,"
                  f"tpad=stop_mode=clone:stop_duration=1,trim=duration={dv:.6f},format=yuv420p[v{i}]")
        fa.append(f"[{n}:a]atrim=start={s['a_in']:.6f}:end={s['a_out']:.6f},asetpts=PTS-STARTPTS,aresample=48000,apad=whole_dur={ad:.6f},atrim=duration={ad:.6f},"
                  f"volume={s['gain_db']}dB,afade=t=in:st=0:d={FADE_IN},afade=t=out:st={ad - FADE_OUT:.6f}:d={FADE_OUT}[a{i}]")
    k = len(tl)
    filt = ";".join(fv + fa) + ";" + "".join(f"[v{i}]" for i in range(k)) + f"concat=n={k}:v=1:a=0[vc];" + \
           "".join(f"[a{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1,highpass=f=70[ac]"
    tmp = p(d, "cut", f"_prenorm_{tag}.mkv")
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", filt, "-map", "[vc]", "-map", "[ac]", "-c:v", "libx264", "-crf", "14",
         "-preset", "slow", "-r", str(fps), "-c:a", "pcm_s16le", tmp])
    m = subprocess.run(["ffmpeg", "-hide_banner", "-i", tmp, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    j = json.loads(m[m.rindex("{"):m.rindex("}") + 1])
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:"
          f"measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true,aresample=48000")
    out = p(d, "cut", f"clean_{tag}.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p", "-r", str(fps),
         "-af", ln, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    save(tl, d, "cut", f"timeline_{tag}.json")
    print(f"{k} segments -> {out}  ({t:.2f}s)")
    if "--screen" in args: cut_screen(d, cfg, tl, tag, args)
    for s in tl: print(f"  {s['key']:9} @ {s['out_start']:7.2f}-{s['out_end']:7.2f}  zoom {s['zoom']}")

if __name__ == "__main__":
    main()
