"""Re-transcribe one stretch of audio and print every word with its time: the second opinion on a suspected repeat,
a word-diff line, or a clipped word.

Usage: uv run --project $S python retranscribe.py <file | ws segment-or-clip-key> <start> <end> [--no-prompt] [--pad 1]
                                                   [--model large-v3]
  <file>          any audio or video file (a raw clip, the cut, an export); times are seconds in that file
  <ws> <key>      a workspace and a clip key (c03) or segment key (c03_s01): times are seconds in that clip's source.
                  A workspace and "cut:<tag>" (cut:v1) reads cut/clean_<tag>.mp4, times on the output timeline.
--no-prompt  transcribe without the capitalised prompt transcribe.py uses. Use it to confirm a repeat: with a prompt,
             Whisper sometimes invents a doubled word, and a doubled word heard twice without one is real.
--pad S      seconds of silence before the window (default 1): a word on the window's first frame is otherwise often
             misheard (validate_cut.py pads its re-transcription the same way).
Same model and settings as transcribe.py (faster-whisper large-v3, word timestamps, CUDA when usable). Times printed are
in the file's own timeline. Whisper's times are a second check, never cut points: place cuts with align.py.
"""
import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import run, whisper_model

PROMPT = "Hello, and welcome. Today I'm showing you something new. Let's get into it."   # transcribe.py's prompt

def arg(name, default):
    a = sys.argv
    return type(default)(a[a.index(name) + 1]) if name in a else default

def resolve(pos):
    """(source file, start, end, label) from the positional arguments."""
    if len(pos) >= 4 and os.path.isdir(pos[0]):
        import json
        d, key, t0, t1 = pos[0], pos[1], float(pos[2]), float(pos[3])
        if key.startswith("cut:"):
            f = os.path.join(d, "cut", f"clean_{key[4:]}.mp4")
            if not os.path.exists(f): sys.exit(f"no cut {f}")
            return f, t0, t1, key
        cfg = json.load(open(os.path.join(d, "config.json"), encoding="utf-8"))
        clip = key.split("_")[0]
        c = next((c for c in cfg["clips"] if c["key"] == clip), None)
        if c is None: sys.exit(f"no clip {clip} in {d}/config.json (keys: {', '.join(c['key'] for c in cfg['clips'])})")
        return c["path"], t0, t1, clip
    if len(pos) >= 3 and os.path.isfile(pos[0]): return pos[0], float(pos[1]), float(pos[2]), os.path.basename(pos[0])
    sys.exit(__doc__)

def main():
    flags = {"--pad", "--model"}
    pos = [x for i, x in enumerate(sys.argv[1:], 1) if not x.startswith("--") and sys.argv[i - 1] not in flags]
    src, t0, t1, label = resolve(pos)
    if t1 <= t0: sys.exit("end must be after start")
    pad = arg("--pad", 1.0)
    tmp = os.path.join(tempfile.gettempdir(), f"_retranscribe_{os.getpid()}.wav")
    try:
        # pad with silence first, then the window, 16 kHz mono: what transcribe.py feeds the model
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
             "-af", f"adelay={int(pad * 1000)}:all=1", tmp])
        m = whisper_model(arg("--model", "large-v3"))
        segs, _ = m.transcribe(tmp, language="en", word_timestamps=True, vad_filter=False, beam_size=5,
                               condition_on_previous_text=False, initial_prompt=None if "--no-prompt" in sys.argv else PROMPT)
        words = [(w.word.strip(), w.start - pad + t0, w.end - pad + t0, w.probability) for s in segs for w in (s.words or [])]
    finally:
        if os.path.exists(tmp): os.remove(tmp)
    print(f"{label} {t0:.2f}-{t1:.2f}s  ({'no prompt' if '--no-prompt' in sys.argv else 'prompt'}, {pad:.1f} s pad)")
    print("  " + " ".join(w for w, *_ in words))
    for w, s, e, p_ in words: print(f"  {s:8.3f} {e:8.3f}  {p_:.2f}  {w}")
    if not words: print("  (no words heard)")

if __name__ == "__main__":
    main()
