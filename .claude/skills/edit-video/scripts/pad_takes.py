"""Find takes whose camera file stops while the speaker is still sounding, and rebuild them from a longer recording.

Usage: python pad_takes.py <ws> [--long "<folder>/<glob>"] [--apply]

Recorders that write the camera as its own file (OBS Source Record and similar) often stop it ~1 s before the main
recording. When the last word runs into that edge, the clip ends mid-word and NO later gate can see it: cutpoints,
validate_cut and TAIL ON SOUND only hear what the file holds, and Whisper still prints the clipped word.

- Report (default): the level of each clip's last 0.15 s against its own noise floor. `ENDS ON SOUND` means the
  file was cut off while the voice was still sounding.
- --long: the longer recordings of the same takes (the recorder's composite, or any file carrying the same mic),
  paired with the clips in order (the glob must match exactly one file per clip). Prints how much longer each runs.
- --apply (with --long): rebuilds every ENDS ON SOUND clip as the camera picture (its last frame held) + the long
  file's audio, into <ws>/clips_long/<same file name>, and points config.json at it. The source is never touched.
Run it after init_workspace.py and before transcribe.py, so every later step reads the rebuilt clip.
"""
import glob, os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import ws, save, probe

SR = 16000

def pcm(f, ss=0.0, t=None):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{ss:.3f}", "-i", f] + (["-t", f"{t:.3f}"] if t else []) + \
          ["-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.int16).astype(np.float32) / 32768

def db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)

def end_level(a):
    """(level of the last 0.15 s, noise floor) in dB; the floor is the 10th percentile of 50 ms windows."""
    w = int(0.05 * SR); fr = a[: len(a) // w * w].reshape(-1, w)
    floor = np.percentile(20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9), 10)
    return db(a[-int(0.15 * SR):]), floor

def lag(short, long_, secs=20):
    """Seconds into the long file where the short file starts (cross-correlation of the first `secs`)."""
    a, b = short[: SR * secs], long_[: SR * (secs + 3)]
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    c = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)
    k = int(np.argmax(c)); k = k - n if k > n // 2 else k
    return k / SR

def main():
    d, cfg = ws(); a = sys.argv
    longs = sorted(glob.glob(a[a.index("--long") + 1])) if "--long" in a else []
    clips = cfg["clips"]
    if longs and len(longs) != len(clips): sys.exit(f"--long matched {len(longs)} files for {len(clips)} clips: narrow the glob")
    changed = 0
    for i, c in enumerate(clips):
        src = c.get("padded_from", c["path"]); x = pcm(src)
        lvl, floor = end_level(x); hot = lvl > floor + 12
        line = f"{c['key']}  last 0.15 s {lvl:6.1f} dB  floor {floor:6.1f} dB  {'ENDS ON SOUND' if hot else 'ok'}"
        if longs:
            L = longs[i]; y = pcm(L); g = lag(x, y); extra = len(y) / SR - g - len(x) / SR
            e = int((g + len(x) / SR) * SR); post = db(y[e:e + int(0.15 * SR)]); lfloor = end_level(y)[1]
            hot = hot or post > lfloor + 12        # the long file still sounding right after the clip's end decides it
            line = line.replace("ok", "ENDS ON SOUND") if hot and line.endswith("ok") else line
            line += f"  | next 0.15 s in {os.path.basename(L)}: {post:6.1f} dB (floor {lfloor:6.1f}), runs {extra:+.2f} s longer"
            if hot and "--apply" in a and extra > 0.2:
                out = os.path.join(d, "clips_long", os.path.basename(src)); os.makedirs(os.path.dirname(out), exist_ok=True)
                end = len(y) / SR - g
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-ss", f"{g:.4f}", "-i", L,
                                "-filter_complex", f"[0:v]tpad=stop_mode=clone:stop_duration={extra + 1:.2f}[v]",
                                "-map", "[v]", "-map", "1:a:0", "-c:v", "libx264", "-crf", "14", "-preset", "veryfast",
                                "-c:a", "flac", "-t", f"{end:.3f}", out], check=True)
                c["padded_from"] = src; c["path"] = out; c["dur"] = round(probe(out)["dur"], 3); changed += 1
                line += f"  -> rebuilt {c['dur']:.2f} s"
        print(line, flush=True)
    if changed:
        save(cfg, d, "config.json")
        print(f"{changed} clip(s) rebuilt in clips_long/ (same file names, so assemble.py --screen still pairs them).")
        print("If transcribe.py already ran, run it again: the words and audio of those clips changed.")

if __name__ == "__main__":
    main()
