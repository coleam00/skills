"""Layout engine for B-roll on a talking-head cut.

Modes
  FACE  : full-frame speaker, captions in their band
  SPLIT : speaker stays unscaled and unboxed; slides up (vertical) or left (horizontal) to a window derived from the
          measured face, with a soft edge fade into the graphics area. Graphics live in `page_box`.
  FULL  : graphics cover the frame (wipe up); captions stay.
  PIP   : graphics cover the frame like FULL, the speaker stays on as a round bubble bottom right (long-form 16:9).
          Content lives in `pip_box`, which keeps clear of the bubble.
  SCREEN: the cut screen track (assemble.py --screen, same timeline as the face) fills the frame, speaker in the
          bubble: real slides, a demo, a browser.
Stacked layout (config.json "layout": {"mode": "stacked", ...}, written by split_wide.py for a stacked recorder canvas):
  the cut is the camera band at native size, parked in its own band (bottom by default) of the output canvas. SPLIT
  puts the graphic in the band above the seam (the face does not move), FACE leaves that band on the background,
  FULL covers everything. Captions sit on the graphics side of the seam. FACE grows the band to full frame only when
  that needs no more than common.MAX_EXPAND (1.2x); PIP / SCREEN are not available (the face already has its band).
Rules the engine enforces
  - cut sweep: a layout change never shows the next take's face for a split second (see _avoid_cut)
  - every scene element must be positioned inside page_box / full_box / pip_box (scenes.py takes the box)
Times come from words: tk.at("governed autonomy") -> start of that phrase on the output timeline.
"""
import json, math, os, re

import scenes, style
from common import canvas, stacked

TR = 0.6            # layout transition (s): long enough to read as a move, short enough not to lag speech
MIN_DWELL = 1.5     # a scene on screen for less than this is flagged: viewers need 1.5-3 s to take a graphic in
FULL_IN = 0.5       # full-screen wipe duration
FACELESS_MAX = 12.0 # FULL longer than this is flagged: the face has to come back (PIP/SCREEN keep it on screen)
POP_AT = 0.85       # share of the wipe after which the face under it is covered (power3.inOut: 99%) and the bubble can appear
BUB_FADE = 0.22     # bubble fade when it leaves for a layout that hides the face (the face is restored behind a layer)
MIN_FACE = 3.5      # a face beat shorter than this between two graphics is dropped: the graphic crosses to the next one.
                    # Graphic -> face -> graphic inside 2-3 s read as jumping back and forth in review
FOLLOW_EVERY = 1.5  # the panel re-centres on the face this often while it is up (cut/facetrack_<tag>.json)
EMPTY_BAND = 2.0    # stacked layout: the graphics band empty (no beat up) longer than this is flagged; it reads as unfinished
FOLLOW_MIN = 10     # ... but only when the face has moved more than this many cut pixels

class Track:
    def __init__(self, d, cfg, tag="v1"):
        self.d, self.cfg, self.tag = d, cfg, tag
        scenes.TYPE_SCALE = cfg.get("type_scale", 1.0)
        self.G = stacked(cfg)                                     # None unless config.json "layout" is stacked
        self.W, self.H = canvas(cfg); self.vertical = self.H > self.W
        self.valign = "top" if self.vertical and not self.G else "center"   # vertical SPLIT content hangs just under the face;
        # a stacked page band is a whole panel (~850 px tall): top-aligned content left its lower half empty
        self.tl = json.load(open(os.path.join(d, "cut", f"timeline_{tag}.json")))
        self.cap = json.load(open(os.path.join(d, "cut", f"captions_{tag}.json"), encoding="utf-8"))
        self.words = self.cap["words"]; self.D = round(self.tl[-1]["out_end"], 3)
        self.joins = [s["v_out_start"] for s in self.tl[1:]]
        self.js, self.segments, self.moves, self.shown = [], [], [], []   # shown: (scene, t) each time a scene goes up
        self.keys = {}      # scene -> when its main visual has landed (tk.key); dwell is measured from here
        self.assets = {}    # published name -> source file (screenshots for S.shot); style.page copies them
        self.mode, self.face_since, self.seg_start = "FACE", 0.0, 0.0
        self.ready = 0.0   # scenes.py holds every element until this time: text never lands on a panel still sliding in
        self.cap_top, self.cap_h, _, _ = style.caption_geom(cfg)
        self.T = style.tokens(d)
        self.used_screen = self.used_bubble = False   # page() only adds the screen video / bubble ring when a schedule uses them
        self.screen_src = (cfg.get("screen_cuts") or {}).get(tag)
        self._geometry()
        ft = os.path.join(d, "cut", f"facetrack_{tag}.json")
        self.ftrack = json.load(open(ft))["track"] if os.path.exists(ft) else None   # face_track.py: [t, cx, cy, h]
        self._pending_face = None; self.merged = []; self.pip_since = None
        if self.G and self.G["expand"]:                           # FACE is the full-frame face from the first frame
            x, y, s = self._expanded(); self.add(f"tl.set('#facewrap',{{x:{x},y:{y},scale:{s}}},0);")
            self._caps(False, 0, 0, instant=True)

    # ------------------------------------------------------------------ geometry from the measured face
    def _geometry(self):
        W, H = self.W, self.H
        faces = json.load(open(os.path.join(self.d, "faces.json"))) if os.path.exists(os.path.join(self.d, "faces.json")) else {}
        f = sorted(faces.values(), key=lambda v: v["w"])[len(faces) // 2] if faces else {"cx": W / 2, "cy": H * 0.38, "w": W * 0.3, "h": W * 0.3}
        fh = f["h"] * 1.05                                            # clean cut alternates ~0-10% punch-ins
        ov = self.cfg.get("split", {}); G = self.G
        if G:                                                    # stacked: the graphics band is the side away from the face
            ct, ch = G["cap_top"], G["cap_h"]
            if G["side"] == "bottom": self.page_box = (70, 110, W - 140, ct - 20 - 110); self.full_box = (80, 150, W - 160, ct - 30 - 150)
            else:
                y = ct + ch + 20; self.page_box = (70, y, W - 140, H - 90 - y); self.full_box = (80, y + 10, W - 160, H - 120 - y)
            self.win = None; self.cap_split = None
        elif self.vertical:
            top = max(0, f["cy"] - fh / 2 - ov.get("headroom", 0.5) * fh)   # room to breathe above the head
            bot = min(H, f["cy"] + ov.get("below", 0.75) * fh)              # chin clear, shirt kept for captions
            self.win = (0, round(top), W, round(bot))
            wh = self.win[3] - self.win[1]
            self.cap_split = wh - 130                                   # captions sit on the shirt, as in FACE mode
            pt = wh + 30
            self.page_box = (80, pt, W - 160, H - pt - 50)
            self.full_box = (80, 150, W - 160, round(H * 0.66) - 190)
        else:
            cw = ov.get("width", 0.44) * W
            x0 = max(0, min(W - cw, f["cx"] - cw / 2))
            self.win = (round(x0), 0, round(x0 + cw), H)
            self.cap_split = None
            self.page_box = (round(cw + W * 0.03), round(H * 0.09), round(W - cw - W * 0.07), round(H * 0.68))
            fh_ = round(H * 0.64); fw = round(min(W * 0.8, fh_ * 1.6))   # a centred column: a 1536px-wide card reads as empty
            self.full_box = (round((W - fw) / 2), round(H * 0.1), fw, fh_)
        self._bubble_geometry(f)

    def _bubble_geometry(self, f):
        """Bubble bottom right, ~23% of the width across (a typical face-cam bubble), showing head and shoulders.
        config.json "bubble_layout": {"r", "cx", "cy"} places the bubble; "src_r", "src_cx", "src_cy" pick the circle
        cut from the face frame. The face video is scaled by r/src_r and moved so src centre lands on the bubble centre."""
        W, H = self.W, self.H; bl = self.cfg.get("bubble_layout", {})
        r = bl.get("r", round(W * (0.115 if not self.vertical else 0.2)))
        m = round(W * 0.022)
        self.bub = {"r": r, "cx": bl.get("cx", W - m - r), "cy": bl.get("cy", H - m - r),
                    "src_r": bl.get("src_r", f["h"] * 1.18), "src_cx": bl.get("src_cx", f["cx"]), "src_cy": bl.get("src_cy", f["cy"] + f["h"] * 0.14)}
        sx, sy = self.bub["src_cx"], self.bub["src_cy"]
        # Clip radii in face-frame pixels: corner = clips nothing (same look as no clip, but it tweens to the bubble);
        # inner = the biggest circle that fits inside the frame. Shrinking goes corner -> inner fast, then inner -> bubble,
        # so the face reads as a circle for most of the move instead of a rectangle (a face in a box was rejected).
        self.big_r = round(max(math.hypot(sx - cx, sy - cy) for cx in (0, W) for cy in (0, H)) + 2)
        self.inner_r = round(max(min(sx, W - sx, sy, H - sy), self.bub["src_r"] * 1.05))
        b = self.bub; left = b["cx"] - b["r"]
        # PIP content keeps clear of the bubble: a column from the left edge to just short of the bubble
        self.pip_box = (round(W * 0.06), round(H * 0.1), round(left - W * 0.06 - W * 0.035), round(H * 0.68)) if not self.vertical else \
            (80, 150, W - 160, round(b["cy"] - b["r"] - 190))
        # 16:9 default: the face PANEL, a portrait rectangle vertically centred on the right, and the graphic on a card
        # to its left as if the speaker were showing it. config.json "bubble_shape": "circle" keeps a round bubble.
        self.shape = "circle" if self.vertical else self.cfg.get("bubble_shape", "panel")
        if self.shape == "panel":
            pl = self.cfg.get("panel_layout", {})
            pw = pl.get("w", round(W * 0.14)); ph = pl.get("h", round(pw * 4 / 3)); x0 = W - m - pw; y0 = (H - ph) // 2
            sh = pl.get("src_h", min(H, f["h"] * 2.25)); sw = sh * pw / ph   # head, shoulders and room: a tight crop reads "zoomed in"
            scx = min(max(pl.get("src_cx", f["cx"]), sw / 2), W - sw / 2)
            scy = min(max(pl.get("src_cy", f["cy"] + f["h"] * 0.12), sh / 2), H - sh / 2)
            self.panel = {"x0": x0, "y0": y0, "w": pw, "h": ph, "s": ph / sh, "scx": scx, "scy": scy, "rad": 18}
            self.bub.update(r=pw / 2, cx=x0 + pw / 2, cy=H / 2)                                 # pip_box / caps read these
            cw = x0 - 2 * m; chh = round(cw * 9 / 16)                                           # the card: 16:9, left of the panel
            self.card = (m, (H - chh) // 2, cw, chh); pad = round(W * 0.03)
            self.full_pre = '<div id="pcard"></div>'                                            # style.page puts it under the scenes
            self.pip_box = (m + pad, (H - chh) // 2 + pad, cw - 2 * pad, chh - 2 * pad)

    def _expanded(self):
        """#facewrap transform that grows the stacked band to cover the frame (centred), for FACE beats."""
        G = self.G; k = G["cover"] / G["s"]
        return round((self.W - G["fw"] * G["cover"]) / 2, 2), round((self.H - G["fh"] * G["cover"]) / 2 - G["band_y"], 2), round(k, 5)

    def css(self):
        if self.G:                                               # a thin lit line on the seam between face and graphics
            return (f"#edge{{left:0;top:{self.G['seam'] - 2}px;width:{self.W}px;height:4px;opacity:1;"
                    f"background:linear-gradient(90deg,rgba(96,165,250,.08),#60A5FA,rgba(96,165,250,.08));box-shadow:0 0 18px rgba(59,130,246,.55);}}")
        W, H = self.W, self.H; x0, y0, x1, y1 = self.win
        if self.vertical:
            return (f"#edge{{left:0;top:{y1 - y0 - 100}px;width:{W}px;height:110px;"
                    f"background:linear-gradient(to bottom,rgba(18,33,75,0) 0%,rgba(18,33,75,.85) 70%,#12214B 100%);}}")
        return (f"#edge{{left:{x1 - x0 - 120}px;top:0;width:130px;height:{H}px;"
                f"background:linear-gradient(to right,rgba(10,18,40,0) 0%,rgba(10,18,40,.85) 70%,#0a1228 100%);}}")

    # ------------------------------------------------------------------ word lookup
    def at(self, phrase, after=0.0, end=False):
        """Start (or end) time of the first occurrence of `phrase` at/after `after` on the output timeline."""
        n = lambda s: re.sub(r"[^a-z0-9']", "", s.lower())
        toks = [n(x) for x in phrase.split()]; ws_ = [n(w["w"]) for w in self.words]
        for i in range(len(ws_) - len(toks) + 1):
            if self.words[i]["s"] >= after - 1e-6 and ws_[i:i + len(toks)] == toks:
                return self.words[i + len(toks) - 1]["e"] if end else self.words[i]["s"]
        raise KeyError(f"phrase not found after {after}: {phrase!r}")

    def add(self, s): self.js.append(s)

    def asset(self, path):
        """Register an image the page shows; returns the name to put in src (style.page copies it into the project)."""
        name = "a_" + os.path.basename(path).replace(" ", "_")
        if self.assets.get(name, path) != path: name = f"a{len(self.assets)}_" + os.path.basename(path).replace(" ", "_")
        self.assets[name] = os.path.abspath(path); return name

    def key(self, scene, t):
        """Mark when a scene's main visual (the screenshot, the lit cards, the payoff) has fully landed."""
        self.keys[scene] = max(self.keys.get(scene, 0.0), t)

    # ------------------------------------------------------------------ cut sweep
    def _avoid_cut(self, t, kind):
        """Entering B-roll: if a picture cut falls within [t-0.6, t+0.45], start so the graphic covers the cut.
        Returning to the face: if a cut falls within (t, t+0.6], return exactly on the cut (no 1-frame flash).
        PIP/SCREEN shrink the face like SPLIT moves it, so they start 0.4 s early: the cut lands mid-move, never
        as a full-size flash of the next take right before the shrink."""
        for J in self.joins:
            if kind in ("full", "split", "pip", "screen") and t - 0.6 <= J <= t + 0.45:
                nt = J - (0.52 if kind == "full" else 0.4); self.moves.append((kind, t, nt)); return nt
            if kind == "face" and t < J <= t + 0.6:
                self.moves.append((kind, t, J)); return J
        return t

    def _snap_join(self, t, kind):
        """SCREEN <-> graphic over a recorded screen track: the screen changes at the take joins, not at the words, so
        a switch near a join that ignores it shows the wrong take's raw screen for a few frames (read as a glitch).
        The graphic is fully in 0.05 s before the join; the screen comes back exactly on it."""
        for J in self.joins:
            if abs(J - t) <= 0.8:
                nt = J - (TR if self.shape == "panel" else FULL_IN) - 0.05 if kind == "pip" else J
                self.moves.append((kind, t, nt)); return nt
        return t

    # ------------------------------------------------------------------ layout moves
    def _drift(self, t0, t1):
        if t1 - t0 > 0.3:
            self.add(f"tl.fromTo('#facezoom',{{scale:1}},{{scale:1.03,duration:{t1 - t0:.3f},ease:'none',immediateRender:false}},{t0:.3f});")

    def _win_state(self):
        x0, y0, x1, y1 = self.win; W, H = self.W, self.H
        clip = f"inset({y0}px {W - x1}px {H - y1}px {x0}px)"
        return -x0, -y0, clip

    def _caps(self, split, t, dur, instant=False):
        if self.G:                                               # stacked: captions only move when the face grows to full frame
            if not self.G["expand"]: return
            y = 0 if split else round(self.H * 0.66) - self.G["cap_top"]
            v = f"{{y:{y}}}"
        elif self.vertical:
            y = (self.cap_split - self.cap_top) if split else 0
            v = f"{{y:{y}}}"
        else:  # horizontal: captions keep their full-width band under both panels (shrinking them into the face
            return  # column made them unreadable); page_box and full_box end above the caption band
        self.add(f"tl.set('#caps',{v},{t:.3f});" if instant else f"tl.to('#caps',{{...{v},duration:{dur},ease:'power3.inOut'}},{t:.3f});")

    def _to_split(self, t, dur, instant=False):
        if self.G:
            if self.G["expand"]:                                 # full-frame face -> its band
                x, y, s = self._expanded(); e = "#edge"
                if instant: self.add(f"tl.set('#facewrap',{{x:0,y:0,scale:1}},{t:.3f}); tl.set('{e}',{{opacity:1}},{t:.3f});")
                else:
                    self.add(f"tl.fromTo('#facewrap',{{x:{x},y:{y},scale:{s}}},{{x:0,y:0,scale:1,duration:{dur},ease:'power3.inOut',immediateRender:false}},{t:.3f});")
                    self.add(f"tl.fromTo('{e}',{{opacity:0}},{{opacity:1,duration:0.3,ease:'sine.out',immediateRender:false}},{t + dur * 0.7:.3f});")
                self._caps(True, t, dur, instant)
            return
        x, y, clip = self._win_state()
        if instant:
            self.add(f"tl.set('#facewrap',{{x:{x},y:{y},clipPath:'{clip}'}},{t:.3f}); tl.set('#edge',{{opacity:1}},{t:.3f});")
        else:
            self.add(f"tl.fromTo('#facewrap',{{x:0,y:0,clipPath:'inset(0px 0px 0px 0px)'}},{{x:{x},y:{y},clipPath:'{clip}',duration:{dur},ease:'power3.inOut',immediateRender:false}},{t:.3f});")
            self.add(f"tl.fromTo('#edge',{{opacity:0}},{{opacity:1,duration:0.3,ease:'sine.out',immediateRender:false}},{t + dur * 0.7:.3f});")
        self._caps(True, t, dur, instant)

    def _to_face(self, t, dur, instant=False):
        if self.G:
            if self.G["expand"]:                                 # band -> full-frame face (at most MAX_EXPAND upscale)
                x, y, s = self._expanded()
                if instant: self.add(f"tl.set('#facewrap',{{x:{x},y:{y},scale:{s}}},{t:.3f}); tl.set('#edge',{{opacity:0}},{t:.3f});")
                else:
                    self.add(f"tl.to('#edge',{{opacity:0,duration:0.15}},{t:.3f});")
                    self.add(f"tl.fromTo('#facewrap',{{x:0,y:0,scale:1}},{{x:{x},y:{y},scale:{s},duration:{dur},ease:'power3.inOut',immediateRender:false}},{t:.3f});")
                self._caps(False, t, dur, instant)
            return
        x, y, clip = self._win_state()
        if instant:
            self.add(f"tl.set('#facewrap',{{x:0,y:0,clipPath:'inset(0px 0px 0px 0px)'}},{t:.3f}); tl.set('#edge',{{opacity:0}},{t:.3f});")
        else:
            self.add(f"tl.to('#edge',{{opacity:0,duration:0.15}},{t:.3f});")
            self.add(f"tl.fromTo('#facewrap',{{x:{x},y:{y},clipPath:'{clip}'}},{{x:0,y:0,clipPath:'inset(0px 0px 0px 0px)',duration:{dur},ease:'power3.inOut',immediateRender:false}},{t:.3f});")
        self._caps(False, t, dur, instant)

    # ------------------------------------------------------------------ face-centred panel
    def _face_c(self, t, half=0.75):
        """Median face centre in the cut around t (cut pixels), or None without a face track."""
        if not self.ftrack: return None
        pts = [r for r in self.ftrack if abs(r[0] - t) <= half] or [min(self.ftrack, key=lambda r: abs(r[0] - t))]
        xs = sorted(r[1] for r in pts); ys = sorted(r[2] + r[3] * 0.12 for r in pts)
        return xs[len(xs) // 2], ys[len(ys) // 2]

    def _set_center(self, t):
        """Point the panel's source crop at the face at time t. Returns True if it moved."""
        if self.shape != "panel": return False
        c = self._face_c(t)
        if not c: return False
        P = self.panel; sh = P["h"] / P["s"]; sw = sh * P["w"] / P["h"]
        nx = min(max(c[0], sw / 2), self.W - sw / 2); ny = min(max(c[1], sh / 2), self.H - sh / 2)
        moved = abs(nx - P["scx"]) > FOLLOW_MIN or abs(ny - P["scy"]) > FOLLOW_MIN
        P["scx"], P["scy"] = nx, ny
        return moved

    def _follow(self, t0, t1):
        """While the panel is up, ease the crop onto the face every FOLLOW_EVERY s (the speaker moves, takes punch in)."""
        if self.shape != "panel" or not self.ftrack: return
        t = t0
        while t + 1.2 < t1 - 0.2:
            a = self._panel_state(0.0)
            if self._set_center(t + 1.2):
                b = self._panel_state(0.0)
                self.add(f"tl.fromTo('#facewrap',{{x:{a[0]},y:{a[1]},clipPath:'{a[3]}'}},{{x:{b[0]},y:{b[1]},clipPath:'{b[3]}',"
                         f"duration:1.2,ease:'sine.inOut',immediateRender:false}},{t:.3f});")
            t += FOLLOW_EVERY

    def _pip_out(self, t):
        """Leaving PIP at t: the follow moves for the span that is ending."""
        if self.mode == "PIP" and self.pip_since is not None: self._follow(self.pip_since, t)
        self.pip_since = None

    # ------------------------------------------------------------------ bubble (PIP / SCREEN)
    def _panel_state(self, q):
        """The face at morph position q (0 = in the panel, 1 = full frame), solved in SCREEN space: each edge of the
        visible window moves straight from the panel's edge to the frame's edge, the face scales from the panel's scale
        to 1, and the frame is clamped so it always covers the window. Returns (x, y, scale, clip-path) for #facewrap
        (transform-origin 0 0; the clip is in its own pixels). The old circle grow moved the bubble to the middle of the
        frame, parked, then burst open, which read as choppy."""
        P, W, H = self.panel, self.W, self.H
        s = P["s"] + (1 - P["s"]) * q
        L, T = P["x0"] * (1 - q), P["y0"] * (1 - q)
        R, B = P["x0"] + P["w"] + (W - P["x0"] - P["w"]) * q, P["y0"] + P["h"] + (H - P["y0"] - P["h"]) * q
        ax = P["x0"] + P["w"] / 2 + (P["scx"] - P["x0"] - P["w"] / 2) * q
        ay = P["y0"] + P["h"] / 2 + (P["scy"] - P["y0"] - P["h"] / 2) * q
        x = min(max(ax - s * P["scx"], R - s * W), L); y = min(max(ay - s * P["scy"], B - s * H), T)
        l, t_, r, b = (L - x) / s, (T - y) / s, W - (R - x) / s, H - (B - y) / s
        rad = P["rad"] * (1 - q) / s
        return (round(x, 2), round(y, 2), round(s, 5),
                f"inset({max(0, t_):.1f}px {max(0, r):.1f}px {max(0, b):.1f}px {max(0, l):.1f}px round {rad:.1f}px)")

    def _panel_morph(self, t, dur, grow, n=24):
        """Keyframes of _panel_state along power3.inOut, linear between samples (GSAP cannot tween the solved path)."""
        ease = lambda p: 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2
        qs = [ease(i / n) if grow else 1 - ease(i / n) for i in range(n + 1)]
        for i in range(n):
            x0, y0, s0, c0 = self._panel_state(qs[i]); x1, y1, s1, c1 = self._panel_state(qs[i + 1])
            self.add(f"tl.fromTo('#facewrap',{{x:{x0},y:{y0},scale:{s0},clipPath:'{c0}'}},{{x:{x1},y:{y1},scale:{s1},clipPath:'{c1}',"
                     f"duration:{dur / n:.4f},ease:'none',immediateRender:false}},{t + dur * i / n:.4f});")

    def _bub_state(self):
        if self.shape == "panel": return self._panel_state(0.0)
        b = self.bub; s = b["r"] / b["src_r"]
        clip = f"circle({b['src_r']:.1f}px at {b['src_cx']:.1f}px {b['src_cy']:.1f}px)"
        return round(b["cx"] - s * b["src_cx"], 2), round(b["cy"] - s * b["src_cy"], 2), round(s, 5), clip

    def _clip(self, r):
        b = self.bub; return f"circle({r:.1f}px at {b['src_cx']:.1f}px {b['src_cy']:.1f}px)"

    def _big_clip(self): return self._clip(self.big_r)

    def _clip_tw(self, t, dur, shrink):
        """Two clip tweens: the frame corners round off in the first 40% (shrink) / last 40% (grow), the circle
        itself scales with the face the rest of the way."""
        a, b, c = (self.big_r, self.inner_r, self.bub["src_r"]) if shrink else (self.bub["src_r"], self.inner_r, self.big_r)
        d1, d2 = (dur * 0.4, dur * 0.6) if shrink else (dur * 0.6, dur * 0.4)
        e1, e2 = ("power1.out", "power2.inOut") if shrink else ("power2.inOut", "power1.in")
        self.add(f"tl.fromTo('#facewrap',{{clipPath:'{self._clip(a)}'}},{{clipPath:'{self._clip(b)}',duration:{d1:.3f},ease:'{e1}',immediateRender:false}},{t:.3f});")
        self.add(f"tl.fromTo('#facewrap',{{clipPath:'{self._clip(b)}'}},{{clipPath:'{self._clip(c)}',duration:{d2:.3f},ease:'{e2}',immediateRender:false}},{t + d1:.3f});")

    def _caps_bubble(self, on, t, dur=0.45):
        """Burned 16:9 captions would run under the bubble: shrink and slide them into the space left of it."""
        if self.vertical or self.cfg.get("captions", "burn") != "burn": return
        if on:
            left, right = self.W * 0.04, self.bub["cx"] - self.bub["r"] - self.W * 0.02
            sc = min(1.0, (right - left) / (self.W * 0.78)); x = (left + right) / 2 - self.W * sc / 2; y = self.cap_h * (1 - sc) / 2
            self.add(f"tl.to('#caps',{{x:{x:.1f},y:{y:.1f},scale:{sc:.4f},duration:{dur},ease:'power3.inOut'}},{t:.3f});")
        else:
            self.add(f"tl.to('#caps',{{x:0,y:0,scale:1,duration:{dur},ease:'power3.inOut'}},{t:.3f});")

    def _ring(self, on, t):
        self.used_bubble = True
        self.add(f"tl.to('#bring',{{opacity:{1 if on else 0},duration:{0.25 if on else 0.12},ease:'sine.out'}},{t:.3f});")

    def _shrink_to_bubble(self, t, dur):
        """Full-frame face -> bubble, animated. The clip starts as a circle too big to clip anything, so it can tween."""
        self._set_center(t + dur)                          # land on where the face is, not on the whole video's median
        x, y, s, clip = self._bub_state()
        self.add(f"tl.set('#facewrap',{{zIndex:40}},{t:.3f});")
        if self.shape == "panel": self._panel_morph(t, dur, grow=False)
        else:
            self.add(f"tl.fromTo('#facewrap',{{x:0,y:0,scale:1}},{{x:{x},y:{y},scale:{s},duration:{dur},ease:'power3.inOut',immediateRender:false}},{t:.3f});")
            self._clip_tw(t, dur, True)
        self._ring(True, t + dur * 0.8); self._caps_bubble(True, t)

    def _grow_from_bubble(self, t, dur):
        """Bubble -> full-frame face, animated, above every layer; the layers under it are hidden once it covers them."""
        x, y, s, clip = self._bub_state()
        self._ring(False, t)
        if self.shape == "panel": self._panel_morph(t, dur, grow=True)
        else: self.add(f"tl.fromTo('#facewrap',{{x:{x},y:{y},scale:{s}}},{{x:0,y:0,scale:1,duration:{dur},ease:'power3.inOut',immediateRender:false}},{t:.3f});")
        # ONE clip tween on the same ease as the move, so the visible circle opens continuously to the frame corners.
        # The old two-step grow held the circle at face size for 60% of the move, then burst open: a big round face
        # parked mid-frame, then a jump. The graphic under it fades over the second half instead of vanishing at the end.
        if self.shape != "panel":
            self.add(f"tl.fromTo('#facewrap',{{clipPath:'{self._clip(self.bub['src_r'])}'}},{{clipPath:'{self._clip(self.big_r)}',duration:{dur},ease:'power3.inOut',immediateRender:false}},{t:.3f});")
        # fade what the layer SHOWS, not the layer: an opacity tween on the full-frame #full trips hyperframes lint
        # (gsap_fullscreen_overlay_starts_visible) and the navy layer under a dissolving graphic reads cleaner anyway
        # only the scene on screen: a fromTo on every '#full .scene' set all the earlier, hidden scenes back to opacity 1
        # for the length of the fade, so old graphics ghosted over the grow
        layer = (f"#{self.full_sid}" + (",#pcard" if self.shape == "panel" else "")) if self.mode == "PIP" else "#screen video"
        self.add(f"tl.fromTo('{layer}',{{opacity:1}},{{opacity:0,duration:{dur * 0.5:.3f},ease:'sine.in',immediateRender:false}},{t + dur * 0.45:.3f});")
        if self.mode != "PIP": self.add(f"tl.set('{layer}',{{opacity:1}},{t + dur + 0.05:.3f});")
        self.add(f"tl.set('#facewrap',{{zIndex:5,clipPath:'inset(0px 0px 0px 0px)'}},{t + dur + 0.01:.3f});")
        self._caps_bubble(False, t)

    def _bubble_pop(self, t):
        """The face is hidden under a layer (FULL, a wipe in progress): park it in the bubble and fade it in."""
        self._set_center(t + 0.3)
        x, y, s, clip = self._bub_state()
        self.add(f"tl.set('#facewrap',{{x:{x},y:{y},scale:{s},clipPath:'{clip}',zIndex:40}},{t:.3f}); tl.set('#edge',{{opacity:0}},{t:.3f});")
        self.add(f"tl.fromTo('#facewrap',{{opacity:0}},{{opacity:1,duration:0.3,ease:'sine.out',immediateRender:false}},{t:.3f});")
        self._ring(True, t + 0.05); self._caps(False, t, 0, instant=True); self._caps_bubble(True, t)

    def _bubble_hide(self, t, to="face"):
        """Fade the bubble out, then park the face (behind an opaque layer, which the caller guarantees) in its
        full-frame or SPLIT geometry. Returns when it is parked."""
        self._ring(False, t)
        self.add(f"tl.to('#facewrap',{{opacity:0,duration:{BUB_FADE},ease:'sine.in'}},{t:.3f});")
        tp = t + BUB_FADE + 0.01
        if to == "split":
            x, y, clip = self._win_state()
            self.add(f"tl.set('#facewrap',{{x:{x},y:{y},scale:1,clipPath:'{clip}',zIndex:5,opacity:1}},{tp:.3f}); tl.set('#edge',{{opacity:1}},{tp:.3f});")
            self._caps(True, tp, 0, instant=True)
        else:
            self.add(f"tl.set('#facewrap',{{x:0,y:0,scale:1,clipPath:'inset(0px 0px 0px 0px)',zIndex:5,opacity:1}},{tp:.3f});")
        self._caps_bubble(False, t)
        return tp

    # ------------------------------------------------------------------ layers
    def _layer_in(self, sel, t, instant=False):
        if sel == "#full" and not instant and getattr(self, "shape", "") == "panel":
            # the panel shrinks while the navy fades up behind it and the card settles in: one move, not a wipe racing
            # a shrink (that read as choppy)
            self.add(f"tl.set('#full',{{clipPath:'inset(0% 0% 0% 0%)'}},{t:.3f});"
                     f"tl.fromTo('#fullbg',{{opacity:0}},{{opacity:1,duration:{TR * 0.8:.3f},ease:'sine.inOut',immediateRender:false}},{t:.3f});"
                     f"tl.fromTo('#pcard',{{opacity:0,scale:0.965}},{{opacity:1,scale:1,duration:{TR:.3f},ease:'power3.out',immediateRender:false}},{t + TR * 0.25:.3f});")
            return
        if sel == "#full": self.add(f"tl.set('#fullbg',{{opacity:1}},{t:.3f});")
        if instant: self.add(f"tl.set('{sel}',{{clipPath:'inset(0% 0% 0% 0%)'}},{t:.3f});")
        else: self.add(f"tl.fromTo('{sel}',{{clipPath:'inset(100% 0% 0% 0%)'}},{{clipPath:'inset(0% 0% 0% 0%)',duration:{FULL_IN},ease:'power3.inOut',immediateRender:false}},{t:.3f});")

    def _layer_out(self, sel, t, instant=False):
        if instant: self.add(f"tl.set('{sel}',{{clipPath:'inset(100% 0% 0% 0%)'}},{t:.3f});")
        else: self.add(f"tl.fromTo('{sel}',{{clipPath:'inset(0% 0% 0% 0%)'}},{{clipPath:'inset(0% 0% 100% 0%)',duration:0.45,ease:'power3.inOut',immediateRender:false}},{t:.3f});")

    def _full_scene(self, t, scene, cross=False):
        """Show a scene in the #full layer (FULL and PIP share it). cross: fade the old scene out first."""
        if cross:
            old = f"#{self.full_sid}" if getattr(self, "full_sid", None) else "#full .scene"
            self.add(f"tl.to('{old}',{{opacity:0,duration:0.3,ease:'sine.in'}},{t:.3f});"
                     f"tl.fromTo('#{scene}',{{opacity:0}},{{opacity:1,duration:0.35,ease:'sine.out',immediateRender:false}},{t + 0.15:.3f});")
            self.ready = max(self.ready, t + 0.3)
        else:
            self.add(f"tl.set('#full .scene',{{opacity:0}},{t:.3f}); tl.set('#{scene}',{{opacity:1}},{t:.3f});")
        self.shown.append((scene, t)); self.full_sid = scene

    def _leave(self, t):
        if self.mode != "FACE": self.segments.append((self.mode, self.seg_start, t))
        self.seg_start = t

    # ------------------------------------------------------------------ public moves
    def split(self, t):
        """Enter SPLIT. Returns the (possibly moved) start time; build the scene from the returned time."""
        self._resolve(t)
        if self.mode == "FACE" and self.G and not self.G["expand"]:
            # stacked band: the face does not move, so a picture cut near the entry needs no cover; the graphic just arrives
            self._drift(self.face_since, t); self.seg_start = t; self.ready = t + 0.1
        elif self.mode == "FACE":
            t = self._avoid_cut(t, "split"); self._drift(self.face_since, t + TR); self._to_split(t, TR); self.seg_start = t; self.ready = t + TR * 0.8
        elif self.mode == "FULL":
            self._to_split(t - 0.02, 0, instant=True)
            self.add(f"tl.fromTo('#full',{{clipPath:'inset(0% 0% 0% 0%)'}},{{clipPath:'inset(0% 0% 100% 0%)',duration:0.5,ease:'power3.inOut',immediateRender:false}},{t:.3f});")
            self.segments.append(("FULL", self.seg_start, t)); self.seg_start = t; self.ready = t + 0.35
        elif self.mode in ("PIP", "SCREEN"):
            self._pip_out(t); self._leave(t); tp = self._bubble_hide(t, "split")       # parked behind the #full / #screen layer
            self._layer_out("#full" if self.mode == "PIP" else "#screen", tp)
            if self.mode == "PIP": self.add(f"tl.set('#full .scene',{{opacity:0}},{tp + 0.46:.3f});")
            t = tp; self.ready = t + 0.35
        self.mode = "SPLIT"; return t

    def full(self, t, scene):
        self._resolve(t)
        if getattr(self, "shape", "") == "panel":
            self.add(f"tl.to('#pcard',{{opacity:0,duration:0.25}},{t:.3f});")         # FULL: the graphic is the whole frame
        if self.mode in ("PIP", "SCREEN"):
            self._pip_out(t); self._leave(t)
            if self.mode == "PIP":
                self._full_scene(t, scene, cross=True); self._bubble_hide(t)
            else:
                self._full_scene(t, scene); self._layer_in("#full", t); self._bubble_hide(t)   # face parks under #screen
                self._layer_out("#screen", t + FULL_IN + 0.02, instant=True); self.ready = t + FULL_IN * 0.8
            self.mode = "FULL"; return t
        if self.mode == "FACE":
            t = self._avoid_cut(t, "full"); self._drift(self.face_since, t + FULL_IN); self.seg_start = t
        elif self.mode == "SPLIT":
            self.segments.append(("SPLIT", self.seg_start, t)); self.seg_start = t
            self.add(f"tl.set('#page .scene',{{opacity:0}},{t + FULL_IN:.3f});")
        self.add(f"tl.set('#full .scene',{{opacity:0}},{t:.3f}); tl.set('#{scene}',{{opacity:1}},{t:.3f});"); self.shown.append((scene, t))
        self.ready = t + (FULL_IN * 0.8 if self.mode != "FULL" else 0)
        if self.mode != "FULL":
            # #fullbg starts transparent (the PIP panel fades it up itself): FULL must make it opaque, or the graphic
            # sits on the live face instead of covering it
            self.add(f"tl.set('#fullbg',{{opacity:1}},{t:.3f});")
            self.add(f"tl.fromTo('#full',{{clipPath:'inset(100% 0% 0% 0%)'}},{{clipPath:'inset(0% 0% 0% 0%)',duration:{FULL_IN},ease:'power3.inOut',immediateRender:false}},{t:.3f});")
            self._to_face(t + FULL_IN + 0.02, 0, instant=True)
        self.mode = "FULL"; return t

    def pip(self, t, scene):
        """Enter PIP: the graphic covers the frame (lay it out in pip_box), the face stays as the bubble.
        Returns the (possibly moved) start time; build the scene from it."""
        if self.G: raise RuntimeError("stacked layout: PIP is not available (the face keeps its band); use split() or full()")
        if self.mode == "SCREEN": t = self._snap_join(t, "pip")
        self._resolve(t)
        m = self.mode
        if self.shape == "panel": self.add(f"tl.set('#pcard',{{opacity:1}},{t:.3f});")
        if m == "FACE":
            t = self._avoid_cut(t, "pip"); self._drift(self.face_since, t + TR); self.seg_start = t
            self._full_scene(t, scene); self._layer_in("#full", t); self._shrink_to_bubble(t, TR); self.ready = t + FULL_IN * 0.8
        elif m == "SPLIT":
            self._leave(t); self._full_scene(t, scene); self._layer_in("#full", t)
            self.add(f"tl.set('#page .scene',{{opacity:0}},{t + FULL_IN:.3f});"); self._bubble_pop(t + FULL_IN * POP_AT); self.ready = t + FULL_IN * 0.8
        elif m == "FULL":
            self._leave(t); self._full_scene(t, scene, cross=True); self._bubble_pop(t)
        elif m == "PIP":
            self._full_scene(t, scene, cross=True)
        elif m == "SCREEN":
            self._leave(t); self._full_scene(t, scene); self._layer_in("#full", t)
            self._layer_out("#screen", t + FULL_IN + 0.02, instant=True); self.ready = t + FULL_IN * 0.8
        if m != "PIP": self.pip_since = t + TR
        self.mode = "PIP"; return t

    def screen(self, t):
        """Enter SCREEN: the cut screen track fills the frame, the face stays as the bubble. Returns the start time."""
        if self.G: raise RuntimeError("stacked layout: SCREEN is not available; a recorder's screen half is usually a script view")
        if not self.screen_src: raise RuntimeError(f"no screen track for tag {self.tag}: run assemble.py <ws> --screen first")
        if self.mode in ("FULL", "PIP"): t = self._snap_join(t, "screen")
        self._resolve(t)
        self.used_screen = True; m = self.mode
        if m == "FACE" and t < 0.3 and not self.shown:
            # a recording that opens on the screen: start there, the face already small. Animating FACE -> SCREEN at 0
            # put a full-frame camera shot and a shrinking face under the first word.
            self.seg_start = 0.0; self._set_center(0.3); x, y, s, clip = self._bub_state()
            self._layer_in("#screen", 0.0, instant=True); self.used_bubble = True
            self.add(f"tl.set('#facewrap',{{x:{x},y:{y},scale:{s},clipPath:'{clip}',zIndex:40}},0);tl.set('#bring',{{opacity:1}},0);")
            self._caps_bubble(True, 0.0)
            self.shown.append((None, 0.0)); self.mode = "SCREEN"; self.ready = 0.0; return 0.0
        if m == "FACE":
            t = self._avoid_cut(t, "screen"); self._drift(self.face_since, t + TR); self.seg_start = t
            self._layer_in("#screen", t); self._shrink_to_bubble(t, TR)
        elif m == "SPLIT":
            self._leave(t); self._layer_in("#screen", t)
            self.add(f"tl.set('#page .scene',{{opacity:0}},{t + FULL_IN:.3f});"); self._bubble_pop(t + FULL_IN * POP_AT)
        elif m in ("FULL", "PIP"):
            self._pip_out(t); self._leave(t); self._layer_in("#screen", t, instant=True); self._layer_out("#full", t)
            self.add(f"tl.set('#full .scene',{{opacity:0}},{t + 0.46:.3f});")
            if m == "FULL": self._bubble_pop(t)
        self.shown.append((None, t)); self.mode = "SCREEN"; self.ready = 0.0; return t

    def face(self, t):
        """Back to the speaker. Deferred from a graphic: if the next graphic arrives within MIN_FACE, the face beat is
        dropped and the graphic crosses to the next one (see _resolve). Returns the (possibly moved) time."""
        if self._pending_face is not None: return self._pending_face      # already on the way back to the face
        t = self._avoid_cut(t, "face")
        if self.mode in ("PIP", "FULL", "SPLIT", "SCREEN"):
            self._pending_face = t; return t
        return self._face_now(t)

    def _resolve(self, t_next):
        """Called by every move: emit or drop a pending face beat."""
        if self._pending_face is None: return
        tf = self._pending_face; self._pending_face = None
        if t_next is not None and t_next - tf < MIN_FACE: self.merged.append((tf, t_next)); return
        self._face_now(tf)

    def _face_now(self, t):
        self._pip_out(t)
        if self.mode == "SPLIT":
            self.add(f"tl.to('#page .scene',{{opacity:0,duration:0.18,ease:'power1.in'}},{t:.3f});"); self._to_face(t, TR * 0.85)
        elif self.mode == "FULL":
            self.add(f"tl.fromTo('#full',{{clipPath:'inset(0% 0% 0% 0%)'}},{{clipPath:'inset(0% 0% 100% 0%)',duration:0.45,ease:'power3.inOut',immediateRender:false}},{t:.3f});")
        elif self.mode in ("PIP", "SCREEN"):
            d = TR * 1.1; self._grow_from_bubble(t, d)          # a touch longer: one continuous move reads smoother
            self._layer_out("#full" if self.mode == "PIP" else "#screen", t + d + 0.02, instant=True)
            if self.mode == "PIP": self.add(f"tl.set('#full .scene',{{opacity:0}},{t + d + 0.02:.3f});")
        self.segments.append((self.mode, self.seg_start, t)); self.shown.append((None, t)); self.mode = "FACE"; self.face_since = t; self.ready = 0.0; return t

    def band(self, t, scene):
        """Stacked layout: put `scene` in the graphics band, entering SPLIT if no beat is up, else swapping the scene.
        The band is never left empty: between beats hold a topic card (scenes.title_card) instead of calling face().
        Returns the start time; build the scene from it."""
        if self.mode != "SPLIT" or self._pending_face is not None: t = self.split(t)
        self.pscene(t, scene); return t

    def pscene(self, t, scene, fade=0.25):
        """Swap the scene shown in the SPLIT graphics area."""
        self.add(f"tl.to('#page .scene',{{opacity:0,duration:{fade},ease:'power1.in'}},{t:.3f}); tl.set('#{scene}',{{opacity:1}},{t + fade:.3f});"); self.shown.append((scene, t))
        self.ready = max(self.ready, t + fade)

    def finish(self):
        self._resolve(None)
        if self.mode == "PIP": self._pip_out(self.D)
        if self.mode == "FACE": self._drift(self.face_since, self.D)
        else: self.segments.append((self.mode, self.seg_start, self.D))
        return "\n".join(self.js)

    def layers(self):
        """(css, html) for the bubble ring and the screen track. Empty unless the schedule used them, so a page built
        without PIP/SCREEN is byte-identical to before."""
        css, html = "", ""
        if self.used_bubble and self.shape == "panel":
            P = self.panel; cx, cy, cw, ch = self.card
            css += (f"#bring{{position:absolute;left:{P['x0']}px;top:{P['y0']}px;width:{P['w']}px;height:{P['h']}px;border-radius:{P['rad']}px;"
                    f"z-index:41;opacity:0;pointer-events:none;box-shadow:0 0 0 3px rgba(96,165,250,.9),0 0 34px rgba(59,130,246,.45),0 14px 40px rgba(0,0,0,.55);}}"
                    f"#pcard{{position:absolute;left:{cx}px;top:{cy}px;width:{cw}px;height:{ch}px;border-radius:18px;opacity:0;overflow:hidden;"
                    f"background:linear-gradient(160deg,rgba(22,36,68,.86) 0%,rgba(12,18,34,.82) 55%,rgba(10,16,30,.86) 100%);"
                    f"border:1.5px solid rgba(96,165,250,.34);"
                    f"box-shadow:0 0 0 1px rgba(96,165,250,.06),0 0 80px rgba(59,130,246,.20),0 24px 70px rgba(0,0,0,.5);}}"
                    f"#pcard::before{{content:'';position:absolute;left:8%;right:8%;top:0;height:1.5px;"
                    f"background:linear-gradient(90deg,rgba(96,165,250,0),rgba(147,197,253,.85),rgba(96,165,250,0));}}"
                    f"#pcard::after{{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 70% 55% at 50% 0%,rgba(59,130,246,.16),rgba(59,130,246,0) 70%);}}")
            html += '<div id="bring"></div>'
        elif self.used_bubble:
            b = self.bub
            css += (f"#bring{{position:absolute;left:{b['cx'] - b['r']:.0f}px;top:{b['cy'] - b['r']:.0f}px;width:{2 * b['r']:.0f}px;height:{2 * b['r']:.0f}px;"
                    f"border-radius:50%;z-index:41;opacity:0;pointer-events:none;box-shadow:0 0 0 4px rgba(96,165,250,.85),0 12px 36px rgba(0,0,0,.55);}}")
            html += '<div id="bring"></div>'
        if self.used_screen:
            css += ("#screen{position:absolute;inset:0;z-index:28;background:#000;clip-path:inset(100% 0% 0% 0%);}"
                    "#screen video{width:100%;height:100%;object-fit:contain;display:block;}")
            html += (f'<div id="screen"><video id="scr" data-start="0" data-duration="{self.D}" data-track-index="2" src="screen.mp4" muted playsinline></video></div>')
        return css, html

    def report(self):
        tot = sum(b - a for _, a, b in self.segments)
        print(f"B-roll {tot:.1f}s of {self.D:.1f}s ({100 * tot / self.D:.0f}%)")
        if self.G:
            G = self.G; z = max([s.get("zoom", 1.0) for s in self.tl] or [1.0])
            up = (G["cover"] if G["expand"] else G["s"]) * z * 1.03            # FACE beats at full frame scale by cover
            print(f"   stacked: face band {G['fw']}x{G['fh']} at y={G['band_y']}..{G['band_y'] + G['bh']} of {self.W}x{self.H}, band scale {G['s']:.2f}, "
                  f"take punch-ins up to {z:.2f}, face drift 1.03 -> largest upscale {up:.2f}x")
            print(f"   graphics page_box {self.page_box}, captions y={G['cap_top']}..{G['cap_top'] + G['cap_h']}, seam y={G['seam']}; FACE beats "
                  + (f"grow the face to full frame ({G['cover']:.2f}x)" if G["expand"] else f"keep the band (full frame would need {G['cover']:.2f}x)"))
            if up > 1.2: print("   UPSCALE: the face is scaled over 1.2x; record the camera band at the canvas width or pass --no-punch")
        if self.G and not self.G["expand"]:
            # a FACE beat in the stacked layout leaves the graphics band as plain background: in a vertical frame
            # that reads as unfinished. Flag every stretch with no beat up over EMPTY_BAND seconds.
            occ = sorted((a, b) for m, a, b in self.segments if m in ("SPLIT", "FULL")); t0 = 0.0; gaps = []
            for a, b in occ + [(self.D, self.D)]:
                if a - t0 > EMPTY_BAND: gaps.append((t0, a))
                t0 = max(t0, b)
            for a, b in gaps:
                print(f"   EMPTY BAND {a:6.2f}-{b:6.2f} ({b - a:4.1f}s): the graphics band is plain background; run a beat "
                      f"through it or hold a topic card (tk.band(t, sid) + scenes.title_card)")
            if not gaps: print(f"   band occupied: no stretch over {EMPTY_BAND:.0f}s without a beat")
        if self.G and self.page_box[3] < self.H * 0.3:
            print(f"   SMALL SPLIT PAGE: the stacked graphics band is {self.page_box[3]}px; the camera band leaves too little room")
        elif self.vertical and any(m == "SPLIT" for m, _, _ in self.segments) and self.page_box[3] < self.H * 0.35:
            print(f"   SMALL SPLIT PAGE: graphics get {self.page_box[3]}px of {self.H} under a large face; set config.json "
                  f"\"split\": {{\"headroom\": 0.2, \"below\": 0.5}} (defaults 0.5 / 0.75 face heights) and rebuild")
        by = {}
        for m, a, b in self.segments: by[m] = by.get(m, 0) + b - a
        if any(k in by for k in ("PIP", "SCREEN")):
            print("   " + ", ".join(f"{k} {v:.1f}s" for k, v in sorted(by.items())) + f"  (face hidden only in FULL: {by.get('FULL', 0):.1f}s)")
        for m, a, b in self.segments:
            print(f"   {m:5} {a:6.2f}-{b:6.2f} ({b - a:4.1f}s)" + ("   LONG FULL: bring the face back (PIP keeps it on)" if m == "FULL" and b - a > FACELESS_MAX else ""))
        for k, a, b in self.moves: print(f"   moved {k} {a:.2f} -> {b:.2f} (picture cut)")
        # a face beat shorter than the move back and forth is not a face beat: the grow (TR*1.1) is still running when the
        # next graphic arrives, and its end-of-move cleanup hides the new scene (once: an empty card for
        # 50 s after a 0.24 s face gap). Stay in the graphic instead (cross to the next scene).
        seg = sorted(self.segments, key=lambda x: x[1])
        for (m1, a1, b1), (m2, a2, b2) in zip(seg, seg[1:]):
            if 0.01 < a2 - b1 < MIN_DWELL: print(f"   SHORT FACE GAP {b1:.2f}-{a2:.2f} ({a2 - b1:.2f}s) between {m1} and {m2}: drop the face() call there")
        ev = self.shown + [(None, self.D)]
        for (sc, a), (_, b) in zip(ev, ev[1:]):        # scene on screen from its key moment until the next scene or the face
            a = max(a, self.keys.get(sc, a)) if sc else a
            if sc and b - a < MIN_DWELL: print(f"   SHORT DWELL {sc} {a:.2f}-{b:.2f} ({b - a:.1f}s): hold it longer or cut it")
