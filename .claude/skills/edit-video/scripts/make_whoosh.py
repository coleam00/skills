"""The default transition whoosh: soft pink-noise air, band-pass opening toward the peak, 0.33 s.

Usage: python make_whoosh.py <ws>   -> <ws>/sfx/whoosh.wav (peak at PEAK s)
Normally you do not need this: the exact file ships at assets/sfx/whoosh.wav and transitions.py copies it.
This script reproduces it bit-for-bit (seeded) so the recipe is not lost, and is the place to tune a new one.
Mix level: -6.4 dB on this file (transitions.py default), about -30 dB in the pause.

How it was found (references/transitions.md): white-noise sweeps read as "whish"; brown noise as too deep;
0.9-1.1 s as exaggerated; ~850-930 Hz as too high. Approved: ~560 Hz spectral centroid, 0.33 s, gentle swell.
"""
import os, sys
import numpy as np, soundfile as sf

SR, PEAK = 48000, 0.21
RECIPE = dict(seed=100 + ord("Q"), pad=0.2, dur=0.33, peak=PEAK, rise=2.4, decay=0.05, open_w=0.065,
              lp=(300, 880), hp=(140, 220), width=0.45)

def pink(n, rng):
    X = np.fft.rfft(rng.standard_normal(n)); f = np.fft.rfftfreq(n, 1 / SR); X[1:] /= np.sqrt(f[1:]); X[0] = 0
    x = np.fft.irfft(X, n); return x / np.abs(x).max()

def bandpass_sweep(x, lo, hi, hop=128, win=512):
    out = np.zeros(len(x)); norm = np.zeros(len(x)); w = np.hanning(win); fr = np.fft.rfftfreq(win, 1 / SR)
    for k in range(0, len(x) - win, hop):
        i = min(k + win // 2, len(x) - 1)
        mask = 1 / (1 + (fr / hi[i]) ** 4) * (1 - 1 / (1 + (fr / lo[i]) ** 4))
        out[k:k + win] += np.fft.irfft(np.fft.rfft(x[k:k + win] * w) * mask, win) * w; norm[k:k + win] += w * w
    return out / np.maximum(norm, 1e-6)

def stereo(m, t, peak, width):
    pan = np.clip((t - (peak - width / 2)) / width, 0, 1)
    return np.stack([m * np.cos(pan * np.pi / 2), m * np.sin(pan * np.pi / 2)], 1) * 1.3

def fade(x, ms=10):
    n = int(SR * ms / 1000); x[:n] *= np.linspace(0, 1, n)[:, None]; x[-n:] *= np.linspace(1, 0, n)[:, None]; return x

def whoosh(seed, dur, peak, lp, hp, open_w, rise, decay, width, pad):
    rng = np.random.default_rng(seed)
    n = int(SR * dur); t = np.arange(n) / SR; g = np.exp(-((t - peak) / open_w) ** 2)
    P = int(SR * pad)   # filter padded noise and crop: the STFT edge frames never land inside the sound
    lo = np.concatenate([np.full(P, hp[0]), hp[0] + (hp[1] - hp[0]) * g, np.full(P, hp[0])])
    hi = np.concatenate([np.full(P, lp[0]), lp[0] + (lp[1] - lp[0]) * g, np.full(P, lp[0])])
    x = bandpass_sweep(pink(n + 2 * P, rng), lo, hi)[P:P + n]
    x *= np.where(t < peak, (t / peak) ** rise, np.exp(-(t - peak) / decay))
    s = fade(stereo(x, t, peak, width)); return s * 0.5 / np.abs(s).max()

def main():
    if any(x in ("-h", "--help") for x in sys.argv[1:]) or len(sys.argv) < 2: sys.exit(print(__doc__.strip()))
    d = os.path.abspath(sys.argv[1]); os.makedirs(os.path.join(d, "sfx"), exist_ok=True)
    out = os.path.join(d, "sfx", "whoosh.wav")
    sf.write(out, whoosh(**RECIPE).astype(np.float32), SR)
    print("wrote", out, f"peak at {PEAK}s")

if __name__ == "__main__":
    main()
