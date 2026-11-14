"""The live screen recording in the stacked layout's graphics band.

For a vertical Short in the stacked layout (references/shorts-from-long.md), where engine.Track.screen() is not
available: the Short's full-resolution screen track (cut/screen_<tag>.mp4 from assemble.py --screen-native, same
timeline as the face cut) plays in a rounded window in the graphics band, and a camera eases onto the region being
talked about, on the spoken word. Show it with tk.band(t, sid) like any other band scene; one scene can be shown again
later (its video keeps running on the shared timeline). Pick the rects off a gridded frame of the screen track.
Built for the Fable Shorts (11/13) and promoted into the kit.

moves: [(t, (x, y, w, h), dur)] in screen pixels (1920x1080). The first move is the opening framing (set at 0);
dur 0 snaps (use it on a hard screen change). Scale is capped at MAX_ZOOM so text never goes soft.
"""
import os

SW, SH = 1920, 1080
MAX_ZOOM = 1.4
BOX = (40, 70, 1000, 900)      # x, y, w, h on the 1080x1920 canvas: above the captions (y 1004..1134) and the seam (1160)


def _state(r, vw, vh):
    rx, ry, rw, rh = r
    sc = min(vw / rw, vh / rh, MAX_ZOOM)
    x = -rx * sc + (vw - rw * sc) / 2; y = -ry * sc + (vh - rh * sc) / 2
    # never show past the recording's edge: clamp inside the frame (centre it if the frame is smaller than the window)
    x = (vw - SW * sc) / 2 if SW * sc <= vw else min(0, max(vw - SW * sc, x))
    y = (vh - SH * sc) / 2 if SH * sc <= vh else min(0, max(vh - SH * sc, y))
    return round(x, 2), round(y, 2), round(sc, 5)


def screen(tk, sid, src, moves, box=BOX, max_zoom=None):
    """max_zoom: dense product UI (~15 px body text in the 1920 recording) is unreadable at phone size under the
    default 1.4x; 1.8-2.0x on a tight rect around the one line being talked about reads (MongoDB Short 2, 11/14)."""
    global MAX_ZOOM
    old = MAX_ZOOM; MAX_ZOOM = max_zoom or MAX_ZOOM
    try:
        return _screen(tk, sid, src, moves, box)
    finally:
        MAX_ZOOM = old


def _screen(tk, sid, src, moves, box):
    x, y, w, h = box
    name = tk.asset(src)
    cam = f"#{sid}cam"
    for k, (t, r, dur) in enumerate(moves):
        X, Y, S = _state(r, w, h)
        if k == 0: tk.add(f"tl.set('{cam}',{{x:{X},y:{Y},scale:{S}}},0);")
        elif dur <= 0: tk.add(f"tl.set('{cam}',{{x:{X},y:{Y},scale:{S}}},{t:.3f});")
        else: tk.add(f"tl.to('{cam}',{{x:{X},y:{Y},scale:{S},duration:{dur},ease:'power2.inOut'}},{t:.3f});")
    body = (f'<div id="{sid}win" style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;border-radius:22px;overflow:hidden;'
            f'background:#05070c;border:2px solid rgba(96,165,250,.38);box-shadow:0 24px 70px rgba(0,0,0,.55),0 0 60px rgba(59,130,246,.18)">'
            f'<div id="{sid}cam" data-layout-allow-overflow style="position:absolute;left:0;top:0;width:{SW}px;height:{SH}px;transform-origin:0 0">'
            f'<video id="{sid}v" data-start="0" data-duration="{tk.D}" data-track-index="3" src="{name}" muted playsinline '
            f'style="position:absolute;left:0;top:0;width:{SW}px;height:{SH}px;display:block"></video></div></div>')
    return f'<div class="scene" id="{sid}">{body}</div>'


def src_for(d, tag="v1"):
    """The Short's screen track: screen_<tag>.mp4 (assemble.py --screen-native), else an older screen_full_<tag>.mp4."""
    a = os.path.join(d, "cut", f"screen_{tag}.mp4"); b = os.path.join(d, "cut", f"screen_full_{tag}.mp4")
    return b if os.path.exists(b) and not os.path.exists(a) else a
