"""Word-level transcription of every clip: faster-whisper large-v3 locally (basic), or the OpenRouter transcription
model when the full pipeline is on (openrouter.py <ws> enable).

Usage: uv run --project $S python transcribe.py <ws> [--model large-v3]
Writes <ws>/audio/<key>_48k.wav, <key>_16k.wav, <ws>/words.json {key: [{w, s, e, p}]} (seconds in the clip) and
<ws>/transcript.txt, and prints the full transcript of every clip.
Skips clips already transcribed unless --force.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import asr_model, load, p, save, wav, ws

# A punctuated, capitalised prompt; without it Whisper sometimes returns a whole take lower-case with no punctuation
PROMPT = "Hello, and welcome. Today I'm showing you something new. Let's get into it."

def main():
    d, cfg = ws()
    model_name = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "large-v3"
    words = {} if "--force" in sys.argv else (load(d, "words.json") or {})
    m = asr_model(cfg, d, model_name)
    print("transcribing with", getattr(m, "model", f"local faster-whisper {model_name}"))
    for c in cfg["clips"]:
        k = c["key"]
        wav(c["path"], p(d, "audio", f"{k}_48k.wav"))
        a16 = wav(c["path"], p(d, "audio", f"{k}_16k.wav"), sr=16000)
        if k in words: continue
        segs, info = m.transcribe(a16, language=cfg.get("language", "en"), word_timestamps=True, vad_filter=False, initial_prompt=PROMPT,
                                  beam_size=5, condition_on_previous_text=False)
        words[k] = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3), "p": round(w.probability, 3)}
                    for s in segs for w in (s.words or [])]
        save(words, d, "words.json")
    save(words, d, "words.json")
    # The whole transcript, every clip (also on a re-run that skipped them all): step 1 reads it end to end
    lines = []
    for c in cfg["clips"]:
        ws_ = words.get(c["key"], [])
        lines.append(f"{c['key']} ({c['dur']:.1f}s, {len(ws_)} words): " + " ".join(w["w"] for w in ws_))
    with open(p(d, "transcript.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(lines) + "\n")
    print("\n\n".join(lines))
    print(f"\n-> {p(d, 'transcript.txt')}")

if __name__ == "__main__":
    main()
