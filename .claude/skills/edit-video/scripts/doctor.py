"""Check this machine for everything the edit-video pipeline uses, and say what will and will not work.

Usage: uv run --project $S python $S/doctor.py [--hyperframes]

Checks Python, ffmpeg/ffprobe (and the encoders and filters the scripts call), the Python packages, the face detector,
CUDA for transcription, NVENC, torch for forced alignment, Node/npx for HyperFrames, and fonts. --hyperframes also
asks npx for the HyperFrames version (downloads it on first run). Exits 1 if something the core cut needs is missing.
Run it once on a new machine before the first edit.
"""
import importlib, os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if any(a in ("-h", "--help") for a in sys.argv[1:]): sys.exit(print(__doc__.strip()))

ROWS, MISSING = [], []

def row(state, name, detail, fix=""):
    ROWS.append((state, name, detail, fix))
    if state == "MISSING": MISSING.append(name)

def sh(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return -1, str(e)

def main():
    v = sys.version_info
    row("OK" if (3, 11) <= v[:2] < (3, 13) else "WARN", "python", f"{v.major}.{v.minor}.{v.micro}",
        "" if (3, 11) <= v[:2] < (3, 13) else "the pinned stack is tested on 3.11-3.12; run through `uv run --project $S`")

    for tool in ("ffmpeg", "ffprobe"):
        code, out = sh([tool, "-version"])
        row("OK" if code == 0 else "MISSING", tool, out.splitlines()[0][:70] if code == 0 else "not on PATH",
            "" if code == 0 else "install ffmpeg (a full build: libx264, libfreetype) and put it on PATH")
    if shutil.which("ffmpeg"):
        _, enc = sh(["ffmpeg", "-hide_banner", "-encoders"]); _, flt = sh(["ffmpeg", "-hide_banner", "-filters"])
        for name, hay, why in (("libx264", enc, "every render"), ("aac", enc, "every export")):
            row("OK" if re.search(rf"\b{name}\b", hay) else "MISSING", f"ffmpeg {name}", why)
        for name, why in (("loudnorm", "loudness"), ("ebur128", "level matching"), ("alimiter", "peak limit"), ("xfade", "transitions"),
                          ("drawtext", "lower-third card (needs libfreetype)"), ("deband", "finalize --deband")):
            ok = re.search(rf"\b{name}\b", flt) is not None
            row("OK" if ok else ("MISSING" if name in ("loudnorm", "alimiter") else "WARN"), f"ffmpeg {name}", why)

    pkgs = {"numpy": "core", "scipy": "core", "soundfile": "core", "PIL": "frame sheets", "faster_whisper": "transcription",
            "cv2": "face measurement (punch-ins)"}
    for mod, why in pkgs.items():
        try:
            m = importlib.import_module(mod); ver = getattr(m, "__version__", "")
            row("OK", mod, f"{ver} ({why})")
        except Exception as e:
            row("MISSING", mod, f"{why}: {str(e)[:60]}", "uv sync --project $S")
    try:
        import cv2
        casc = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        major = int(cv2.__version__.split(".")[0])
        row("OK" if os.path.exists(casc) and major < 5 else "MISSING", "opencv face cascade",
            f"opencv {cv2.__version__}", "" if major < 5 else "pin opencv-python-headless<5: 5.x dropped the Haar cascades")
    except Exception:
        pass

    code, smi = sh(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    gpus = [l.strip() for l in smi.splitlines() if l.strip()] if code == 0 else []
    row("OK" if gpus else "INFO", "NVIDIA GPU", "; ".join(gpus) if gpus else "none found: transcription runs on the CPU (several times slower)")
    try:
        from common import cuda_available, find_font, nvenc_ok
        cu = cuda_available()
        if gpus and not cu:
            row("WARN", "CUDA for whisper", "GPU present but CTranslate2 sees no CUDA device",
                "Windows: uv sync --project $S --extra cuda --inexact. Linux: install CUDA 12 + cuDNN 9")
        else:
            row("OK" if cu else "INFO", "CUDA for whisper", "float16 on the GPU" if cu else "CPU int8 (works; use cutpoints.py --no-asr for first passes)")
        nv = nvenc_ok()
        row("OK" if nv else "INFO", "NVENC", "h264_nvenc usable" if nv else "not usable: libx264 is used instead (slower intermediates)")
        for bold, what in ((True, "bold UI font (cards, burned text)"), (False, "mono font (frame sheet labels)")):
            f = find_font(bold=bold)
            row("OK" if f else "WARN", "font", f"{what}: {f or 'none found'}", "" if f else "install DejaVu or set EDIT_VIDEO_FONT=<path to .ttf>")
    except Exception as e:
        row("MISSING", "common.py", str(e)[:80], "run through `uv run --project $S` so numpy is available")

    try:
        import torch, torchaudio
        row("OK", "align extra", f"torch {torch.__version__}, torchaudio {torchaudio.__version__}, "
            f"{'CUDA' if torch.cuda.is_available() else 'CPU'} (forced alignment)")
    except Exception:
        row("INFO", "align extra", "torch not installed: align.py unavailable", "uv sync --project $S --extra align --inexact")
    try:
        import playwright  # noqa: F401
        row("OK", "playwright", "page_render.py available")
    except Exception:
        row("INFO", "playwright", "only for page_render.py (references/advanced/dynamic-screen.md)", "uv run --with playwright ...")

    node = shutil.which("node"); npx = shutil.which("npx") or shutil.which("npx.cmd")
    if node:
        _, nv_ = sh([node, "--version"]); major = int(re.findall(r"\d+", nv_)[0]) if re.findall(r"\d+", nv_) else 0
        row("OK" if major >= 18 else "WARN", "node", nv_.strip(), "" if major >= 18 else "HyperFrames needs a current Node (18+)")
    else:
        row("INFO", "node", "not found: captions burned by HyperFrames and B-roll unavailable (the clean cut and .srt still work)",
            "install Node 18+ (it brings npx)")
    row("OK" if npx else "INFO", "npx", npx or "not found")
    pin = os.environ.get("HYPERFRAMES_VERSION")
    row("OK" if pin else "INFO", "HYPERFRAMES_VERSION", pin or "unset: render.py runs the latest release",
        "" if pin else "set it per project so a new release cannot change a render mid-edit")
    if "--hyperframes" in sys.argv and npx:
        code, out = sh([npx, "-y", f"hyperframes@{pin}" if pin else "hyperframes", "--version"], timeout=300)
        row("OK" if code == 0 else "WARN", "hyperframes", out.strip().splitlines()[-1][:70] if out.strip() else "no output")
    row("OK" if shutil.which("uv") else "WARN", "uv", shutil.which("uv") or "not found", "" if shutil.which("uv") else "https://docs.astral.sh/uv/")
    try:                                       # the full pipeline only; basic needs no key
        import openrouter; openrouter.api_key(); key = True
    except (SystemExit, Exception): key = False
    row("OK" if key else "INFO", "OpenRouter key", "found (full pipeline available)" if key else
        "not set: basic only (everything local); the full pipeline needs it", "OPENROUTER_API_KEY in the environment or scripts/.env")

    w = max(len(r[1]) for r in ROWS)
    for state, name, detail, fix in ROWS:
        print(f"{state:8} {name:{w}}  {detail}" + (f"\n{'':8} {'':{w}}  fix: {fix}" if fix and state != "OK" else ""))
    have = lambda n: n not in MISSING
    print("\nWhat works here:")
    core = all(have(n) for n in ("ffmpeg", "ffprobe", "numpy", "scipy", "soundfile", "faster_whisper"))
    print(f"  clean cut + validate + export : {'yes' if core else 'NO'}")
    print(f"  punch-ins                      : {'yes' if have('cv2') and have('opencv face cascade') else 'no (assemble.py --no-punch)'}")
    print(f"  burned captions + B-roll       : {'yes' if node and npx else 'no (needs Node + npx)'}")
    print(f"  forced alignment (align.py)    : {'yes' if any(r[1] == 'align extra' and r[0] == 'OK' for r in ROWS) else 'no (align extra)'}")
    sys.exit(1 if not core else 0)

if __name__ == "__main__":
    main()
