"""OpenRouter for the full pipeline: one API key for transcription, video review, thumbnail images and voice.

The basic pipeline never calls this. Full mode is opt-in: run `enable` only when the user asks for the full
pipeline, because it sends the unpublished footage and a voice sample to outside providers.

Usage: python openrouter.py <ws> enable [--transcribe <model>] [--review <model>] [--voice <model>] [--images a,b,c]
       python openrouter.py <ws> disable        # back to basic: transcription on local Whisper again
       python openrouter.py <ws> status         # mode, the model for each step, key found or not
       python openrouter.py <ws> costs          # what every call cost, by step, and the total
       python openrouter.py models <kind>       # image | video | speech | transcription: the current catalog

The key: OPENROUTER_API_KEY in the environment, or a line OPENROUTER_API_KEY=... in scripts/.env (git-ignored).
Every call appends {step, model, cost} to <ws>/costs.jsonl; text to speech returns audio only, so its cost is read
back from the generation endpoint.
"""
import base64, json, os, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://openrouter.ai/api/v1"
DEFAULTS = {
    "transcribe": "elevenlabs/scribe-v2",          # word timestamps; ends words late, the safe side for cutting
    "review": "google/gemini-4-argon",             # whole-video notes; gemini-3.8-flash is ~3x cheaper and weaker
    "voice": "fish-audio/s2.1-pro",                # clones from a reference clip (input_references)
    "images": ["google/gemini-3-pro-image", "openai/gpt-image-2", "bytedance-seed/seedream-5-0-pro",
               "black-forest-labs/flux-3-image"],
}


def api_key():
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k and os.path.exists(os.path.join(HERE, ".env")):
        for line in open(os.path.join(HERE, ".env"), encoding="utf-8"):
            if line.strip().startswith("OPENROUTER_API_KEY="): k = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not k: sys.exit("OPENROUTER_API_KEY not set (environment, or scripts/.env). Get one at https://openrouter.ai/settings/keys")
    return k


def settings(cfg):
    return {**DEFAULTS, **(cfg.get("openrouter") or {})}


def full(cfg):
    """True only when the user turned the full pipeline on for this workspace (openrouter.py <ws> enable)."""
    return bool((cfg.get("openrouter") or {}).get("full"))


def _req(method, path, body=None, timeout=300, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json",
                                        "X-Title": "edit-video skill"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                b = resp.read()
                return (b, dict(resp.headers)) if raw else json.loads(b)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:600]
            if e.code in (429, 502, 503) and attempt < 2: time.sleep(5 * (attempt + 1)); continue
            raise RuntimeError(f"OpenRouter {path} HTTP {e.code}: {msg}")
        except urllib.error.URLError as e:
            if attempt < 2: time.sleep(5); continue
            raise RuntimeError(f"OpenRouter {path}: {e}")


def log_cost(d, step, model, cost, note="", gen=None):
    if d is None: return
    with open(os.path.join(d, "costs.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": round(time.time(), 1), "step": step, "model": model, "cost": cost, "note": note, "gen": gen}) + "\n")


def lookup_cost(gen):
    """Cost of a finished call from the generation endpoint (text to speech reports it only there). None if not ready."""
    try: return (_req("GET", "/generation?" + urllib.parse.urlencode({"id": gen}), timeout=30).get("data") or {}).get("total_cost")
    except RuntimeError: return None


def call(d, step, path, body, timeout=300):
    """POST a JSON body, log usage.cost under `step`, return the parsed response."""
    j = _req("POST", path, body, timeout)
    log_cost(d, step, body.get("model"), (j.get("usage") or {}).get("cost"), "")
    return j


def speech(d, model, text, refs, fmt="mp3", note=""):
    """Text to speech. refs = [(audio_path, transcript or None)] to clone a voice. Returns audio bytes."""
    parts = []
    for path, txt in refs:
        mime = {"wav": "audio/wav", "mp3": "audio/mpeg", "flac": "audio/flac"}.get(path.rsplit(".", 1)[-1].lower(), "audio/mpeg")
        parts.append({"type": "input_audio", "input_audio": {"data": f"data:{mime};base64," + base64.b64encode(open(path, "rb").read()).decode()}})
        if txt: parts.append({"type": "text", "text": txt})
    body = {"model": model, "input": text, "response_format": fmt}
    if parts: body["input_references"] = parts
    audio, hdr = _req("POST", "/audio/speech", body, raw=True)
    gid = next((v for k, v in hdr.items() if k.lower() == "x-generation-id"), None)
    cost = None
    for _ in range(4):                              # the generation record can lag the response; `costs` backfills later
        if not gid: break
        cost = lookup_cost(gid)
        if cost is not None: break
        time.sleep(3)
    log_cost(d, "voice", model, cost, note, gen=gid)
    return audio


def _mp3(src_or_array, sr=16000):
    """A 16 kHz mono mp3 of a file or a float32 array: small enough for the API (25 MB cap), lossless enough for words."""
    tmp = tempfile.mkdtemp(prefix="or_asr_"); out = os.path.join(tmp, "a.mp3")
    if isinstance(src_or_array, str):
        src = src_or_array
    else:
        import soundfile as sf
        src = os.path.join(tmp, "a.wav"); sf.write(src, src_or_array, sr)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", out], check=True)
    return out


class _W:
    def __init__(self, w, s, e, p): self.word, self.start, self.end, self.probability = w, s, e, p


class _Seg:
    def __init__(self, words):
        self.words = words; self.text = " ".join(w.word for w in words)
        self.start = words[0].start if words else 0.0; self.end = words[-1].end if words else 0.0


class Transcriber:
    """Drop-in for a faster-whisper model: transcribe(audio, **ignored) -> ([segment], info), each word with
    word/start/end/probability. Audio over CHUNK s goes up in pieces split at the quietest moment near each boundary
    (the providers time out on long uploads), with every word shifted back to the whole file's clock."""
    CHUNK = 480.0
    remote = True        # cutpoints.py: one call per probe point, run in parallel (beam_size means nothing here)

    def __init__(self, d, cfg):
        self.d, self.model, self.lang = d, settings(cfg)["transcribe"], cfg.get("language", "en")

    def _one(self, mp3, offset):
        j = call(self.d, "transcribe", "/audio/transcriptions", {
            "model": self.model, "input_audio": {"data": base64.b64encode(open(mp3, "rb").read()).decode(), "format": "mp3"},
            "response_format": "verbose_json", "timestamp_granularities": ["word"]}, timeout=300)
        out = []
        for w in j.get("words") or []:
            t = (w.get("word") or w.get("text") or "").strip()
            if not t or t[0] in "([" or w.get("type") in ("spacing", "audio_event"): continue   # "(laughs)" is not a word
            out.append(_W(t, round(w["start"] + offset, 3), round(w["end"] + offset, 3), float(w.get("confidence") or 1.0)))
        return out

    def transcribe(self, audio, **_):
        mp3 = _mp3(audio)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp3],
                                   capture_output=True, text=True).stdout or 0)
        if dur <= self.CHUNK * 1.25:
            return [_Seg(self._one(mp3, 0.0))], None
        import numpy as np                          # split at quiet points so no word is cut in half
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", mp3, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], capture_output=True).stdout
        x = np.frombuffer(raw, np.int16).astype(np.float32); hop = 160
        e = np.sqrt((x[: len(x) // hop * hop].reshape(-1, hop) ** 2).mean(1))
        cuts, t = [0.0], self.CHUNK
        while t < dur - 30:
            lo, hi = int((t - 15) * 100), int((t + 15) * 100)
            cuts.append((lo + int(np.argmin(e[lo:hi]))) / 100); t = cuts[-1] + self.CHUNK
        cuts.append(dur); words = []
        for a, b in zip(cuts, cuts[1:]):
            part = mp3[:-4] + f"_{int(a)}.mp3"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.2f}", "-t", f"{b - a:.2f}", "-i", mp3, "-c", "copy", part], check=True)
            words += self._one(part, a)
        return [_Seg(words)], None


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"): sys.exit(__doc__)
    if a[0] == "models":
        kind = a[1] if len(a) > 1 else "image"
        if kind == "image":
            for m in _req("GET", "/images/models").get("data", []):
                print(f"  {m['id']:45s} input {','.join(m.get('architecture', {}).get('input_modalities', []))}")
            return
        q = {"video": "input_modalities=video", "speech": "output_modalities=speech", "transcription": "output_modalities=transcription"}[kind]
        for m in _req("GET", "/models?" + q).get("data", []): print("  " + m["id"])
        return
    sys.path.insert(0, HERE)
    from common import ws, save
    d, cfg = ws(a[:1] and [sys.argv[0], a[0]]); cmd = a[1] if len(a) > 1 else "status"
    if cmd in ("enable", "disable"):
        o = cfg.get("openrouter") or {}
        o["full"] = cmd == "enable"
        for step in ("transcribe", "review", "voice"):
            if f"--{step}" in a: o[step] = a[a.index(f"--{step}") + 1]
        if "--images" in a: o["images"] = a[a.index("--images") + 1].split(",")
        cfg["openrouter"] = o; save(cfg, d, "config.json")
        if o["full"]: api_key()
        print(f"{'FULL' if o['full'] else 'BASIC'} pipeline for {d}")
        cmd = "status"
    if cmd == "status":
        s = settings(cfg)
        print(f"mode {'full (OpenRouter)' if full(cfg) else 'basic (local, nothing leaves the machine)'}")
        for step in ("transcribe", "review", "voice"): print(f"  {step:10s} {s[step]}")
        print(f"  {'images':10s} {', '.join(s['images'])}")
        k = os.environ.get("OPENROUTER_API_KEY") or os.path.exists(os.path.join(HERE, ".env"))
        print(f"  key       {'found' if k else 'not set'}")
    elif cmd == "costs":
        f = os.path.join(d, "costs.jsonl")
        rows = [json.loads(l) for l in open(f, encoding="utf-8")] if os.path.exists(f) else []
        late = [r for r in rows if r.get("cost") is None and r.get("gen")]
        for r in late: r["cost"] = lookup_cost(r["gen"])            # backfill costs that were not ready at call time
        if late:
            with open(f, "w", encoding="utf-8") as fh: fh.write("".join(json.dumps(r) + "\n" for r in rows))
        by = {}
        for r in rows:
            k = (r["step"], r["model"]); n, c = by.get(k, (0, 0.0)); by[k] = (n + 1, c + (r["cost"] or 0))
        for (step, model), (n, c) in sorted(by.items()): print(f"  {step:11s} {model:40s} {n:4d} calls  ${c:.4f}")
        print(f"  {'total':11s} {'':40s} {len(rows):4d} calls  ${sum((r['cost'] or 0) for r in rows):.4f}")
        if any(r["cost"] is None for r in rows): print("  (some calls reported no cost; they are counted as 0)")


if __name__ == "__main__":
    main()
