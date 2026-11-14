"""Find takes whose camera file starts late or stops early while the speaker is talking, and rebuild them from a
longer recording of the same take.

Usage: python pad_takes.py <ws> [--long "<folder>/<glob>"] [--apply] [--keys c04,c21] [--force] [--all] [--inset x,y,w,h]

Recorders that write the camera as its own file (OBS Source Record and similar) can START it up to ~3 s after the
main recording and STOP it ~1 s before. When a word runs into either edge the clip opens or ends mid-word, and NO later
gate can see it: cutpoints, validate_cut and TAIL ON SOUND only hear what the file holds, and the transcript still
prints the clipped word (or silently starts mid-sentence).

- Report (default): the level of each clip's last 0.15 s. `ENDS ON SOUND` means it was cut off while the voice was
  still sounding (louder than its floor + 12 dB, or above -50 dBFS, which is a word still decaying).
- --long: the longer recordings of the same takes (the recorder's composite, or any file carrying the same mic),
  paired with the clips in order (the glob must match exactly one file per clip). Adds, per clip: where the clip
  starts inside the long file, `STARTS ON SOUND` when the long file has speech in the seconds before the clip begins,
  and whether the long file is still sounding right after the clip ends.
- --apply (with --long): rebuilds every flagged clip from the long file's audio: the missing head (up to 3 s) and/or
  the missing tail, into <ws>/clips_long/<same file name>, and points config.json at it. The source is never touched.
  The picture for a missing tail is the clip's last frame held. For a missing head it is the clip's first frame held,
  unless --inset gives the camera's box inside the long file (e.g. 1470,826,450,254 for a corner camera), which is
  then scaled up and played instead, so the face keeps moving while the speaker talks.
- --keys c04,c21: report and rebuild only these clips. --force: rebuild them even if not flagged (when you can hear
  a clipped word the levels missed).
- --all: rebuild EVERY clip on the long file's audio (= --force on all keys). For when the camera files carry recorder
  buffer skips and the long recordings do not (fix_skips.py --report --long tells): the rebuilt clips then carry clean
  audio, which restores what was dropped instead of smoothing the click. Re-run transcribe.py and cutpoints.py after,
  and check every out point that moved by more than 0.1 s against the old cuts.json (cutting.md, "After an audio swap").
Run it after init_workspace.py and before transcribe.py, so every later step reads the rebuilt clip. If transcribe.py
already ran, run it again (it refreshes the audio and words of rebuilt clips), then cutpoints.py.
"""
import glob, os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import ws, save, probe, load

SR = 16000
HEAD_MAX = 3.0          # seconds of missing head to restore at most
ABS_TAIL = -50.0        # dBFS: a clip ending above this is still sounding (a word decaying), whatever its floor
SPEECH = -45.0          # dBFS of a 100 ms window that counts as speech in the long file before the clip starts


def pcm(f, ss=0.0, t=None):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{ss:.3f}", "-i", f] + (["-t", f"{t:.3f}"] if t else []) + \
          ["-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.int16).astype(np.float32) / 32768


def db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9) if len(x) else -120.0


def windows(x, w=0.1):
    n = int(w * SR); fr = x[: len(x) // n * n].reshape(-1, n)
    return 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9) if len(fr) else np.array([-120.0])


def end_level(a):
    """(level of the last 0.15 s, noise floor) in dB; the floor is the 10th percentile of 50 ms windows."""
    return db(a[-int(0.15 * SR):]), float(np.percentile(windows(a, 0.05), 10))


def lag(short, long_, secs=20, search=6):
    """Seconds into the long file where the short file starts (cross-correlation of the first `secs`)."""
    a, b = short[: SR * secs], long_[: SR * (secs + search)]
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    c = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)
    k = int(np.argmax(c)); k = k - n if k > n // 2 else k
    return k / SR


def rebuild(src, L, out, g, head, tail_to, dur, inset, fps):
    """Clip = [head s of L before the clip] + clip + [L's tail up to tail_to]; audio all from L."""
    a0, a1 = g - head, tail_to
    hold_tail = max(0.0, a1 - (g + dur)) + 1.0
    if head > 0 and inset:
        x, y, w, h = inset
        pr = probe(src)
        fc = (f"[1:v]trim=start={a0:.4f}:end={g:.4f},setpts=PTS-STARTPTS,crop={w}:{h}:{x}:{y},"
              f"scale={pr['w']}:{pr['h']}:flags=lanczos,fps={fps},setsar=1,format=yuv420p[hv];"
              f"[0:v]fps={fps},setsar=1,format=yuv420p,tpad=stop_mode=clone:stop_duration={hold_tail:.2f}[cv];"
              f"[hv][cv]concat=n=2:v=1:a=0[v]")
    else:
        fc = (f"[0:v]fps={fps},setsar=1,format=yuv420p,tpad=start_mode=clone:start_duration={head:.4f}:"
              f"stop_mode=clone:stop_duration={hold_tail:.2f}[v]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-i", L, "-filter_complex",
                    fc + f";[1:a:0]atrim=start={a0:.4f}:end={a1:.4f},asetpts=PTS-STARTPTS[a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "14", "-preset", "veryfast",
                    "-c:a", "flac", "-t", f"{a1 - a0:.3f}", out], check=True)


def main():
    d, cfg = ws(); a = sys.argv
    longs = sorted(glob.glob(a[a.index("--long") + 1])) if "--long" in a else []
    keys = set(a[a.index("--keys") + 1].split(",")) if "--keys" in a else None
    inset = [int(v) for v in a[a.index("--inset") + 1].split(",")] if "--inset" in a else None
    force = "--force" in a or "--all" in a
    clips = cfg["clips"]
    if longs and len(longs) != len(clips): sys.exit(f"--long matched {len(longs)} files for {len(clips)} clips: narrow the glob")
    changed = 0
    for i, c in enumerate(clips):
        if keys and c["key"] not in keys: continue
        src = c.get("padded_from", c["path"]); x = pcm(src)
        lvl, floor = end_level(x)
        hot_tail = lvl > floor + 12 or lvl > ABS_TAIL
        line = f"{c['key']}  last 0.15 s {lvl:6.1f} dB  floor {floor:6.1f} dB  {'ENDS ON SOUND' if hot_tail else 'ok'}"
        if longs:
            L = longs[i]; y = pcm(L); g = lag(x, y); dur = len(x) / SR
            extra = len(y) / SR - g - dur
            e = int((g + dur) * SR); post = db(y[e:e + int(0.15 * SR)]); lfloor = end_level(y)[1]
            if post > lfloor + 12 and post > -60: hot_tail = True     # the long file still sounding right after the clip
            pre = y[int(max(0.0, g - 1.5) * SR): int(g * SR)]
            hot_head = g > 0.15 and len(pre) > 0 and windows(pre).max() > SPEECH
            line = line.replace("  ok", "  ENDS ON SOUND") if hot_tail else line
            line += (f"  | starts {g:+.2f} s into {os.path.basename(L)}"
                     f"{'  STARTS ON SOUND' if hot_head else ''}; after the end: {post:6.1f} dB, runs {extra:+.2f} s longer")
            every = "--all" in a and g >= 0          # --all: every clip gets the long file's audio, even one it already covers
            if "--all" in a and g < 0: line += "  (starts before the long file: kept as is)"
            if "--apply" in a and (every or (hot_head or hot_tail or force) and (extra > 0.2 or (hot_head or force) and g > 0.15)):
                head = min(g, HEAD_MAX) if (hot_head or (force and g > 0.15)) else 0.0
                tail_to = len(y) / SR if (hot_tail or force) and extra > 0.2 else g + dur
                out = os.path.join(d, "clips_long", os.path.basename(src)); os.makedirs(os.path.dirname(out), exist_ok=True)
                rebuild(src, L, out, g, head, tail_to, dur, inset, cfg.get("fps", 60))
                c["padded_from"] = src; c["path"] = out; c["dur"] = round(probe(out)["dur"], 3)
                c["head_padded"] = round(head, 3); changed += 1
                line += f"  -> rebuilt {c['dur']:.2f} s (head +{head:.2f} s{', camera inset' if head and inset else ', first frame held' if head else ''})"
        print(line, flush=True)
    if changed:
        save(cfg, d, "config.json")
        words = load(d, "words.json") or {}        # transcribe.py skips clips it has words for: drop the stale ones
        stale = [c["key"] for c in clips if c.get("padded_from") and c["key"] in words]
        if stale:
            for k in stale: words.pop(k)
            save(words, d, "words.json")
        print(f"{changed} clip(s) rebuilt in clips_long/ (same file names, so assemble.py --screen still pairs them).")
        print("If transcribe.py already ran, run it again (it refreshes their audio and words), then cutpoints.py.")
    if not inset and any(c.get("head_padded") for c in clips):
        print("Note: restored heads show the first camera frame held. With --inset the camera inside the long file plays instead.")


if __name__ == "__main__":
    main()
