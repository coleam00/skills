"""Push transition (the default): the whole frame slides out to the right while the next clip slides in from the left,
locked edge to edge on one eased offset, with real motion blur, and the whoosh peaking on the cut.

Called by `transitions.py <ws> render [--kind push]`. Why it replaced the soft wipe as the default: with the whole frame in
motion, the glance at the record button at the end of a take and the settle at the start of the next one cannot be
seen, so a transition join needs no room tone, no held face and no look-away fixes: its tails are ordinary cut tails.

How a push is built (each one is rendered alone, then overlaid on the untouched cut, so length and audio never move):
- Window = [cut - dur/2, cut + dur/2] around the PICTURE cut (timeline v_out_start), dur 0.35 s (CapCut-like; 0.30-0.45
  all read fine).
- Outgoing side: its real frames up to GUARD before the cut, then that frame held; incoming side: that frame held, then
  its real frames from GUARD after the cut. GUARD (3 frames) matters: with separate screen files the screen track can
  switch 1-3 frames off the picture cut, and a held edge frame that already shows the next screen makes both halves the
  same picture (seen in testing as a white flash with both halves sliding the same way).
- Offset x = W * smoothstep(p); outgoing at x, incoming at x - W. Rendered at 480 fps and averaged 8:1 back to 60 fps,
  which is real motion blur (a 3-frame tmix at 60 fps gives ghosted copies instead).
- Works on any layout: a baked bubble, a face panel composite, a plain talking head. The face moves with its frame.
"""
import json, os, subprocess, sys

GUARD_FRAMES = 3
SUPER = 480                       # supersampling rate for the motion blur (8 sub-frames per 60 fps frame)


def _dur(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                capture_output=True, text=True).stdout)


def _font(card):
    for x in (card.get("font", ""), os.environ.get("EDIT_VIDEO_FONT", ""), "C:/Windows/Fonts/Inter-SemiBold.ttf",
              "C:/Windows/Fonts/segoeuib.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if x and os.path.exists(x): return x
    return None


def source(d, cfg, tag):
    """The picture to push: the composite for separate face + screen files (screen_bubble.py output, kept as
    cut/composite_<tag>.mp4 so re-renders never push an already-pushed file), else the clean cut."""
    sep = bool((cfg.get("screen_cuts") or {}).get(tag)) and not cfg.get("bubble")
    if not sep: return os.path.join(d, "cut", f"clean_{tag}.mp4")
    comp = os.path.join(d, "cut", f"composite_{tag}.mp4"); tr = os.path.join(d, "cut", f"transitions_{tag}.mp4")
    # transitions_<tag>.mp4 is either a FRESH screen_bubble composite or this script's own pushed output. Only a
    # fresh one replaces the kept composite: re-running screen_bubble.py after a fix and then rendering used to push
    # the OLD composite, because the kept one always won (Fable 11/13, a corrected screen track never reached the export)
    if os.path.exists(tr) and not _is_pushed(tr) and (not os.path.exists(comp) or os.path.getmtime(tr) > os.path.getmtime(comp)):
        os.replace(tr, comp); print(f"  kept the fresh screen_bubble composite as {os.path.relpath(comp, d)}")
    if not os.path.exists(comp):
        sys.exit(f"separate face + screen files: run screen_bubble.py <ws> --tag {tag} [--panel] first (the push moves the whole composite)")
    return comp


def _stamp(f):
    st = os.stat(f); return f"{st.st_size} {st.st_mtime_ns}"


def _is_pushed(f):
    m = f[:-4] + ".pushed"
    return os.path.exists(m) and open(m).read().strip() == _stamp(f)


def render_push(d, cfg, tag, dur, whoosh, peak, db, load):
    fps = cfg["fps"]; W, H = cfg["w"], cfg["h"]
    n = max(2, int(round(dur * fps / 2))); h = n / fps            # half window, whole frames
    G = GUARD_FRAMES / fps
    src = source(d, cfg, tag); tl = load(d, "cut", f"timeline_{tag}.json"); tj = load(d, "transitions.json")
    joins = set(tj["joins"]); total = _dur(src)
    cuts = [(b["key"], round(b["v_out_start"] * fps) / fps) for b in tl[1:] if b["key"] in joins]
    if not cuts: sys.exit("no transition joins in transitions.json")
    wdir = os.path.join(d, "cut", f"_push_{tag}"); os.makedirs(wdir, exist_ok=True)
    e = "(P*P*(3-2*P))"
    wins = []
    for key, c in cuts:
        pad = 1.0; ss = max(0.0, c - h - G - pad); lc = c - ss          # cut time inside the extracted piece
        P = f"clip((t-{lc - h:.6f})/{2 * h:.6f},0,1)"; ex = e.replace("P", P)
        fc = (f"[0:v]fps={SUPER},trim=start={lc - h - 0.2:.6f}:end={lc - G:.6f},setpts=PTS-STARTPTS,"
              f"tpad=stop_mode=clone:stop_duration={h + G + 0.1:.6f},setpts=PTS+{lc - h - 0.2:.6f}/TB[A];"
              f"[0:v]fps={SUPER},trim=start={lc + G:.6f}:end={lc + h + 0.2:.6f},setpts=PTS-STARTPTS,"
              f"tpad=start_mode=clone:start_duration={h + G + 0.1:.6f},setpts=PTS+{lc - h - 0.1:.6f}/TB[B];"
              f"color=black:s={W}x{H}:r={SUPER}:d={lc + h + 0.3:.6f}[bg];"
              f"[bg][A]overlay=x='{W}*{ex}':y=0:eval=frame:eof_action=pass[o1];"
              f"[o1][B]overlay=x='{W}*{ex}-{W}':y=0:eval=frame:eof_action=pass[o2];"
              f"[o2]tmix=frames={SUPER // fps}:weights={' '.join(['1'] * (SUPER // fps))},fps={fps},"
              f"trim=start={lc - h:.6f}:end={lc + h:.6f},setpts=PTS-STARTPTS,format=yuv420p[v]")
        out = os.path.join(wdir, f"{key}.mp4")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{ss:.6f}", "-t", f"{lc + h + 0.3:.6f}", "-i", src,
                            "-filter_complex", fc, "-map", "[v]", "-an", "-c:v", "libx264", "-crf", "10", "-preset", "fast",
                            "-r", str(fps), out], capture_output=True, text=True)
        if r.returncode: sys.exit(r.stderr[-2000:])
        wins.append((key, c, out)); print(f"  push {key} @ {int(c // 60)}:{c % 60:05.2f}  ({2 * h:.3f}s, frames {lc - h:.2f}-{lc + h:.2f} of the piece)")
    # one pass: overlay every push window on the untouched cut, whooshes peaking on each cut, optional card
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src, "-i", whoosh]
    f, cur = [], "0:v"
    for j, (key, c, out) in enumerate(wins):
        cmd += ["-i", out]
        f.append(f"[{2 + j}:v]setpts=PTS-STARTPTS+{c - h:.6f}/TB[w{j}]")
        f.append(f"[{cur}][w{j}]overlay=0:0:eof_action=pass:enable='between(t,{c - h:.6f},{c + h - 0.5 / fps:.6f})'[p{j}]"); cur = f"p{j}"
    card = tj.get("card"); vout = cur
    if card:
        k = [w[0] for w in wins].index(card["before"]); t1 = wins[k][1] - h; t0 = t1 - float(card.get("secs", 6))
        open(os.path.join(d, "cut", "_card.txt"), "w", encoding="utf-8").write(card["text"])
        font = _font(card); import shutil
        if font: shutil.copy(font, os.path.join(d, "cut", "_card_font.ttf"))
        size = int(H * 0.030); alpha = f"if(lt(t,{t0 + 0.25:.3f}),(t-{t0:.3f})/0.25,if(gt(t,{t1 - 0.2:.3f}),({t1:.3f}-t)/0.2,1))"
        f.append(f"[{cur}]drawtext={'fontfile=cut/_card_font.ttf:' if font else ''}textfile=cut/_card.txt:fontsize={size}:fontcolor=white:"
                 f"box=1:boxcolor=black@0.85:boxborderw={int(size * 0.55)}:x=(w-text_w)/2:y=h-text_h-{int(H * 0.075)}:alpha='{alpha}':"
                 f"enable='between(t,{t0:.3f},{t1:.3f})'[vc]"); vout = "vc"
        print(f"  card '{card['text']}' {t0:.2f} -> {t1:.2f}, ends as the {card['before']} push starts")
    f.append(f"[{vout}]format=yuv420p[vout]")
    f.append(f"[1:a]volume={db}dB,asplit={len(wins)}" + "".join(f"[s{j}]" for j in range(len(wins))))
    for j, (_, c, _) in enumerate(wins):
        ms = int(round((c - peak) * 1000)); f.append(f"[s{j}]adelay={ms}|{ms}[sd{j}]")
    f.append("[0:a]aformat=channel_layouts=stereo[sp];[sp]" + "".join(f"[sd{j}]" for j in range(len(wins))) +
             f"amix=inputs={len(wins) + 1}:duration=first:normalize=0,alimiter=limit=0.84:level=false:latency=1[aout]")
    out = os.path.join(d, "cut", f"transitions_{tag}.mp4")
    r = subprocess.run(cmd + ["-filter_complex", ";".join(f), "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-crf", "16",
                              "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "192k",
                              "-movflags", "+faststart", out], capture_output=True, text=True, cwd=d)
    if r.returncode: sys.exit(r.stderr[-2000:])
    open(out[:-4] + ".pushed", "w").write(_stamp(out))      # marks this file as pushed: never used as a composite
    print(f"{len(wins)} pushes -> {out} ({_dur(out):.3f}s, source {total:.3f}s). No room tone, no held face: transition "
          f"joins keep plain-cut tails. Check: frames across each push (review.py) and the joins' audio (validate_cut.py).")
    return out
