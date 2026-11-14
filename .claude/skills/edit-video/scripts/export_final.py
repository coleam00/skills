"""Final export when there is no B-roll layer: the transitions render (cut/transitions_<tag>.mp4) gets a 1 s hold on
the last frame + 0.7 s fade out, two-pass loudnorm to -14 LUFS, limiter, a sync check against the clean cut
(finalize.py functions) and the .srt next to it (only if captions.py ran for this tag). Never overwrites: writes <dest>/<Name>_<tag>.mp4 and refuses if it exists.

  python export_final.py <ws> <tag> <dest_dir> <Name>

The hold exists because a speaker who looks down to stop the recording leaves no usable footage after the last word;
holding the last good frame under the fade ends the video without dead space and without the look-away."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import finalize
from common import load, run

if len(sys.argv) < 5: sys.exit(print(__doc__.strip()))
ws, tag, dest, name = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
FPS = json.load(open(os.path.join(ws, "config.json"), encoding="utf-8"))["fps"]
HOLD, FADE = 1.0, 0.7
src = os.path.join(ws, "cut", f"transitions_{tag}.mp4"); clean = os.path.join(ws, "cut", f"clean_{tag}.mp4")
os.makedirs(dest, exist_ok=True)
# named by the cut's tag (v3 -> Name_v3.mp4) so a version moved to superseded/ can't free its number for reuse
out = os.path.join(dest, f"{name}_{tag}.mp4")
if os.path.exists(out): sys.exit(f"{out} exists; never overwrite an export, use a new --tag")
tmp = os.path.join(ws, "cut", f"_held_{tag}.mkv")
dur = float(os.popen(f'ffprobe -v error -show_entries format=duration -of csv=p=0 "{src}"').read()); T = dur + HOLD
run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", f"tpad=stop_mode=clone:stop_duration={HOLD},fade=t=out:st={T - FADE:.3f}:d={FADE}",
     "-af", f"apad=pad_dur={HOLD},afade=t=out:st={T - FADE:.3f}:d={FADE}", "-t", f"{T:.3f}",
     "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "pcm_s16le", tmp])
j = finalize.lufs(tmp)
# The AAC encode adds inter-sample peaks after the limiter, so a fixed limit can land over the -1.5 dBTP gate (Fable
# v1 11/13: -1.39 with limit 0.70). Measure the ENCODED file and step the limit down until it passes.
part = out[:-4] + ".part.mp4"
for lim in (0.70, 0.63, 0.56, 0.50):
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:"
          f"measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true,alimiter=limit={lim}:level=disabled:latency=1,aresample=48000")
    run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-af", ln, "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", part])
    j2 = finalize.lufs(part)
    if float(j2["input_tp"]) <= -1.5: break
    print(f"  true peak {j2['input_tp']} dBTP with limit {lim}: over -1.5, re-encoding with a lower limit")
os.replace(part, out)
lags, da, db_ = finalize.lag_ms(out, clean, ws)
cap = load(ws, "cut", f"captions_{tag}.json")
ts = lambda t: "%02d:%02d:%02d,%03d" % (int(t // 3600), int(t % 3600 // 60), int(t % 60), int(round((t % 1) * 1000)) % 1000)
if cap: open(out[:-4] + ".srt", "w", encoding="utf-8").write("\n".join(f"{i + 1}\n{ts(g['s'])} --> {ts(g['e'])}\n{g['text']}\n" for i, g in enumerate(cap["groups"])))
print(f"{out}\n  loudness {j2['input_i']} LUFS, true peak {j2['input_tp']} dBTP, LRA {j2['input_lra']}\n  sync {lags} ms\n"
      f"  duration {da:.3f}s = clean {db_:.3f}s + hold {HOLD}s -> diff {da - db_ - HOLD:+.3f}s")
