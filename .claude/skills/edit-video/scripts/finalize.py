"""Final export: high-quality render -> loudness -> peak limit -> sync check -> captions file, into a NEW folder.

Usage: python finalize.py <ws> <name> <deliverable-name> [--tag v1] [--dest <folder>] [--lufs -14] [--use-raw] [--hold] [--deband]
       python finalize.py <ws> --clean <deliverable-name>     # the clean cut itself (no graphics, no burned captions)
- Never overwrites: writes <dest>/<deliverable-name>_vN.mp4 with N = next free number (default dest = <source>/final).
- Loudness: two-pass loudnorm to -14 LUFS (web/social), then alimiter with latency=1 (the limiter otherwise delays
  audio by its 5 ms lookahead) so true peak lands near -2 dBTP after AAC encoding.
- Verifies audio sync against the clean cut by cross-correlation at four points (must be +0.0 ms) and durations.
- Writes the matching .srt next to the video.
"""
import json, os, subprocess, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load, read_wav, run, ws

def lufs(path):
    m = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True).stderr
    j = json.loads(m[m.rindex("{"):m.rindex("}") + 1]); return j

def lag_ms(a_path, b_path, d):
    out = []
    for i, p_ in enumerate((a_path, b_path)):
        w = os.path.join(d, "check", f"_sync{i}.wav"); run(["ffmpeg", "-v", "error", "-y", "-i", p_, "-ac", "1", "-ar", "16000", w]); out.append(read_wav(w)[0])
    a, b = out; res = []
    for t0 in (5, len(b) / 16000 * 0.33, len(b) / 16000 * 0.66, len(b) / 16000 - 8):
        i = int(t0 * 16000); sb = b[i:i + 48000]; best = (-1, 0)
        for lag in range(-1600, 1601, 8):
            sa = a[i + lag:i + lag + len(sb)]
            if len(sa) < len(sb) or i + lag < 0: continue
            c = float(np.dot(sa, sb) / (np.linalg.norm(sa) * np.linalg.norm(sb) + 1e-9))
            if c > best[0]: best = (c, lag)
        res.append(best[1] / 16)
    return res, len(a) / 16000, len(b) / 16000

def main():
    d, cfg = ws(); a = sys.argv; name, deliver = a[2], a[3]
    tag = a[a.index("--tag") + 1] if "--tag" in a else "v1"
    target = a[a.index("--lufs") + 1] if "--lufs" in a else "-14"
    src = cfg["source"]; dest = a[a.index("--dest") + 1] if "--dest" in a else os.path.join(src if os.path.isdir(src) else os.path.dirname(src), "final")
    os.makedirs(dest, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(dest, f"{deliver}_v{n}.mp4")): n += 1
    out = os.path.join(dest, f"{deliver}_v{n}.mp4")
    if name == "--clean":
        raw = os.path.join(d, "cut", f"clean_{tag}.mp4")
    else:
        raw = os.path.join(d, "hf", name, "out", f"{name}_final_raw.mp4")
    # --use-raw: the high render already exists (a chunked render.py run of a long page); don't spend another hour on it
    reuse = "--use-raw" in a and os.path.exists(raw)
    r = None if name == "--clean" or reuse else subprocess.run(f'"{sys.executable}" "{os.path.join(os.path.dirname(os.path.abspath(__file__)), "render.py")}" "{d}" {name} --quality high --out "{raw}" --skip-inspect', shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if r is not None: print(r.stdout[-400:])
    if not os.path.exists(raw): sys.exit(r.stderr[-1500:] if r else f"missing {raw}")
    hold = 1.0 if "--hold" in a else 0.0
    if hold:   # export_final.py's ending: the last frame held 1 s under a 0.7 s fade (the speaker looks down to stop recording)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", raw], capture_output=True, text=True).stdout)
        T = dur + hold; held = raw[:-4] + "_held.mkv"
        run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-vf", f"tpad=stop_mode=clone:stop_duration={hold},fade=t=out:st={T - 0.7:.3f}:d=0.7",
             "-af", f"apad=pad_dur={hold},afade=t=out:st={T - 0.7:.3f}:d=0.7", "-t", f"{T:.3f}", "-c:v", "libx264", "-crf", "16", "-preset", "slow",
             "-pix_fmt", "yuv420p", "-r", str(cfg["fps"]), "-c:a", "pcm_s16le", held])
        raw = held
    j = lufs(raw)
    ln = (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:"
          f"measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true,alimiter=limit=0.66:level=disabled:latency=1,volume=0.3dB,aresample=48000")   # 0.70 landed -1.1 dBTP after AAC on a HyperFrames render
    # --deband: dark gradients band after several encodes (it reads as a choppy background). Smooth the steps, add a faint
    # STATIC grain (no t flag, so it never shimmers) and encode tuned for grain so the dither survives. Faces are unchanged.
    vopt = (["-vf", "deband=1thr=0.012:2thr=0.012:3thr=0.012:range=24:blur=1,noise=alls=3:allf=u", "-c:v", "libx264", "-crf", "14",
             "-preset", "slow", "-tune", "grain", "-pix_fmt", "yuv420p"] if "--deband" in a else ["-c:v", "copy"])
    run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-map", "0:v:0", "-map", "0:a:0", *vopt, "-af", ln, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    j2 = lufs(out); lags, da, db_ = lag_ms(out, os.path.join(d, "cut", f"clean_{tag}.mp4"), d)
    cap = load(d, "cut", f"captions_{tag}.json")
    ts = lambda t: "%02d:%02d:%02d,%03d" % (int(t // 3600), int(t % 3600 // 60), int(t % 60), int(round((t % 1) * 1000)) % 1000)
    if cap: open(out[:-4] + ".srt", "w", encoding="utf-8").write("\n".join(f"{i + 1}\n{ts(g['s'])} --> {ts(g['e'])}\n{g['text']}\n" for i, g in enumerate(cap["groups"])))
    ok = all(abs(x) < 0.5 for x in lags) and abs(da - db_ - hold) < 0.05
    print(f"{out}\n  loudness {j2['input_i']} LUFS, true peak {j2['input_tp']} dBTP\n  sync {lags} ms, duration {da:.3f}s vs clean {db_:.3f}s  {'OK' if ok else 'CHECK'}")

if __name__ == "__main__":
    main()
