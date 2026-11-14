"""Scene-change transitions between clips. DEFAULT: a push (the whole frame slides, whoosh on the cut), with plain-cut
tails and no `room` step. The legacy soft wipe (--kind smoothleft) is described further down; ignore it for a push.

Usage:
  uv run --project $S python transitions.py <ws> detect [--threshold 6]   # which clip joins change scene
  uv run --project $S python transitions.py <ws> room [--tail 0.45] [--head 0]  # widen those joins (edits cuts.json)
  uv run --project $S python transitions.py <ws> render [--tag v1] [--kind push|smoothleft] [--dur 0.35] [--whoosh-db -6.4] [--sfx file --sfx-peak s]

DEFAULT: --kind push (scripts/push.py): the whole frame slides out right, the next clip slides in from the left,
motion-blurred, whoosh peaking on the PICTURE cut. No `room` step and no held face: transition joins keep plain-cut
tails (~0.2-0.35 s heard pause). Separate face + screen files: run screen_bubble.py first; the push moves the
composite. Everything below about room tone, centring in the pause, the bubble hold and wiped face/screen cuts is the
legacy soft wipe (--kind smoothleft).

Rules (references/transitions.md): only at clip joins where the SCREEN changes, never at a tab switch inside one
clip, never at a join that stays on the same screen. The whoosh is quiet and lands in silence, never over a word,
so a SOFT-WIPE join gets ~0.5-0.8 s of pause where a plain cut gets ~0.15-0.3 s. A push join keeps its plain-cut pause.

detect : compares the last kept frame of each segment with the first of the next (face-cam bubble masked) and writes
         <ws>/transitions.json {"joins": [incoming segment keys]}. Edit that list by hand to add/remove joins.
room   : for each join in transitions.json, extends the outgoing tail by up to --tail s and the incoming head by up
         to --head s (default 0: heads hold breaths), but only through quiet audio (stops at anything QUIET_DB over the clip's room tone: a breath
         or a word). Writes the new in/out into cuts.json and overrides.json. Re-run assemble + validate after;
         validate will flag these joins DEAD AIR on purpose.
render : wipes at those joins on cut/clean_<tag>.mp4 (length and audio untouched), each wipe + whoosh centred in
         the pause between the last word and the next (a held edge frame covers the gap), the bubble (config.json "bubble": [cx, cy, r], optional) overlaid from the
         untouched cut so it never slides, whooshes (assets/sfx/whoosh.wav unless --sfx) mixed peaking on each wipe. -> cut/transitions_<tag>.mp4
         The bubble switches to the incoming clip AT THE WIPE MIDPOINT, not at the picture cut: between the two it shows
         the incoming clip's real pre-roll (live, facing camera), because the outgoing tail is where the speaker looks
         away to stop the recording (~0.45 s after the last word).
         Separate face and screen files (assemble.py --screen, no "bubble"): the wipe goes on the SCREEN cut and the
         face track gets the same live, HELD, live switch over its full frame, with the face switch kept inside the
         wipe so the panel never shows the incoming take while the outgoing screen is still whole (or the reverse).
         -> cut/screen_wiped_<tag>.mp4 + cut/face_wiped_<tag>.mp4 (whooshes mixed in), recorded in config.json
         "wiped_cuts"; screen_bubble.py --tag <tag> picks them up and writes cut/transitions_<tag>.mp4.
         transitions.json may carry "bubble_at_cut": ["<incoming key>", ...] (bubble switches at the picture cut, for a
         clip whose pre-roll still looks at the record button) and "card": {"before": "<segment key>", "text": "...", "secs": 6} (a lower-third
         line before a join, references/transitions.md): white text in a black box, bottom centre, ending as that join's wipe starts.
"""
import json, os, subprocess, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import find_font, load, save

D = 0.34                 # wipe length; 0.40 read slow in review, don't go much below 0.30
ASSET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sfx", "whoosh.wav")
PEAK = 0.21              # peak offset of assets/sfx/whoosh.wav
QUIET_DB = 9           # "room tone" = within this many dB of the clip's quietest 15%
HERE = os.path.dirname(os.path.abspath(__file__))

def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default

def bubble_mask(cfg, w, h):
    m = np.ones((h, w), bool)
    if cfg.get("bubble"):
        cx, cy, r = cfg["bubble"]; sx, sy = w / cfg["w"], h / cfg["h"]
        m[max(int((cy - r) * sy), 0):, max(int((cx - r) * sx), 0):] = False
    return m

def grab(path, t, vf, pix, nbytes):
    """One raw frame at t; past the file's end (a padded take's out point beyond its screen file), its last frame,
    which is what assemble.py holds there."""
    cmd = lambda pos: ["ffmpeg", "-v", "error"] + pos + ["-i", path, "-frames:v", "1", "-vf", vf, "-f", "rawvideo",
                                                         "-pix_fmt", pix, "-"]
    r = subprocess.run(cmd(["-ss", f"{max(t, 0):.4f}"]), capture_output=True).stdout
    if len(r) < nbytes: r = subprocess.run(cmd(["-sseof", "-0.25"]), capture_output=True).stdout
    return r[:nbytes]

def frame(path, t, w=192, h=108):
    return np.frombuffer(grab(path, t, f"scale={w}:{h}", "gray", w * h), np.uint8).reshape(h, w).astype(np.float32)

def detect(d, cfg):
    segs = load(d, "cuts.json")["segments"]; thr = arg("--threshold", 6.0); m = bubble_mask(cfg, 192, 108); joins = []; every = []
    # separate face and screen files (assemble.py --screen): the scene is the SCREEN, so compare the screen files at the
    # same trims, shifted by each pair's measured lag. Comparing the face files measured a talking head on one set.
    def pic(s, t):
        if cfg.get("screen_cuts"):
            from assemble import screen_path
            sp = screen_path(s["path"], cfg.get("screen_from"))
            if sp: return sp, t - cfg.get("screen_lags", {}).get(os.path.basename(sp), 0.0)
        return s["path"], t
    if cfg.get("screen_cuts"): print("comparing the screen files (assemble.py --screen), not the face files")
    for a, b in zip(segs, segs[1:]):
        diff = float(np.abs(frame(*pic(a, a["out"] - 1 / cfg["fps"])) - frame(*pic(b, b["in"])))[m].mean())
        on = diff >= thr; every.append((a, b, diff, on))
        if on: joins.append((a, b, diff))
        ins = "  insert join: a transition only if the insert looks different, else a clean cut" if (a["clip"].startswith("m") or b["clip"].startswith("m")) else ""
        print(f"  {a['key']} -> {b['key']}  screen diff {diff:6.1f}  {'CANDIDATE' if on else ''}{ins}")
    save({"joins": [b["key"] for _, b, _ in joins]}, d, "transitions.json")
    # contact sheet: the agent must READ it and drop joins that stay on the same screen (scroll, panel, popover)
    from PIL import Image, ImageDraw
    def rgb(p, t):
        return Image.frombytes("RGB", (480, 270), grab(p, t, "scale=480:270", "rgb24", 480 * 270 * 3))
    # every join, not only the candidates: a missed scene change (and "0 candidates") must be checked by eye too
    # in pages of 6 joins: one sheet of every join of a 28-take video was 7,500 px tall, too tall to read (Fable 11/13)
    PAGE = 6; pages = []
    os.makedirs(os.path.join(d, "check"), exist_ok=True)
    for f in os.listdir(os.path.join(d, "check")):
        if f.startswith("transition_joins"): os.remove(os.path.join(d, "check", f))
    for p0 in range(0, len(every), PAGE):
        chunk = every[p0:p0 + PAGE]
        sheet = Image.new("RGB", (960, 270 * len(chunk)), "black"); dr = ImageDraw.Draw(sheet)
        for i, (a, b, diff, on) in enumerate(chunk):
            sheet.paste(rgb(*pic(a, a["out"] - 1 / cfg["fps"])), (0, 270 * i)); sheet.paste(rgb(*pic(b, b["in"])), (480, 270 * i))
            dr.rectangle((0, 270 * i, 959, 270 * i + 24), fill=(0, 0, 0))
            dr.text((6, 270 * i + 6), f"{a['key']} -> {b['key']}  diff {diff:.1f}{'  CANDIDATE' if on else ''}   (left: outgoing last frame | right: incoming first frame)", fill=(255, 230, 0))
        name = f"transition_joins_{p0 // PAGE + 1}.png"; sheet.save(os.path.join(d, "check", name)); pages.append(name)
    print(f"{len(joins)} candidates -> transitions.json. READ every check/transition_joins_N.png ({len(pages)} pages, every join, candidates marked) "
          f"with the words across each join: keep only real scene changes that end a thought. No transition is a valid "
          f"outcome: a talking head on one set has no scene change to mark.")

def room(d, cfg):
    import soundfile as sf
    tail, head = arg("--tail", 0.45), arg("--head", 0.0)   # heads hold breaths: opt in only after listening
    cuts = load(d, "cuts.json"); segs = cuts["segments"]; ov = load(d, "overrides.json", default={}) or {}
    joins = set(load(d, "transitions.json")["joins"])
    def env(seg, a, b):
        x, sr = sf.read(os.path.join(d, "audio", f"{seg['clip']}_48k.wav")); x = x if x.ndim == 1 else x.mean(1); h = int(0.02 * sr)
        ts = np.arange(max(a, 0), max(b, 0), 0.02)
        return ts, np.array([20 * np.log10(np.sqrt(np.mean(x[int(t * sr):int(t * sr) + h] ** 2)) + 1e-9) for t in ts]), x, sr
    for i in range(1, len(segs)):
        if segs[i]["key"] not in joins: continue
        a, b = segs[i - 1], segs[i]
        # outgoing tail: skip the last word's decay (<= 0.2 s), then extend through room tone, stop at a breath/sound
        _, ea, _, _ = env(a, 0, a["hi_lim"] - 0.05); thr = np.nanpercentile(ea, 15) + QUIET_DB
        ts, e, _, _ = env(a, a["out"], min(a["out"] + tail, a["hi_lim"] - 0.05))
        i = 0
        while i < len(e) and e[i] > thr and ts[i] < a["out"] + 0.2: i += 1
        j = i
        while j < len(e) and e[j] <= thr: j += 1
        new_out = max(a["out"], ts[j] if j < len(ts) else (ts[-1] + 0.02 if len(ts) else a["out"]))
        # incoming head: walk back from the cut through room tone only; never later than the current in point
        _, eb, _, _ = env(b, 0, b["hi_lim"] - 0.05); thr_b = np.nanpercentile(eb, 15) + QUIET_DB
        ts, e, _, _ = env(b, b["in"] - head, b["in"])
        k = len(e) - 1
        while k >= 0 and e[k] <= thr_b: k -= 1
        new_in = min(b["in"], ts[k + 1] if k + 1 < len(ts) else b["in"])
        print(f"  {a['key']} out {a['out']:.3f} -> {new_out:.3f}   {b['key']} in {b['in']:.3f} -> {new_in:.3f}")
        a["out"], b["in"] = round(float(new_out), 3), round(float(new_in), 3)
        ov.setdefault("out", {})[a["key"]] = a["out"]; ov.setdefault("in", {})[b["key"]] = b["in"]
    save(cuts, d, "cuts.json"); save(ov, d, "overrides.json")
    print("re-run assemble.py + validate_cut.py (these joins will show as DEAD AIR on purpose)")

def q(t): return round(t * 1000) / 1000

def dur(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                capture_output=True, text=True).stdout)

def render(d, cfg):
    global D
    tag = arg("--tag", "v1"); db = arg("--whoosh-db", -6.4); kind = arg("--kind", "push"); fps = cfg["fps"]
    if kind == "push":
        import push
        return push.render_push(d, cfg, tag, arg("--dur", 0.35), arg("--sfx", ASSET), arg("--sfx-peak", PEAK), db, load)
    D = arg("--dur", D)
    # separate face and screen files: the wipe belongs on the SCREEN cut, and the face track (composed later by
    # screen_bubble.py as a bubble or panel) gets the live, HELD, live switch over its whole frame
    sep = bool((cfg.get("screen_cuts") or {}).get(tag)) and not cfg.get("bubble")
    W, H = cfg["w"], cfg["h"]
    if sep:
        scr = os.path.join(d, cfg["screen_cuts"][tag])
        if not os.path.exists(scr): sys.exit(f"no screen cut {scr}: run assemble.py <ws> --no-punch --screen <folder> --tag {tag}")
        print(f"separate face and screen files: wiping {os.path.relpath(scr, d)}, switching the face inside each wipe")
    src = os.path.join(d, "cut", f"clean_{tag}.mp4"); tl = load(d, "cut", f"timeline_{tag}.json")
    segs = {s["key"]: s for s in load(d, "cuts.json")["segments"]}
    joins = set(load(d, "transitions.json")["joins"])
    # joins whose incoming pre-roll shows the speaker still looking at the record button: switch the bubble at the
    # picture cut instead of the wipe centre (trim the outgoing tail to its last frame on the lens first)
    at_cut = set(load(d, "transitions.json").get("bubble_at_cut", []))
    # Bubble across a transition pause: both sides look away there. The speaker turns to STOP the outgoing take
    # right after the last word, and is still turning back from the record button early in the incoming pre-roll
    # (only its last ~0.3 s before the first word is reliably on the lens). So: outgoing live until the last word ends
    # (+OUT_KEEP), then its frame HELD, then the incoming pre-roll live for only IN_PRE before the picture cut.
    # Per-join override in transitions.json: "bubble": {"<incoming key>": {"out_keep": -0.3, "in_pre": 0.2}}
    # (a negative out_keep freezes on a frame before the last word ends, for a speaker who glances down mid-word).
    bub_cfg = load(d, "transitions.json").get("bubble", {})
    OUT_KEEP, IN_PRE = arg("--out-keep", 0.04), arg("--in-pre", 0.30)
    wh = arg("--sfx", ASSET); peak = arg("--sfx-peak", PEAK)   # the approved whoosh ships with the skill
    total = dur(src)
    # each wipe + whoosh is centred in the PAUSE (speech stop -> speech resume), not on the picture cut, so the
    # whoosh never runs into a word; the picture side that is not there yet is a held edge frame (bubble stays live)
    cuts, cents, pre = [], [], []   # pre: (incoming source path, its in point, wipe centre, picture cut) for the bubble
    for k in range(1, len(tl)):
        if tl[k]["key"] not in joins: continue
        A, B = tl[k - 1], tl[k]; sa, sb = segs[A["key"]], segs[B["key"]]
        stop = A["out_start"] + sa["end"] - A["a_in"]; resume = B["out_start"] + max(sb["onset"], B["a_in"]) - B["a_in"]
        c = q((stop + resume) / 2)
        c = min(max(c, stop + 0.25), resume - 0.30) if resume - stop >= 0.55 else c
        cuts.append(B["out_start"]); cents.append(round(c * fps) / fps)
        o = bub_cfg.get(B["key"], {}); ok = float(o.get("out_keep", OUT_KEEP)); ip = float(o.get("in_pre", IN_PRE))
        sw = B["out_start"] if B["key"] in at_cut else max(B["out_start"] - ip, stop + ok)
        if sep:   # the face switches while both screens are visible: never the new face over the whole old screen
            c_ = round(c * fps) / fps; sw = min(max(sw, c_ - D / 2 + 1 / fps), c_ + D / 2 - 1 / fps)
        hold_t = min(stop + ok, sw)   # output time of the outgoing frame to hold until sw
        hold_src = A["v_in"] + (hold_t - A["v_out_start"])
        pre.append((sb["path"], sb["in"], q(sw), B["out_start"], B["key"], q(hold_t), sa["path"], hold_src))
        print(f"  {A['key']} -> {B['key']}: speech {stop:.2f} | {resume:.2f} (pause {resume - stop:.2f}s)  wipe+whoosh @ {c:.2f}"
              + ("   WARN pause < 0.55 s: whoosh will touch speech, widen with room" if resume - stop < 0.55 else ""))
    if not cuts: sys.exit("no transition joins in transitions.json")
    n_in = len(pre)
    head = f"[{2 + 2 * n_in}:v]fps={fps},format=yuv420p[base];[0:v]null[bub]" if sep else "[0:v]split=2[base][bub]"
    bounds = [0.0] + cuts + [total]; f = [head, f"[base]split={len(bounds) - 1}" + "".join(f"[s{i}]" for i in range(len(bounds) - 1))]
    for i in range(len(bounds) - 1):
        s0, e0 = bounds[i], bounds[i + 1]
        w0 = cents[i - 1] - D / 2 if i > 0 else 0.0; w1 = cents[i] + D / 2 if i < len(cents) else total
        t0, t1 = max(s0, w0), min(e0, w1); pad = []
        if s0 - w0 > 1e-6: pad.append(f"start_mode=clone:start_duration={s0 - w0:.6f}")
        if w1 - e0 > 1e-6: pad.append(f"stop_mode=clone:stop_duration={w1 - e0:.6f}")
        f.append(f"[s{i}]trim=start={t0:.6f}:end={t1:.6f},setpts=PTS-STARTPTS{',tpad=' + ':'.join(pad) if pad else ''},"
                 f"format=yuv444p,settb=1/{fps * 1000}[p{i}]")
    last = "p0"
    for i in range(1, len(bounds) - 1):
        f.append(f"[{last}][p{i}]xfade=transition={kind}:duration={D}:offset={cents[i - 1] - D / 2:.6f}[x{i}]"); last = f"x{i}"
    times = cents
    if sep:
        # the wiped screen is one output; the face track (full frame) gets the held frame + incoming pre-roll overlays
        f.append(f"[{last}]format=yuv420p[vscr]"); f.append(f"[bub]settb=1/{fps * 1000}[fv0]"); cur = "fv0"
        for j, (p, b_in, c, cut, key, ht, _, _) in enumerate(pre):
            if c - ht >= 1 / fps:
                f.append(f"[{2 + n_in + j}:v]scale={W}:{H},setsar=1,trim=end_frame=1,tpad=stop_mode=clone:stop_duration={c - ht + 0.2:.4f},"
                         f"fps={fps},format=yuv420p,setpts=PTS-STARTPTS+{ht:.6f}/TB[fh{j}]")
                f.append(f"[{cur}][fh{j}]overlay=0:0:eof_action=pass:enable='between(t,{ht:.4f},{c - 0.5 / fps:.4f})'[foh{j}]"); cur = f"foh{j}"
            if cut - c >= 1 / fps:
                f.append(f"[{2 + j}:v]scale={W}:{H},setsar=1,fps={fps},format=yuv420p,setpts=PTS-STARTPTS+{c:.6f}/TB[fp{j}]")
                f.append(f"[{cur}][fp{j}]overlay=0:0:eof_action=pass:enable='between(t,{c:.4f},{cut - 0.5 / fps:.4f})'[fov{j}]"); cur = f"fov{j}"
            print(f"  face {key}: outgoing live to {ht:.2f}, held to {c:.2f}, "
                  + (f"incoming pre-roll {c:.2f} -> cut {cut:.2f}" if cut - c >= 1 / fps else f"incoming from {c:.2f} (cut {cut:.2f})"))
        f.append(f"[{cur}]format=yuv420p[vcard]")
    elif cfg.get("bubble"):
        cx, cy, r = cfg["bubble"]; s = 2 * r
        f.append(f"[bub]crop={s}:{s}:{cx - r}:{cy - r},format=yuva420p,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':"
                 f"a='255*clip(({r}-hypot(X-{r},Y-{r}))/2,0,1)'[bm]")
        mask = f"format=yuva420p,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='255*clip(({r}-hypot(X-{r},Y-{r}))/2,0,1)'"
        f.append(f"[{last}]settb=1/{fps * 1000}[tv];[tv][bm]overlay={cx - r}:{cy - r}:shortest=1[ov0]"); cur = "ov0"
        n_in = len(pre)
        for j, (p, b_in, c, cut, _, ht, _, _) in enumerate(pre):
            if c - ht >= 1 / fps:   # held outgoing frame between the last word and the incoming pre-roll
                f.append(f"[{2 + n_in + j}:v]crop={s}:{s}:{cx - r}:{cy - r},trim=end_frame=1,{mask},tpad=stop_mode=clone:stop_duration={c - ht + 0.2:.4f},"
                         f"fps={fps},setpts=PTS-STARTPTS+{ht:.6f}/TB[ph{j}]")
                f.append(f"[{cur}][ph{j}]overlay={cx - r}:{cy - r}:eof_action=pass:enable='between(t,{ht:.4f},{c - 0.5 / fps:.4f})'[oh{j}]"); cur = f"oh{j}"
            if cut - c < 1 / fps: continue
            f.append(f"[{2 + j}:v]crop={s}:{s}:{cx - r}:{cy - r},fps={fps},{mask},setpts=PTS-STARTPTS+{c:.6f}/TB[pb{j}]")
            f.append(f"[{cur}][pb{j}]overlay={cx - r}:{cy - r}:eof_action=pass:enable='between(t,{c:.4f},{cut - 0.5 / fps:.4f})'[ov{j + 1}]"); cur = f"ov{j + 1}"
            print(f"  bubble {pre[j][4]}: outgoing live to {ht:.2f}, held to {c:.2f}, incoming pre-roll {c:.2f} -> cut {cut:.2f}")
        f.append(f"[{cur}]format=yuv420p[vcard]")
    else:
        f.append(f"[bub]nullsink;[{last}]format=yuv420p[vcard]")
    tj = load(d, "transitions.json"); card = tj.get("card")
    if card and sep:
        print("  card: drawn by screen_bubble.py --card for separate files, not here"); card = None
    if card:
        k = [x[4] for x in pre].index(card["before"]); t1 = cents[k] - D / 2; t0 = t1 - float(card.get("secs", 6))
        font = find_font(card.get("font", ""), bold=True)
        # text and font go through files next to the cut: no filtergraph escaping of quotes, colons or commas
        import shutil
        open(os.path.join(d, "cut", "_card.txt"), "w", encoding="utf-8").write(card["text"])
        if font: shutil.copy(font, os.path.join(d, "cut", "_card_font.ttf"))
        fp = "cut/_card_font.ttf" if font else ""
        alpha = f"if(lt(t,{t0 + 0.25:.3f}),(t-{t0:.3f})/0.25,if(gt(t,{t1 - 0.2:.3f}),({t1:.3f}-t)/0.2,1))"
        size = int(cfg["h"] * 0.030)   # 32 px at 1080p: 38 px ran 1,320 px wide and nearly met the bubble
        f.append(f"[vcard]drawtext=fontfile={fp}:textfile=cut/_card.txt:fontsize={size}:fontcolor=white:box=1:boxcolor=black@0.85:"
                 f"boxborderw={int(size * 0.55)}:x=(w-text_w)/2:y=h-text_h-{int(cfg['h'] * 0.075)}:alpha='{alpha}':"
                 f"enable='between(t,{t0:.3f},{t1:.3f})'[vout]")
        print(f"  card '{card['text']}' {t0:.2f} -> {t1:.2f} ({t1 - t0:.1f}s, ends as the {card['before']} wipe starts)")
    else:
        f.append("[vcard]null[vout]")
    f.append(f"[1:a]volume={db}dB,asplit={len(times)}" + "".join(f"[w{j}]" for j in range(len(times))))
    for j, t in enumerate(times):
        ms = int(round((t - peak) * 1000)); f.append(f"[w{j}]adelay={ms}|{ms}[wd{j}]")
    f.append("[0:a]aformat=channel_layouts=stereo[sp];[sp]" + "".join(f"[wd{j}]" for j in range(len(times))) +
             f"amix=inputs={len(times) + 1}:duration=first:normalize=0,alimiter=limit=0.84:level=false:latency=1[aout]")
    out = os.path.join(d, "cut", f"transitions_{tag}.mp4")
    extra = []
    for p, b_in, c, cut, *_ in pre:   # incoming clip pre-roll for the bubble, switch point -> picture cut
        if b_in - (cut - c) < 0: print(f"  WARN {_[0]}: only {b_in:.2f}s of pre-roll, needs {cut - c:.2f}s")
        extra += ["-ss", f"{max(b_in - (cut - c), 0):.4f}", "-t", f"{cut - c + 0.1:.4f}", "-i", p]
    for *_, hp, hs in pre:            # the outgoing frame held across the middle of the pause (inputs 2+n .. 2+2n-1)
        extra += ["-ss", f"{max(hs, 0):.4f}", "-t", "0.1", "-i", hp]
    enc = ["-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(fps)]
    if sep:
        so, fo = os.path.join(d, "cut", f"screen_wiped_{tag}.mp4"), os.path.join(d, "cut", f"face_wiped_{tag}.mp4")
        outs = ["-map", "[vscr]", "-an", *enc, "-movflags", "+faststart", so,
                "-map", "[vout]", "-map", "[aout]", *enc, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", fo]
        extra += ["-i", scr]
    else:
        outs = ["-map", "[vout]", "-map", "[aout]", *enc, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-i", wh] + extra + ["-filter_complex", ";".join(f)] + outs,
                       capture_output=True, text=True, cwd=d)
    if r.returncode: sys.exit(r.stderr[-2000:])
    if sep:
        cfg.setdefault("wiped_cuts", {})[tag] = {"screen": f"cut/screen_wiped_{tag}.mp4", "face": f"cut/face_wiped_{tag}.mp4"}
        save(cfg, d, "config.json")
        for t in times: print(f"  wipe @ {int(t // 60)}:{t % 60:05.2f}")
        print(f"{len(times)} transitions -> {so} + {fo} ({dur(fo):.3f}s, source {total:.3f}s). Next: "
              f"screen_bubble.py <ws> --tag {tag} [--panel] (uses them, writes cut/transitions_{tag}.mp4), then wipe_bubbles.py <ws> {tag}")
        return
    for t in times: print(f"  wipe @ {int(t // 60)}:{t % 60:05.2f}")
    print(f"{len(times)} transitions -> {out} ({dur(out):.3f}s, source {total:.3f}s)")

def main():
    d = os.path.abspath(sys.argv[1]); cmd = sys.argv[2] if len(sys.argv) > 2 else "detect"
    cfg = json.load(open(os.path.join(d, "config.json")))
    {"detect": detect, "room": room, "render": render}[cmd](d, cfg)

if __name__ == "__main__":
    main()
