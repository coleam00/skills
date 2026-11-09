"""The same finished video with the cut's audio rebuilt from other sources (e.g. the clips before fix_skips.py).

Usage: uv run --project $S python swap_audio.py <ws> <final.mp4> <tag> <cuts.json with the other source paths> <out.mp4>

Rebuilds the audio exactly as assemble.py does for <tag> (timeline_<tag>.json trims, per-segment gain, micro-fades,
concat, 70 Hz high-pass, two-pass linear loudnorm), pads the end hold + fade the final carries, then finalize's
-14 LUFS + limiter, and muxes it onto <final.mp4> with the video stream copied. Prints loudness and the lag against the
final's own audio (must be 0.0 ms). For when the speaker wants a version without a repair, to run through their own tools.
"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import finalize
from common import load, run, ws

FADE_IN, FADE_OUT = 0.008, 0.015   # assemble.py

def main():
    d, cfg = ws(); final, tag, cuts_path, out = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
    if os.path.exists(out): sys.exit(f"{out} exists; never overwrite an export")
    tl = load(d, "cut", f"timeline_{tag}.json"); src = {s["key"]: s["path"] for s in json.load(open(cuts_path))["segments"]}
    paths = []; fa = []
    for s in tl:
        p = src[s["key"]]
        if p not in paths: paths.append(p)
    inputs = sum((["-i", p] for p in paths), [])
    for i, s in enumerate(tl):
        n = paths.index(src[s["key"]]); ad = s["a_out"] - s["a_in"]
        fa.append(f"[{n}:a]atrim=start={s['a_in']:.6f}:end={s['a_out']:.6f},asetpts=PTS-STARTPTS,aresample=48000,volume={s.get('gain_db', 0)}dB,"
                  f"afade=t=in:st=0:d={FADE_IN},afade=t=out:st={ad - FADE_OUT:.6f}:d={FADE_OUT}[a{i}]")
    filt = ";".join(fa) + ";" + "".join(f"[a{i}]" for i in range(len(tl))) + f"concat=n={len(tl)}:v=0:a=1,highpass=f=70[ac]"
    pre = os.path.join(d, "cut", f"_swap_pre_{tag}.wav")
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", filt, "-map", "[ac]", "-c:a", "pcm_s16le", pre])
    j = finalize.lufs(pre)
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:"
          f"measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true,aresample=48000")
    cutwav = os.path.join(d, "cut", f"_swap_cut_{tag}.wav"); run(["ffmpeg", "-v", "error", "-y", "-i", pre, "-af", ln, "-c:a", "pcm_s16le", cutwav])
    fd = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", final], capture_output=True, text=True).stdout)
    ad = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", cutwav], capture_output=True, text=True).stdout)
    hold = max(0.0, round(fd - ad, 3))                              # the final's end hold (1 s), if it has one
    held = os.path.join(d, "cut", f"_swap_held_{tag}.wav")
    af = f"apad=pad_dur={hold},afade=t=out:st={fd - 0.7:.3f}:d=0.7" if hold > 0.2 else "anull"
    run(["ffmpeg", "-v", "error", "-y", "-i", cutwav, "-af", af, "-t", f"{fd:.3f}", "-c:a", "pcm_s16le", held])
    j = finalize.lufs(held)
    ln2 = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:"
           f"measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true,alimiter=limit=0.70:level=disabled:latency=1,aresample=48000")   # export_final.py's ceiling
    run(["ffmpeg", "-v", "error", "-y", "-i", final, "-i", held, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af", ln2,
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out])
    for f in (pre, cutwav, held): os.remove(f)
    j2 = finalize.lufs(out); lags, da, db_ = finalize.lag_ms(out, final, d)
    srt = final[:-4] + ".srt"
    if os.path.exists(srt): open(out[:-4] + ".srt", "w", encoding="utf-8").write(open(srt, encoding="utf-8").read())
    print(f"{out}\n  loudness {j2['input_i']} LUFS, true peak {j2['input_tp']} dBTP\n  lag vs {os.path.basename(final)}: {lags} ms, "
          f"duration {da:.3f}s vs {db_:.3f}s")

if __name__ == "__main__":
    main()
