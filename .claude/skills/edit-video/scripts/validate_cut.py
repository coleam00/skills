"""Validate a clean cut: nothing lost, no dead air, no breaths, no clicks, clean picture at every join.

Usage: uv run --project $S python validate_cut.py <ws> [--tag v1]
1. Re-transcribes the output and diffs it word-by-word against the source transcripts (any DIFF that is not an ASR
   spelling variant - e.g. a missing final word, "actions" -> "action" - means a tail was clipped: re-run cutpoints).
2. For every join: silence between last sound and next sound (target 0.15-0.25 s; > 0.3 s = dead air;
   0.0 = the cut lands on sound) and the sample jump at the cut (clicks). TAIL ON SOUND: the source is still loud at
   the out point and keeps sounding > 0.1 s, i.e. the last word's decay was clipped.
3. Writes check/joins_<tag>.png: 4 frames before and after every picture cut, for the visual read.
Writes cut/words_<tag>.json (output-timeline words) for captions.py.
"""
import difflib, io, json, os, re, subprocess, sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import envelope, load, p, read_wav, save, whisper_model, ws, HOP
from eye_strip import font

def main():
    d, cfg = ws(); tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "v1"
    vid = os.path.join(d, "cut", f"clean_{tag}.mp4"); tl = load(d, "cut", f"timeline_{tag}.json"); W = load(d, "words.json")
    a = p(d, "check", f"_clean_{tag}.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", vid, "-ac", "1", "-ar", "48000", a], check=True)
    x, sr = read_wav(a)
    m = whisper_model("large-v3")
    # 1 s of silence first: a word on frame one ("And it also...") was heard as "That also", a false DIFF at the head
    from scipy.signal import resample_poly
    a16 = np.concatenate([np.zeros(16000, np.float32), resample_poly(x, 1, sr // 16000).astype(np.float32)])
    segs, _ = m.transcribe(a16, language=cfg.get("language", "en"), word_timestamps=True, beam_size=5, condition_on_previous_text=False)
    got_w = [w for s in segs for w in s.words]
    norm = lambda s: re.sub(r"[^a-z0-9']", "", s.lower())
    inseg = lambda w, s: w["e"] > s["a_in"] + 0.03 and w["s"] < s["a_out"] - 0.03   # overlap, not start: Whisper stamps first words at 0.0
    src = [norm(w["w"]) for s in tl for w in W[s["clip"]] if inseg(w, s)]
    got = [norm(w.word) for w in got_w]
    sm = difflib.SequenceMatcher(a=src, b=got, autojunk=False)
    print(f"WORDS source {len(src)} output {len(got)} similarity {sm.ratio():.4f}")
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op != "equal": print(f"   DIFF {op}: {' '.join(src[a0:a1])!r} -> {' '.join(got[b0:b1])!r}")
    db = envelope(x, sr); thr = np.percentile(db[db > -60], 60) - 14
    print("JOINS  (cut @ t | silence | click ratio)")
    bad = 0
    for s in tl[:-1]:
        t = s["out_end"]; i = int(t / HOP); a_ = i
        while a_ > 0 and db[a_] < thr: a_ -= 1
        b_ = i
        while b_ < len(db) - 1 and db[b_] < thr: b_ += 1
        gap = (b_ - a_) * HOP; k = int(t * sr); seg = x[max(0, k - 240):k + 240]
        jump = np.abs(np.diff(seg)).max() / (np.abs(np.diff(x[max(0, k - 4800):k - 240])).mean() + 1e-9)
        flag = "DEAD AIR" if gap > 0.3 else ("ON SOUND" if gap < 0.03 else "")
        bad += bool(flag)
        print(f"  {s['key']:9} @ {t:7.2f} | {gap:5.3f}s | {jump:5.1f}x  {flag}")
    # A clipped decay hides from the pause measure above (the cut is followed by silence either way), so read the
    # SOURCE at each out point: still loud in the last 30 ms and sounding on for > 0.1 s means the word was cut
    env = {}
    for s in tl[:-1]:
        if s["clip"] not in env:
            y, ysr = read_wav(p(d, "audio", f"{s['clip']}_48k.wav")); e = envelope(y, ysr)
            env[s["clip"]] = (e, np.percentile(e[e > e.max() - 60], 60) - 38)
        e, room = env[s["clip"]]; i = int(s["a_out"] / HOP); j = i
        last = e[max(0, i - int(0.03 / HOP)):i].mean()
        while j < len(e) - 1 and e[j] > room: j += 1
        if last > room + 12 and (j - i) * HOP > 0.1:
            bad += 1; print(f"  {s['key']:9} TAIL ON SOUND: {last:.0f} dB at the cut, word sounds {(j - i) * HOP:.2f}s past it (move out to ~{j * HOP:.2f})")
    print(f"{bad} joins flagged")
    # per-segment integrated loudness on the cut: a spread over ~1.5 LU means re-assemble with --level
    lv = []
    for s in tl:
        if s["out_end"] - s["out_start"] < 3: continue          # ebur128's integrated value needs a few seconds
        r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", f"{s['out_start']:.3f}", "-t", f"{s['out_end'] - s['out_start']:.3f}", "-i", a,
                            "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
        v = re.findall(r"I:\s+(-?[\d.]+) LUFS", r)
        if v: lv.append((s["key"], float(v[-1])))
    if lv:
        spread = max(v for _, v in lv) - min(v for _, v in lv)
        print("LEVELS  " + "  ".join(f"{k} {v:.1f}" for k, v in lv) + f"  | spread {spread:.1f} LU" + ("  RE-ASSEMBLE WITH --level" if spread > 1.5 else ""))
    F = font(14); rows = []; tw = 160 if cfg["h"] > cfg["w"] else 240; th = int(tw * cfg["h"] / cfg["w"])
    for s in tl[:-1]:
        t = s["v_out_end"]; ims = []
        for k in range(8):
            tt = t - 8 / cfg["fps"] + k * 2 / cfg["fps"]
            b = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{tt:.4f}", "-i", vid, "-frames:v", "1", "-vf", f"scale={tw}:{th}",
                                "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
            ims.append((tt, Image.open(io.BytesIO(b)).convert("RGB")))
        rows.append((s["key"], ims))
    sh = Image.new("RGB", (8 * (tw + 4) + 90, len(rows) * (th + 22)), (0, 0, 0)); dr = ImageDraw.Draw(sh)
    for r, (k, ims) in enumerate(rows):
        y = r * (th + 22); dr.text((2, y + th // 2), k, font=F, fill=(255, 255, 255))
        for i, (tt, im) in enumerate(ims):
            xx = 90 + i * (tw + 4); sh.paste(im, (xx, y + 18)); dr.text((xx, y + 2), f"{tt:.2f}{'|CUT' if i == 4 else ''}", font=F, fill=(255, 90, 90) if i == 4 else (220, 220, 220))
    sh.save(p(d, "check", f"joins_{tag}.png")); print("wrote", os.path.join(d, "check", f"joins_{tag}.png"))
    out_words = []
    for s in tl:
        for w in W[s["clip"]]:
            if inseg(w, s):
                out_words.append({"w": w["w"], "s": round(max(s["out_start"], s["out_start"] + w["s"] - s["a_in"]), 3),
                                  "e": round(min(s["out_end"], s["out_start"] + w["e"] - s["a_in"]), 3), "seg": s["key"]})
    save(out_words, d, "cut", f"words_{tag}.json")

if __name__ == "__main__":
    main()
