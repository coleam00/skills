"""Shared helpers: workspace config, paths, audio envelopes, ffmpeg wrappers.

Every script takes the workspace dir (the `_edit/` folder init_workspace.py created) as its first argument.
config.json in the workspace is the single source of truth for format (W, H, fps) and the source clips.
"""
import json, os, site, subprocess, sys

import numpy as np

for _s in (sys.stdout, sys.stderr):   # Windows consoles default to cp1252; HyperFrames prints unicode
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

def _maybe_help():
    """`python <script>.py -h` / `--help` prints that script's docstring and exits, for every script importing this."""
    import __main__
    if any(a in ("-h", "--help") for a in sys.argv[1:]) and getattr(__main__, "__doc__", None):
        print(__main__.__doc__.strip()); sys.exit(0)

_maybe_help()

def pick_gpu():
    """Pin CUDA to the least-busy GPU unless CUDA_VISIBLE_DEVICES is set: the display GPU can sit at 99% (a
    recorder, a game), which once made a transcription ~5x slower while a second GPU idled."""
    if "CUDA_VISIBLE_DEVICES" in os.environ: return
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10).stdout
        rows = [[int(v) for v in l.split(",")] for l in r.strip().splitlines()]
        if len(rows) > 1: os.environ["CUDA_VISIBLE_DEVICES"] = str(min(rows, key=lambda x: (x[1], x[2]))[0])
    except Exception: pass

def cuda_dlls():
    """faster-whisper (ctranslate2) on Windows needs the pip CUDA DLLs on the search path. No-op elsewhere."""
    pick_gpu()
    if os.name != "nt": return
    for sp in site.getsitepackages():
        for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin"):
            d = os.path.join(sp, sub)
            if os.path.isdir(d):
                os.add_dll_directory(d); os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]

def cuda_available():
    """True when CTranslate2 (faster-whisper's backend) can see a CUDA device. False on macOS, on machines without an
    NVIDIA GPU, and when the CUDA runtime libraries are missing."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() == 0: return False
    except Exception:
        return False
    import ctypes                    # a visible device is not enough: the model also loads cuBLAS at transcribe time
    cuda_dlls()
    for lib in (("cublas64_12.dll",) if os.name == "nt" else ("libcublas.so.12", "libcublas.so")):
        try: ctypes.CDLL(lib); return True
        except OSError: pass
    return False

def whisper_model(name="large-v3"):
    """A faster-whisper model on the GPU when one is usable (float16), else on the CPU (int8). The CPU path works
    everywhere but is several times slower: on a long recording pass --no-asr to cutpoints.py for a first look."""
    cuda_dlls()
    from faster_whisper import WhisperModel
    if cuda_available():
        try:
            return WhisperModel(name, device="cuda", compute_type="float16")
        except Exception as e:
            print("CUDA model load failed, using CPU int8:", str(e)[:160])
    return WhisperModel(name, device="cpu", compute_type="int8")

FONT_DIRS = [os.path.join(os.environ.get("WINDIR", os.environ.get("SystemRoot", "")), "Fonts"), "/System/Library/Fonts", "/System/Library/Fonts/Supplemental", "/Library/Fonts",
             os.path.expanduser("~/Library/Fonts"), "/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
             os.path.expanduser("~/.local/share/fonts")]

def find_font(*names, bold=False):
    """First existing font file among `names` (file names or absolute paths), searched across the usual Windows, macOS
    and Linux font folders (recursively on Linux). Falls back to common system fonts; None if nothing is found.
    Set EDIT_VIDEO_FONT to force one file everywhere."""
    forced = os.environ.get("EDIT_VIDEO_FONT")
    if forced and os.path.exists(forced): return forced
    fallback = (["Inter-SemiBold.ttf", "Inter-Bold.ttf", "segoeuib.ttf", "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
                 "LiberationSans-Bold.ttf"] if bold else
                ["consola.ttf", "Menlo.ttc", "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf", "arial.ttf", "Arial.ttf", "DejaVuSans.ttf"])
    for n in [x for x in names if x] + fallback:
        if os.path.isabs(n):
            if os.path.exists(n): return n
            continue
        for d in FONT_DIRS:
            f = os.path.join(d, n)
            if os.path.exists(f): return f
        for d in FONT_DIRS:
            if d.startswith("/usr") or d.startswith(os.path.expanduser("~/.")):
                for root, _, files in os.walk(d) if os.path.isdir(d) else ():
                    if n in files: return os.path.join(root, n)
    return None

def nvenc_ok():
    """True if ffmpeg can actually encode with NVENC here. Listed is not the same as usable (no GPU, an old driver,
    every session busy), so try one tiny encode."""
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1", "-c:v", "h264_nvenc",
                            "-f", "null", "-"], capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except Exception:
        return False

def ws(argv=None):
    """Workspace path from argv[1] (or cwd) + its config."""
    argv = argv if argv is not None else sys.argv
    d = os.path.abspath(argv[1] if len(argv) > 1 else os.getcwd())
    cfg = json.load(open(os.path.join(d, "config.json"), encoding="utf-8"))
    return d, cfg

def p(d, *parts):
    path = os.path.join(d, *parts); os.makedirs(os.path.dirname(path), exist_ok=True); return path

def load(d, *parts, default=None):
    path = os.path.join(d, *parts)
    if not os.path.exists(path): return default
    return json.load(open(path, encoding="utf-8"))

def save(obj, d, *parts):
    # write-then-rename: a crash mid-write (a power cut) once left words.json zero-filled
    out = p(d, *parts); tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(tmp, out)

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode != 0: raise RuntimeError(f"{cmd[0]} failed: {r.stderr[-1500:]}")
    return r

def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json", path])
    j = json.loads(r.stdout); v = next(s for s in j["streams"] if s["codec_type"] == "video")
    num, den = v["r_frame_rate"].split("/")
    return {"w": int(v["width"]), "h": int(v["height"]), "fps": round(int(num) / int(den)), "dur": float(j["format"]["duration"]),
            "audio": any(s["codec_type"] == "audio" for s in j["streams"])}

def wav(src, out, sr=48000):
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(src):
        run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", out])
    return out

HOP = 0.005  # 5 ms analysis hop: fine enough to place a cut inside a 1-frame window at 60 fps

def envelope(x, sr):
    """RMS level in dB, 20 ms window, 5 ms hop."""
    n = int(HOP * sr); win = int(0.02 * sr)
    fr = np.lib.stride_tricks.sliding_window_view(np.pad(x, (win // 2, win // 2)), win)[::n]
    return 20 * np.log10(np.sqrt((fr.astype(np.float64) ** 2).mean(axis=1) + 1e-12) + 1e-9)

def bands(x, sr):
    """Low band (100-900 Hz, voicing) and high band (2.5-8 kHz, fricatives) levels in dB on the 5 ms grid."""
    from scipy.signal import stft
    nper = int(0.03 * sr); hop = int(HOP * sr)
    f, t, Z = stft(x, fs=sr, nperseg=nper, noverlap=nper - hop)
    P = np.abs(Z) ** 2
    lo = 10 * np.log10(P[(f >= 100) & (f <= 900)].sum(axis=0) + 1e-12)
    hi = 10 * np.log10(P[(f >= 2500) & (f <= 8000)].sum(axis=0) + 1e-12)
    return t, lo, hi

def read_wav(path):
    import soundfile as sf
    x, sr = sf.read(path)
    if x.ndim > 1: x = x.mean(axis=1)
    return x, sr

def q(t, fps):
    """Snap a time to the frame grid."""
    return round(t * fps) / fps
