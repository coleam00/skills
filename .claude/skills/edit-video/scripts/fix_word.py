"""Fix a misspoken word or line in the speaker's own cloned voice, without re-recording. Full pipeline (OpenRouter).
Only with the speaker's consent: it sends a clip of their voice to the voice provider.

Usage: python fix_word.py <ws> <clip> <start> <end> "<corrected words for that stretch>" [--candidates 3 | --use <gen.mp3>]
                          [--model <id>] [--tries 3] [--ref-secs 25]

- <start> <end>: clip seconds around the words to replace. Both edges snap to the quietest moment within 0.3 s, so
  the span is bounded by pauses (a swap inside connected speech sounds choppy). Give the corrected text for the WHOLE
  span, e.g. span "we use the MDA engine" -> "we use LangSmith Engine".
- The clone hears the line itself (the span plus ~4 s, with its transcript: the pitch and pace of this sentence) and
  clean speech from the same recording, about 25 s in all. 8 s of reference sounded unlike the speaker.
- Natural speed: never slowed down (a stretched line sounded slow and odd), sped up at most 8% if it runs long; a
  shorter take leaves room tone, not silence. Level-matched, crossfaded 40 ms at both edges.
- --candidates N: generate N takes, write a listening file for each (3 s either side), apply nothing. The speaker
  picks by ear, then --use <that take's gen file> applies it. Without either, the first take that verifies is applied.
- Verified: the span is transcribed and must read as the corrected words (removed words gone, new words heard).
- Writes clips_fixed/<same file name> (picture untouched, new audio), points config.json at it, refreshes that clip's
  words. The source file is never touched. Then re-run cutpoints.py and assemble.py as usual.
Keep an export of the original voice too: the speaker may prefer to re-record the line.
"""
import difflib, json, os, re, subprocess, sys, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import asr_model, envelope, load, read_wav, save, wav, ws, HOP
import openrouter

SR = 48000
TRIM = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"   # trim both ENDS only: stop_periods cut at the first gap
        "silenceremove=start_periods=1:start_threshold=-45dB,areverse")


def pcm(path, sr=SR, af=None):
    cmd = ["ffmpeg", "-v", "error", "-i", path] + (["-af", af] if af else []) + ["-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32).copy()


def write_wav(x, path, sr=SR):
    import soundfile as sf
    sf.write(path, x, sr, subtype="PCM_24")


_ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}


def norm(t):
    """Words to compare, with numbers in one form: transcription writes "75%" one time and "seventy-five percent" the
    next, and a correct fix must not fail on that."""
    ws_ = [w for w in re.sub(r"[^a-z0-9' ]", " ", t.lower().replace("%", " percent")).split() if w]
    out, i = [], 0
    while i < len(ws_):
        w = ws_[i]
        if w in ("percent", "per", "cent", "point"): i += 1; continue
        if w in _TENS:
            v = _TENS[w]
            if i + 1 < len(ws_) and ws_[i + 1] in _ONES and 0 < _ONES[ws_[i + 1]] < 10: v += _ONES[ws_[i + 1]]; i += 1
            out.append(str(v))
        elif w in _ONES: out.append(str(_ONES[w]))
        elif w == "hundred" and out and out[-1].isdigit(): out[-1] = str(int(out[-1]) * 100)
        else: out.append(w)
        i += 1
    return out


def reference(d, cfg, key, x, sr, words, t0, t1, secs, tmp):
    """The line itself (span + ~4 s: the pitch and pace of this sentence) plus clean, continuous speech from the same
    recording up to `secs` in total. 8 s of reference sounded unlike the speaker where 15+ s had sounded right."""
    dur = len(x) / sr; r0, r1 = max(0.0, t0 - 4.0), min(dur, t1 + 4.0)
    p0 = os.path.join(tmp, "ref_line.wav"); write_wav(x[int(r0 * sr):int(r1 * sr)], p0)
    refs = [(p0, " ".join(w["w"] for w in words if w["s"] >= r0 and w["e"] <= r1), f"{key} the line", r1 - r0)]
    need = secs - (r1 - r0)
    W = load(d, "words.json") or {}
    keys = [c["key"] for c in cfg["clips"]]; i = keys.index(key)
    for k in [key] + [keys[j] for j in (i - 1, i + 1, i - 2, i + 2) if 0 <= j < len(keys)]:
        if need < 3 or len(refs) >= 3: break                 # providers take at most 3 reference clips
        ws_ = W.get(k, []); length = min(need, 20.0); best = None
        for j, w in enumerate(ws_):
            s, e = w["s"], w["s"] + length
            if k == key and s < r1 + 0.5 and e > r0 - 0.5: continue          # not the line itself again
            inside = [v for v in ws_[j:] if v["e"] <= e]
            if not inside or inside[-1]["e"] - s < length * 0.8: continue
            talk = sum(v["e"] - v["s"] for v in inside)                     # most speech, fewest pauses
            if best is None or talk > best[0]: best = (talk, s, inside[-1]["e"], inside)
        if best:
            _, s, e, inside = best
            c = next(c for c in cfg["clips"] if c["key"] == k)
            xx, _ = read_wav(wav(c["path"], os.path.join(d, "audio", f"{k}_48k.wav")))
            pth = os.path.join(tmp, f"ref_{k}.wav"); write_wav(xx[int(max(0.0, s - 0.1) * sr):int((e + 0.15) * sr)], pth)
            refs.append((pth, " ".join(v["w"] for v in inside), f"{k} clean speech", e - s + 0.25)); need -= e - s
    if len(refs) > 1:            # most voice models take ONE reference clip (Fish: "no endpoints supporting multiple"):
        import soundfile as sf   # join them with 0.4 s of silence, transcripts in the same order
        gap = np.zeros(int(0.4 * sr), np.float32)
        joined = np.concatenate([np.concatenate([sf.read(p_)[0].astype(np.float32), gap]) for p_, *_ in refs])
        pj = os.path.join(tmp, "ref_joined.wav"); write_wav(joined, pj)
        refs = [(pj, " ".join(t for _, t, *_ in refs), " + ".join(f"{lab} {du:.1f} s" for _, _, lab, du in refs), len(joined) / sr)]
    return refs


def speech_rms(x):
    fr = x[: len(x) // 480 * 480].reshape(-1, 480); r = np.sqrt((fr ** 2).mean(1)) + 1e-9
    db = 20 * np.log10(r); return float(np.sqrt(np.mean(r[db > np.percentile(db, 30)] ** 2)))


def main():
    a = sys.argv
    if len(a) < 6 or a[1] in ("-h", "--help"): sys.exit(__doc__)
    d, cfg = ws(); key, s0, s1, new_text = a[2], float(a[3]), float(a[4]), a[5]
    model = a[a.index("--model") + 1] if "--model" in a else openrouter.settings(cfg)["voice"]
    tries = int(a[a.index("--tries") + 1]) if "--tries" in a else 3
    ref_secs = float(a[a.index("--ref-secs") + 1]) if "--ref-secs" in a else 25.0
    c = next((c for c in cfg["clips"] if c["key"] == key), None)
    if c is None: sys.exit(f"no clip {key}")
    src = c["path"]; tmp = tempfile.mkdtemp(prefix="fixword_")
    x, sr = read_wav(wav(src, os.path.join(d, "audio", f"{key}_48k.wav")))
    db = envelope(x, sr)
    snap = lambda t: (lambda lo, hi: (lo + int(np.argmin(db[lo:hi]))) * HOP)(max(0, int((t - 0.3) / HOP)), min(len(db), int((t + 0.3) / HOP)))
    t0, t1 = snap(s0), snap(s1)
    if t1 - t0 < 0.3: sys.exit(f"span {t0:.2f}-{t1:.2f} too short after snapping to pauses: widen it")
    words = (load(d, "words.json") or {}).get(key, [])
    old = " ".join(w["w"] for w in words if w["s"] >= t0 - 0.05 and w["e"] <= t1 + 0.05)
    print(f"{key} {t0:.2f}-{t1:.2f} ({t1 - t0:.2f} s): \"{old}\" -> \"{new_text}\"   voice {model}")
    refs = reference(d, cfg, key, x, sr, words, t0, t1, ref_secs, tmp)
    print("  reference: " + "; ".join(f"{lab} {dur:.1f} s" for _, _, lab, dur in refs) + f" = {sum(r[3] for r in refs):.1f} s")
    refs = [(path, txt) for path, txt, _, _ in refs]
    span = x[int(t0 * sr):int(t1 * sr)]; L = len(span)
    # room tone: the quietest half second of the clip, looped under the new words and into any gap they leave
    w_ = int(0.5 * sr); k = int(np.argmin([np.mean(x[i:i + w_] ** 2) for i in range(0, len(x) - w_, w_ // 2)])) * (w_ // 2)
    room = np.resize(x[k:k + w_], L)
    lead = max(0.0, min((w["s"] for w in words if w["s"] >= t0 - 0.05), default=t0) - t0)   # silence before the first word
    # scored on the span alone: with the unchanged words around it counted too, a 3-word fix that came out wrong still
    # matched ~0.9. Every removed word must be gone and every added word heard.
    want = norm(new_text); removed = set(norm(old)) - set(want); added = set(want) - set(norm(old))
    asr = asr_model(cfg, d)

    def build(g):
        """Splice one generated take: natural speed (sped up at most 8% if it runs long), never slowed down; the gap
        a shorter take leaves is room tone. Returns (audio, fit, match, note)."""
        y = pcm(g, af=TRIM); fit = len(y) / L
        if fit > 1.08 or (len(y) + int(lead * sr)) / L > 1.08:
            return None, fit, 0.0, f"{len(y) / sr:.2f} s of speech for a {L / sr:.2f} s span: too long, widen the span or shorten the line"
        if len(y) + int(lead * sr) > L: y = pcm(g, af=TRIM + f",atempo={(len(y) + lead * sr) / L:.4f}")
        y = y * (speech_rms(span) / max(speech_rms(y), 1e-6))
        body = room.copy(); o = min(int(lead * sr), L - len(y)); body[o:o + len(y)] += y[: L - o]
        out = x.copy(); f = int(0.04 * sr); ramp = np.linspace(0, 1, f, dtype=np.float32)
        body[:f] = body[:f] * ramp + span[:f] * (1 - ramp); body[-f:] = body[-f:] * ramp[::-1] + span[-f:] * (1 - ramp[::-1])
        out[int(t0 * sr):int(t0 * sr) + L] = body
        chk = os.path.join(tmp, "chk.wav"); a0 = max(0.0, t0 - 2.5); write_wav(out[int(a0 * sr):int((t1 + 2.5) * sr)], chk)
        segs, _ = asr.transcribe(chk, language=cfg.get("language", "en"), word_timestamps=True, beam_size=5)
        hw = [(w.word, w.start + a0, w.end + a0) for s_ in segs for w in (s_.words or [])]
        heard = norm(" ".join(w for w, s_, e_ in hw if s_ >= t0 - 0.15 and e_ <= t1 + 0.15))
        sim = difflib.SequenceMatcher(a=want, b=heard, autojunk=False).ratio()
        left = sorted(w for w in removed if w in heard); miss = sorted(w for w in added if w not in heard)
        if left or miss: sim = min(sim, 0.5)
        return out, fit, sim, (f"heard \"{' '.join(heard)}\"" + (f", still says {', '.join(left)}" if left else "")
                               + (f", missing {', '.join(miss)}" if miss else ""))

    os.makedirs(os.path.join(d, "check"), exist_ok=True); stem = os.path.join(d, "check", f"fix_{key}_{t0:.1f}")
    if "--use" in a:                                  # apply a candidate the user picked by ear
        gens = [os.path.abspath(a[a.index("--use") + 1])]
    else:
        n = int(a[a.index("--candidates") + 1]) if "--candidates" in a else tries
        gens = []
        for i in range(1, n + 1):
            g = f"{stem}_gen{i}.mp3"; open(g, "wb").write(openrouter.speech(d, model, new_text, refs, fmt="mp3", note=f"{key} {t0:.2f}-{t1:.2f}"))
            gens.append(g)
            if "--candidates" not in a:
                out, fit, sim, note = build(g); print(f"  try {i}: x{fit:.2f} of the span, match {sim:.2f}, {note}")
                if out is not None and sim >= 0.9: gens = [g]; break
    best = None
    for i, g in enumerate(gens, 1):
        out, fit, sim, note = build(g)
        if "--candidates" in a:
            if out is not None:
                lst = f"{stem}_cand{i}.mp3"; write_wav(out[int(max(0.0, t0 - 3) * sr):int((t1 + 3) * sr)], lst + ".wav")
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", lst + ".wav", lst], check=True); os.remove(lst + ".wav")
            print(f"  candidate {i}: x{fit:.2f} of the span, match {sim:.2f}, {note}" + (f"\n     listen: {lst}\n     apply:  --use {g}" if out is not None else ""))
        elif out is not None and (best is None or sim > best[0]): best = (sim, out, fit)
    if "--candidates" in a:
        sys.exit("  Nothing applied. Listen to each candidate, then run again with --use <its gen file>.")
    if best is None or best[0] < 0.9:
        if best is not None: write_wav(best[1][int(max(0.0, t0 - 3) * sr):int((t1 + 3) * sr)], stem + "_best.wav")
        sys.exit(f"  NOT APPLIED: no take read back as the corrected words. config.json is unchanged. "
                 f"Try --candidates 3 and pick by ear, or re-record the line.")
    sim, out, ratio = best
    nw = os.path.join(tmp, "new.wav"); write_wav(out, nw)
    orig = c.get("fixed_from") or src             # same file name as the original, so assemble.py --screen still pairs it
    dst = os.path.join(d, "clips_fixed", os.path.basename(orig)); os.makedirs(os.path.dirname(dst), exist_ok=True)
    ext = os.path.splitext(dst)[1]; tmpdst = dst + ".tmp" + ext
    acodec = ["-c:a", "flac"] if ext.lower() == ".mkv" else ["-c:a", "aac", "-b:a", "320k"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-i", nw, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", *acodec, tmpdst], check=True)
    os.replace(tmpdst, dst)
    c["fixed_from"] = orig; c["path"] = dst
    cfg.setdefault("voice_fixes", []).append({"clip": key, "span": [round(t0, 3), round(t1, 3)], "from": old, "to": new_text,
                                              "model": model, "match": round(sim, 2), "tempo": round(ratio, 3)})
    save(cfg, d, "config.json")
    wav(dst, os.path.join(d, "audio", f"{key}_48k.wav")); a16 = wav(dst, os.path.join(d, "audio", f"{key}_16k.wav"), sr=16000)
    W = load(d, "words.json") or {}
    segs, _ = asr.transcribe(a16, language=cfg.get("language", "en"), word_timestamps=True, beam_size=5)
    W[key] = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3), "p": round(w.probability, 3)} for s_ in segs for w in (s_.words or [])]
    save(W, d, "words.json")
    print(f"-> {dst}  (config.json now points {key} here; words refreshed). Re-run cutpoints.py and assemble.py.")
    print(f"   listen to {key} around {t0:.1f} s before shipping it, and keep an export with the original voice.")


if __name__ == "__main__":
    main()
