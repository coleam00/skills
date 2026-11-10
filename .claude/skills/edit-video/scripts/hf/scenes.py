"""Scene library. Every scene lays out inside a box (x, y, w, h) on the canvas and scales its type to the box, so
the same scene works in a vertical SPLIT, a vertical FULL, or a 16:9 side panel.

House rules baked in (each one came from a real review; see references/captions-and-broll.md):
- elements appear when they are SPOKEN, never pre-faded/greyed waiting for their word
- no "fig. 1" labels, no zero-padded "01" numbering, no rubber stamps, no slapped-on badges
- every label and list item starts with a capital letter
- one accent colour; highlight = a marker sweep behind the word; red only for crossed-out / rejected
- hand-drawn marks (rough.py) for circles, checks, underlines, strikes: drawn on, never stretched
Usage pattern (in a schedule): html = scenes.checklist(tk, "scan", box, "Before you trust it", [("The model", t1), ...], t0)
"""
import json, math

import rough
import style

_seed = [100]
def _s():
    _seed[0] += 1; return _seed[0]

TYPE_SCALE = 1.0   # config.json "type_scale", set by engine.Track. Applies to the wide 16:9 boxes (FULL, PIP) only

def unit(box):
    """Type scale for a box: 1.0 at 920x760 (a vertical panel), capped so 16:9 full-screen does not shout.
    A 16:9 talking-head edit sets "type_scale" ~1.25: at 1.0 its PIP and FULL scenes filled a third of the frame and
    read as half-empty. SPLIT panels (under ~1000 px wide) are left alone."""
    u = min(box[2] / 920, box[3] / 700, 1.35)
    return u * TYPE_SCALE if box[2] > 1000 else u

def est_w(text, size, mono=False):
    return len(text) * size * (0.6 if mono else 0.56)     # Inter 700-800 / JetBrains Mono average advance

def base_css(t):
    return f"""
.a {{ position:absolute; opacity:0; }}
.hd {{ font-family:'{t['font']}'; font-weight:800; color:{t['ink']}; letter-spacing:-0.03em; line-height:1.06;
  text-shadow:0 0 26px rgba(59,130,246,.30), 0 2px 10px rgba(0,0,0,.35); }}
.tx {{ font-family:'{t['font']}'; font-weight:700; color:{t['ink']}; letter-spacing:-0.02em; line-height:1.15; }}
.sub {{ font-family:'{t['font']}'; font-weight:600; color:{t['ink2']}; letter-spacing:-0.01em; }}
.mono {{ font-family:'{t['mono']}'; font-weight:500; color:{t['ink']}; letter-spacing:-0.02em; }}
.lab {{ font-family:'{t['mono']}'; font-weight:500; color:{t['accent_light']}; }}
.acc {{ color:{t['accent_light']}; }}
.rule {{ position:absolute; height:2px; background:rgba(148,163,184,.3); transform-origin:0 50%; opacity:0; }}
.mk {{ position:relative; display:inline-block; isolation:isolate; }}
.mk > .hl {{ position:absolute; left:-0.12em; right:-0.12em; top:12%; bottom:4%; border-radius:6px; background:{t['marker']}; z-index:-1;
  transform-origin:0 50%; transform:scaleX(0); }}
svg.mark {{ position:absolute; overflow:visible; pointer-events:none; }}
svg.mark path {{ fill:none; stroke-linecap:round; stroke-linejoin:round; }}
.card {{ background:{t['surface']}; border:2px solid rgba(96,165,250,.55); border-radius:18px; box-shadow:10px 12px 0 {t['accent_deep']}; }}
"""

# ------------------------------------------------------------------ marks
def mark(kind, sid, color, width, box_px):
    """An SVG hand mark drawn in real pixels inside box_px = (left, top, w, h) relative to its parent."""
    L, T, bw, bh = box_px; s = _s()
    if kind == "circle": d, _ = rough.ellipse(bw / 2, bh / 2, bw / 2 * 0.94, bh / 2 * 0.88, seed=s)
    elif kind == "underline": d, _ = rough.underline(4, bw - 4, bh * 0.35, seed=s, sag=7)
    elif kind == "strike": d, _ = rough.strike(0, bw, bh / 2, seed=s, amp=bh * 0.42)
    elif kind == "check": d, _ = rough.check(bw * 0.08, bh * 0.42, s=bw / 60, seed=s)
    elif kind == "sig": d, _ = rough.signature(6, bh * 0.45, w=bw * 0.86, seed=s)
    elif kind == "box": d, _ = rough.box(2, 2, bw - 4, bh - 4, seed=s)
    else: raise ValueError(kind)
    return (f'<svg class="mark" id="{sid}" viewBox="0 0 {bw:.0f} {bh:.0f}" style="left:{L:.0f}px;top:{T:.0f}px;width:{bw:.0f}px;height:{bh:.0f}px">'
            f'<path pathLength="1" stroke-dasharray="1" stroke-dashoffset="1" d="{d}" stroke="{color}" stroke-width="{width}"/></svg>')

def mk_text(text, sid, size, kind=None, color=None, hl=False, width=6, mono=False):
    """Inline span with an optional marker (hl) and/or a hand mark sized from the text."""
    w = est_w(text, size, mono); h = size * 1.05
    m = ""
    if kind:
        bx = {"circle": (-0.08 * w - 12, -0.32 * h, 1.16 * w + 24, 1.62 * h), "underline": (-6, h * 0.92, w + 12, 30),
              "strike": (-8, h * 0.2, w + 16, h * 0.6)}[kind]
        m = mark(kind, f"{sid}m", color, width, bx)
    return f'<span class="mk" id="{sid}">{"<span class=hl></span>" if hl else ""}{text}{m}</span>'

# ------------------------------------------------------------------ motion primitives
def rise(tk, sel, t, d=0.45, y=26):
    t = max(t, tk.ready)
    tk.add(f"tl.fromTo('{sel}',{{opacity:0,y:{y}}},{{opacity:1,y:0,duration:{d},ease:'expo.out',immediateRender:false}},{t:.3f});")

def reveal(tk, sel, t, d=0.55):
    """Left-to-right wipe; insets are negative top/bottom so descenders and ascenders are never clipped."""
    t = max(t, tk.ready)
    tk.add(f"tl.fromTo('{sel}',{{opacity:1,clipPath:'inset(-15% 100% -30% -2%)'}},{{opacity:1,clipPath:'inset(-15% -3% -30% -2%)',duration:{d},ease:'power4.out',immediateRender:false}},{t:.3f});")

def fade(tk, sel, t, d=0.3, to=1):
    t = max(t, tk.ready)
    tk.add(f"tl.fromTo('{sel}',{{opacity:0}},{{opacity:{to},duration:{d},ease:'sine.out',immediateRender:false}},{t:.3f});")

def pop(tk, sel, t, d=0.3):
    t = max(t, tk.ready)
    tk.add(f"tl.fromTo('{sel}',{{opacity:0,scale:1.07}},{{opacity:1,scale:1,duration:{d},ease:'power4.out',immediateRender:false}},{t:.3f});")

def ink(tk, sel, t, d=0.5):
    t = max(t, tk.ready)
    tk.add(f"tl.fromTo('{sel} path',{{attr:{{'stroke-dashoffset':1}}}},{{attr:{{'stroke-dashoffset':0}},duration:{d},ease:'power2.inOut',immediateRender:false}},{t:.3f});")

def marker(tk, sel, t, d=0.32):
    t = max(t, tk.ready)
    tk.add(f"tl.fromTo('{sel} > .hl',{{scaleX:0}},{{scaleX:1,duration:{d},ease:'power2.out',immediateRender:false}},{t:.3f});")

def rule(tk, sel, t, d=0.45):
    t = max(t, tk.ready)
    tk.add(f"tl.fromTo('{sel}',{{opacity:1,scaleX:0}},{{opacity:1,scaleX:1,duration:{d},ease:'power3.inOut',immediateRender:false}},{t:.3f});")

def typeon(tk, sel, text, t, cps=40):
    t = max(t, tk.ready)
    tk.add(f"tl.set('{sel}',{{opacity:1,textContent:''}},{t:.3f});")
    step = max(1, round(cps / 30))
    for i in range(step, len(text) + step, step):
        tk.add(f"tl.set('{sel}',{{textContent:{json.dumps(text[:min(i, len(text))])}}},{t + i / cps:.3f});")

def drift(tk, sel, t0, t1, amt=1.018):
    return      # off: a sub-pixel creep renders as 1 px hops (see motion._cam)
    if t1 - t0 > 0.6: tk.add(f"tl.fromTo('{sel}',{{scale:1}},{{scale:{amt},duration:{t1 - t0:.3f},ease:'sine.inOut',immediateRender:false}},{t0:.3f});")

def _scene(sid, body, tk=None, box=None, used=None):
    """Wrap a scene. Flow scenes pass the height they used: full-screen scenes (and every 16:9 scene) sit at the box's
    optical centre instead of hanging from its top edge with the bottom half empty. Vertical SPLIT stays top-aligned,
    right under the face."""
    centre = tk is not None and (getattr(tk, "valign", "top") == "center" or tuple(box) == tuple(tk.full_box))
    if centre and used and used < box[3]:
        body = f'<div style="position:absolute;left:0;top:{(box[3] - used) * 0.42:.0f}px;width:100%;height:100%">{body}</div>'
    return f'<div class="scene" id="{sid}">{body}</div>'

# ================================================================== scenes
def statement(tk, sid, box, lines, t0):
    """Stacked statement lines. lines: [dict(text, t, kind='head'|'line'|'sub'|'accent', mark=None|'strike'|'underline'|'circle',
    key=None (word inside text to mark/highlight, default whole line), hl=False)]. A strike line greys out after drawing."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []; yy = y
    size = {"head": 104, "line": 76, "accent": 96, "sub": 50}
    def height(u_):
        tot = 0.0
        for L in lines:
            fs = round(size[L.get("kind", "line")] * u_); nl = max(1, math.ceil(est_w(L["text"], fs) / w))
            tot += fs * 1.12 * nl + (0.42 * fs if L.get("kind") in ("head", "accent") else 0.3 * fs)
        return tot
    while height(u) > h and u > 0.4: u *= 0.94          # fit: four lines at type_scale 1.45 ran off the bottom of pip_box
    for i, L in enumerate(lines):
        fs = round(size[L.get("kind", "line")] * u); col = t_["accent_light"] if L.get("kind") == "accent" else t_["ink"]
        txt = L["text"]; key = L.get("key", txt); pre, _, post = txt.partition(key)
        span = mk_text(key, f"{sid}k{i}", fs, L.get("mark"), t_["bad"] if L.get("mark") == "strike" else t_["accent_light"], L.get("hl", False), 7)
        cls = "sub" if L.get("kind") == "sub" else "hd"
        out.append(f'<div class="a {cls}" id="{sid}l{i}" style="left:{x}px;top:{yy:.0f}px;width:{w}px;font-size:{fs}px;color:{col}">{pre}{span}{post}</div>')
        nl = max(1, math.ceil(est_w(txt, fs) / w))
        yy += fs * 1.12 * nl + (0.42 * fs if L.get("kind") in ("head", "accent") else 0.3 * fs)
        t = L["t"]
        (reveal if L.get("kind") in ("head", "accent") else rise)(tk, f"#{sid}l{i}", t - 0.1)
        if L.get("hl"): marker(tk, f"#{sid}k{i}", t + 0.3)
        if L.get("mark"):
            ink(tk, f"#{sid}k{i}m", L.get("t_mark", t + 0.45), 0.45)
            if L["mark"] == "strike": tk.add(f"tl.to('#{sid}l{i}',{{color:'{t_['ink2']}',duration:0.3}},{L.get('t_mark', t + 0.45) + 0.2:.3f});")
    return _scene(sid, "".join(out), tk, box, yy - y)

def points(tk, sid, box, items, title=None, t_title=None):
    """Plain list lines (questions, steps) with a close underline; key word highlighted on its word. No numbering.
    items: [(pre, key, post, t)]"""
    x, y, w, h = box; u = unit(box); fs = round(60 * u); gap = round(fs * 1.9); out = []; yy = y
    if title:
        tf = round(80 * u); out.append(f'<div class="a hd" id="{sid}t" style="left:{x}px;top:{yy}px;width:{w}px;font-size:{tf}px">{title}</div>')
        reveal(tk, f"#{sid}t", t_title); yy += round(tf * 1.6)
    for i, (pre, key, post, t) in enumerate(items):
        out.append(f'<div class="a tx" id="{sid}r{i}" style="left:{x}px;top:{yy}px;width:{w}px;font-size:{fs}px">{pre}{mk_text(key, f"{sid}k{i}", fs, hl=True)}{post}</div>')
        out.append(f'<div class="rule" id="{sid}u{i}" style="left:{x}px;top:{yy + round(fs * 1.25)}px;width:{w}px"></div>')
        reveal(tk, f"#{sid}r{i}", t - 0.2, 0.5); rule(tk, f"#{sid}u{i}", t); marker(tk, f"#{sid}k{i}", t + 0.25); yy += gap
    return _scene(sid, "".join(out), tk, box, yy - y)

def checklist(tk, sid, box, items, t0, title=None, t_title=None):
    """Hand-drawn checkboxes; rows and boxes build at scene start, each check is drawn on its spoken word.
    items: [(text, t)]"""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []; yy = y
    if title:
        tf = round(80 * u); out.append(f'<div class="a hd" id="{sid}t" style="left:{x}px;top:{yy}px;width:{w}px;font-size:{tf}px">{title}</div>')
        reveal(tk, f"#{sid}t", t_title if t_title is not None else t0 + 0.2); yy += round(tf * (1.25 if est_w(title, tf) <= w else 2.4)) + round(24 * u)
    n = len(items); fs = round(min(58 * u, (y + h - yy) / max(n, 1) / 1.9)); gap = round(fs * 1.9); bx = round(fs * 1.15)
    for i, (text, t) in enumerate(items):
        out.append(f'<div class="a" id="{sid}r{i}" style="left:{x}px;top:{yy}px;width:{w}px;height:{gap - 10}px;display:flex;align-items:center;gap:{round(fs * 0.55)}px">'
                   f'<span style="position:relative;width:{bx}px;height:{bx}px;flex:none">{mark("box", f"{sid}b{i}", t_["ink"], 4, (0, 0, bx, bx))}'
                   f'{mark("check", f"{sid}c{i}", t_["accent_light"], 8, (-6, -bx * 0.35, bx * 1.3, bx * 1.3))}</span>'
                   f'<span class="tx" style="font-size:{fs}px">{text}</span></div>')
        out.append(f'<div class="rule" id="{sid}u{i}" style="left:{x}px;top:{yy + gap - 12}px;width:{w}px"></div>')
        rise(tk, f"#{sid}r{i}", t0 + 0.3 + i * 0.07, 0.4); ink(tk, f"#{sid}b{i}", t0 + 0.35 + i * 0.07, 0.35); rule(tk, f"#{sid}u{i}", t0 + 0.4 + i * 0.07)
        ink(tk, f"#{sid}c{i}", t, 0.32); yy += gap
    return _scene(sid, "".join(out), tk, box, yy - y)

def ledger(tk, sid, box, title, headers, rows, t_rows, t0, t_circle=None):
    """Two-column table (e.g. Agent | Owner). Rows land on t_rows; the right column is circled on t_circle."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []
    tf = round(80 * u); fs = round(48 * u); rh = round(fs * 2.4); c2 = x + round(w * 0.56)
    out.append(f'<div class="a hd" id="{sid}t" style="left:{x}px;top:{y}px;width:{w}px;font-size:{tf}px">{title}</div>')
    hy = y + round(tf * (1.3 if est_w(title, tf) <= w else 2.45)) + 20
    out.append(f'<div class="a lab" id="{sid}h" style="left:{x}px;top:{hy}px;width:{w}px;font-size:{round(28 * u)}px;display:flex">'
               f'<span style="width:{c2 - x}px">{headers[0]}</span><span>{headers[1]}</span></div>')
    out.append(f'<div class="rule" id="{sid}r" style="left:{x}px;top:{hy + round(44 * u)}px;width:{w}px;background:{t_["accent"]}"></div>')
    ry0 = hy + round(64 * u)
    for i, (a, b) in enumerate(rows):
        yy = ry0 + i * rh
        out.append(f'<div class="a" id="{sid}x{i}" style="left:{x}px;top:{yy}px;width:{w}px;display:flex;align-items:baseline">'
                   f'<span class="mono" style="width:{c2 - x}px;font-size:{fs}px">{a}</span><span class="tx acc" style="font-size:{round(fs * 1.08)}px">{b}</span></div>')
        out.append(f'<div class="rule" id="{sid}u{i}" style="left:{x}px;top:{yy + rh - 22}px;width:{w}px"></div>')
    span = len(rows) * rh
    out.append(f'<div id="{sid}oc" style="position:absolute;left:{c2 - 30}px;top:{ry0 - 34}px;width:{x + w - c2 + 50}px;height:{span + 40}px">'
               f'{mark("circle", f"{sid}c", t_["accent_light"], 6, (0, 0, x + w - c2 + 50, span + 40))}</div>')
    reveal(tk, f"#{sid}t", t0 + 0.2); fade(tk, f"#{sid}h", t_rows - 0.15, 0.25); rule(tk, f"#{sid}r", t_rows - 0.15)
    for i in range(len(rows)): pop(tk, f"#{sid}x{i}", t_rows + i * 0.16); rule(tk, f"#{sid}u{i}", t_rows + i * 0.16 + 0.1)
    if t_circle is not None: ink(tk, f"#{sid}c", t_circle, 0.7)
    return _scene(sid, "".join(out), tk, box, ry0 + span - y)

def meters(tk, sid, box, rows, t0, n=9):
    """Access meters: per row a title, a capitalised sub-label and n squares; `lit` squares fill on the row's word.
    rows: [(title, sub, lit, color, t)]"""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []
    sq = min(round(86 * u), (w - (n - 1) * 14) // n); step = (w - sq) / (n - 1); rowh = round(380 * u)
    for k, (title, sub, lit, col, t) in enumerate(rows):
        yy = y + k * rowh
        out.append(f'<div class="a hd" id="{sid}h{k}" style="left:{x}px;top:{yy}px;font-size:{round(74 * u)}px">{title}</div>')
        out.append(f'<div class="a lab" id="{sid}s{k}" style="left:{x}px;top:{yy + round(96 * u)}px;font-size:{round(30 * u)}px">{sub}</div>')
        for j in range(n):
            out.append(f'<div class="a" id="{sid}b{k}_{j}" style="left:{x + j * step:.0f}px;top:{yy + round(150 * u)}px;width:{sq}px;height:{sq}px;border:5px solid {t_["ink"]};box-sizing:border-box"></div>')
        reveal(tk, f"#{sid}h{k}", t0 + 0.15 + k * 0.22); fade(tk, f"#{sid}s{k}", t0 + 0.3 + k * 0.22)
        for j in range(n):
            pop(tk, f"#{sid}b{k}_{j}", t0 + 0.4 + k * 0.22 + j * 0.03, 0.22)
            if j < lit: tk.add(f"tl.to('#{sid}b{k}_{j}',{{backgroundColor:'{col}',borderColor:'{col}',duration:0.12}},{t + j * 0.045:.3f});")
    return _scene(sid, "".join(out), tk, box, len(rows) * rowh - round(380 * u) + round(150 * u) + sq)

def ring(tk, sid, box, words, center, t_center, t0):
    """A lifecycle: a hand-drawn loop; each word appears (highlighted) as it is spoken, a dot travels; centre resolves last."""
    x, y, w, h = box; u = unit(box); t_ = tk.T
    R = min(w, h) * 0.4; cx, cy = x + w / 2, y + h / 2
    # a wide box gets an ellipse: on a circle in the 16:9 PIP box the side words sat on the centre label
    rx, ry = (max(R, min(w * 0.30, R * 1.9)), R) if w > h * 1.3 else (R, R)   # 0.36 put the side words past the card edge
    d, _ = rough.circle_path(cx, cy, R, seed=41) if rx == ry else rough.ellipse(cx, cy, rx, ry, seed=41, overshoot=0.04)
    out = [f'<svg class="mark" id="{sid}c" viewBox="0 0 {tk.W} {tk.H}" style="left:0;top:0;width:{tk.W}px;height:{tk.H}px">'
           f'<path pathLength="1" stroke-dasharray="1" stroke-dashoffset="1" d="{d}" stroke="{t_["ink"]}" stroke-width="4"/></svg>']
    n = len(words); fs = round(60 * u)
    for k, (word, t) in enumerate(words):
        a = -90 + k * 360 / n; wx = cx + rx * math.cos(math.radians(a)); wy = cy + ry * math.sin(math.radians(a))
        out.append(f'<div class="a tx" id="{sid}w{k}" style="left:{wx - 170 * u:.0f}px;top:{wy - fs * 0.6:.0f}px;width:{340 * u:.0f}px;text-align:center;font-size:{fs}px">'
                   f'{mk_text(word, f"{sid}k{k}", fs, hl=True)}</div>')
    out.append(f'<div class="a hd" id="{sid}ctr" style="left:{cx - 240 * u:.0f}px;top:{cy - 70 * u:.0f}px;width:{480 * u:.0f}px;text-align:center;font-size:{round(70 * u)}px;color:{t_["accent_light"]}">{center}</div>')
    ink(tk, f"#{sid}c", t0 + 0.2, 1.0)
    for k, (word, t) in enumerate(words): rise(tk, f"#{sid}w{k}", t - 0.05, 0.3, 14); marker(tk, f"#{sid}k{k}", t, 0.25)
    rise(tk, f"#{sid}ctr", t_center, 0.5)
    return _scene(sid, "".join(out))

def card(tk, sid, box, title, fields, t0, countdown=None, side_label=("Valid for", "Then expires")):
    """A key/value card (an access pass, a ticket, a config). Values type on as they are spoken. Optional countdown
    in a side stub that starts ticking as soon as the card appears. fields: [(label, value, t)]"""
    x, y, w, h = box; u = unit(box); t_ = tk.T; stub = round(236 * u) if countdown else 0
    fx = x + round(46 * u); fs = round(46 * u); lf = round(28 * u)
    out = [f'<div class="a card" id="{sid}p" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px">'
           + (f'<div style="position:absolute;left:{w - stub}px;top:0;bottom:0;border-left:4px dashed rgba(148,163,184,.45)"></div>'
              f'<div class="lab" style="position:absolute;left:{w - stub + 34}px;top:{round(46 * u)}px;font-size:{lf}px">{side_label[0]}</div>'
              f'<div class="mono" id="{sid}clk" style="position:absolute;left:{w - stub + 30}px;top:{round(90 * u)}px;font-size:{round(60 * u)}px">{countdown // 60:02d}:{countdown % 60:02d}</div>'
              f'<div class="lab" style="position:absolute;left:{w - stub + 34}px;top:{round(176 * u)}px;font-size:{lf}px">{side_label[1]}</div>' if countdown else "")
           + f'<div class="hd" style="position:absolute;left:{round(46 * u)}px;top:{round(34 * u)}px;font-size:{round(84 * u)}px">{title}</div>'
             f'<div style="position:absolute;left:{round(46 * u)}px;top:{round(150 * u)}px;width:{w - stub - round(92 * u)}px;height:3px;background:{t_["accent"]}"></div></div>']
    yy = y + round(196 * u); rowh = (h - round(220 * u)) / max(len(fields), 1)
    for i, (lab, val, t) in enumerate(fields):
        out.append(f'<div class="a lab" id="{sid}L{i}" style="left:{fx}px;top:{yy + i * rowh:.0f}px;font-size:{lf}px">{lab}</div>')
        out.append(f'<div class="a mono" id="{sid}V{i}" style="left:{fx}px;top:{yy + i * rowh + lf * 1.5:.0f}px;font-size:{fs}px;max-width:{w - stub - round(92 * u)}px"></div>')
        fade(tk, f"#{sid}L{i}", t - 0.25, 0.2); typeon(tk, f"#{sid}V{i}", val, t, 42)
    pop(tk, f"#{sid}p", t0 + 0.1, 0.34)
    if countdown:
        secs, tt = countdown, t0 + 1.0
        while tt < tk.D and secs > 0:
            secs -= 1; tk.add(f"tl.set('#{sid}clk',{{textContent:'{secs // 60:02d}:{secs % 60:02d}'}},{tt:.3f});"); tt += 1.0
    return _scene(sid, "".join(out))

def log(tk, sid, box, lines, t0):
    """Typed mono log lines on a dark slip (traceability, a run log). lines: [(text, t)]"""
    x, y, w, h = box; u = unit(box); fs = round(40 * u)
    out = [f'<div class="a card" id="{sid}p" style="left:{x}px;top:{y}px;width:{w}px;height:{round(len(lines) * fs * 2 + fs * 2)}px"></div>']
    for i, (txt, t) in enumerate(lines):
        out.append(f'<div class="a mono" id="{sid}x{i}" style="left:{x + round(40 * u)}px;top:{y + fs + i * fs * 2:.0f}px;font-size:{fs}px"></div>')
        typeon(tk, f"#{sid}x{i}", txt, t, 46)
    fade(tk, f"#{sid}p", t0 + 0.1, 0.35)
    return _scene(sid, "".join(out), tk, box, round(len(lines) * fs * 2 + fs * 2))

def lanes(tk, sid, box, title_html, lanes_, steps, t0):
    """Two (or more) labelled arrows that shoot across on their words, then a short list of stages.
    lanes_: [(name, color, t)], steps: [(text, t)]"""
    x, y, w, h = box; u = unit(box); out = []
    tf = round(96 * u); out.append(f'<div class="a hd" id="{sid}t" style="left:{x}px;top:{y}px;width:{w}px;font-size:{tf}px">{title_html}</div>')
    reveal(tk, f"#{sid}t", t0 + 0.3)
    ly = y + round(tf * 2.6)
    for k, (name, col, t) in enumerate(lanes_):
        yy = ly + k * round(190 * u)
        out.append(f'<div class="a hd" id="{sid}n{k}" style="left:{x}px;top:{yy - round(100 * u)}px;font-size:{round(72 * u)}px;color:{col}">{name}</div>')
        out.append(f'<div class="a" id="{sid}b{k}" style="left:{x}px;top:{yy}px;width:{w - round(40 * u)}px;height:{round(12 * u)}px;border-radius:6px;background:{col};transform-origin:0 50%"></div>')
        out.append(f'<div class="a" id="{sid}h{k}" style="left:{x + w - round(52 * u)}px;top:{yy - round(22 * u)}px;width:0;height:0;border-top:{round(28 * u)}px solid transparent;border-bottom:{round(28 * u)}px solid transparent;border-left:{round(52 * u)}px solid {col}"></div>')
        rise(tk, f"#{sid}n{k}", t - 0.1, 0.35)
        tk.add(f"tl.fromTo('#{sid}b{k}',{{opacity:1,scaleX:0}},{{opacity:1,scaleX:1,duration:0.45,ease:'power4.in',immediateRender:false}},{t + 0.05:.3f});")
        tk.add(f"tl.fromTo('#{sid}h{k}',{{opacity:0,x:-30}},{{opacity:1,x:0,duration:0.15,ease:'power2.out',immediateRender:false}},{t + 0.45:.3f});")
    sy = ly + len(lanes_) * round(190 * u) - round(40 * u); fs = round(64 * u)
    for j, (txt, t) in enumerate(steps):
        out.append(f'<div class="a tx" id="{sid}s{j}" style="left:{x}px;top:{sy + j * round(fs * 1.55)}px;font-size:{fs}px">{mk_text(txt, f"{sid}sk{j}", fs, hl=True)}</div>')
        rise(tk, f"#{sid}s{j}", t - 0.1, 0.4); marker(tk, f"#{sid}sk{j}", t + 0.2)
    return _scene(sid, "".join(out), tk, box, sy + len(steps) * round(fs * 1.55) - y)

def bignum(tk, sid, box, items, t0):
    """Big accent numbers 1..n with a title and a sub-line each (e.g. 'three jobs'); each appears on its word.
    items: [(title, sub, t)]"""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []; gap = h / max(len(items), 1)
    for k, (title, sub, t) in enumerate(items):
        yy = y + k * gap
        out.append(f'<div class="a" id="{sid}j{k}" style="left:{x}px;top:{yy:.0f}px;width:{w}px;display:flex;gap:{round(34 * u)}px;align-items:flex-start">'
                   f'<span class="hd" style="font-size:{round(150 * u)}px;line-height:.82;color:{t_["accent"]};width:{round(100 * u)}px">{k + 1}</span>'
                   f'<span style="display:flex;flex-direction:column;gap:{round(6 * u)}px"><span class="hd" style="font-size:{round(70 * u)}px">{mk_text(title, f"{sid}k{k}", round(70 * u), hl=True)}</span>'
                   f'<span class="sub" style="font-size:{round(40 * u)}px">{sub}</span></span></div>')
        if k < len(items) - 1: out.append(f'<div class="rule" id="{sid}u{k}" style="left:{x}px;top:{yy + gap - 24:.0f}px;width:{w}px"></div>')
        rise(tk, f"#{sid}j{k}", t - 0.1, 0.45); marker(tk, f"#{sid}k{k}", t + 0.25)
        if k < len(items) - 1: rule(tk, f"#{sid}u{k}", t + 0.2)
    return _scene(sid, "".join(out))

def hub(tk, sid, box, center, items, t0, title_html=None, t_title=None, t_ring=None):
    """A centre node with spokes to tags that land on their words; optional ring closing round them and a title.
    items: [(label, t)]"""
    x, y, w, h = box; u = unit(box); t_ = tk.T
    top = y + (round(150 * u) if title_html else 0); cx, cy = x + w / 2, top + (y + h - top) / 2
    rx, ry = w * 0.43, (y + h - top) * 0.40
    paths, out = [], []
    n = len(items)
    for k, (label, t) in enumerate(items):
        a = -90 + k * 360 / n; tx_, ty_ = cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a))
        d, _, _, _ = rough.arrow(tx_, ty_, cx + 190 * u * math.cos(math.radians(a)), cy + 120 * u * math.sin(math.radians(a)), seed=200 + k, bend=0.08)
        paths.append((f"{sid}s{k}", d, t_["ink2"], 3))
        fs = round(44 * u); tw = est_w(label, fs, True) + 70 * u
        out.append(f'<div class="a card mono" id="{sid}g{k}" style="left:{tx_ - tw / 2:.0f}px;top:{ty_ - fs:.0f}px;width:{tw:.0f}px;height:{fs * 2:.0f}px;'
                   f'display:flex;align-items:center;justify-content:center;font-size:{fs}px;border-radius:12px;box-shadow:6px 7px 0 {t_["accent_deep"]}">{label}</div>')
    d, _ = rough.ellipse(cx, cy, 190 * u, 120 * u, seed=31); paths.append((f"{sid}c", d, t_["ink"], 5))
    if t_ring is not None:
        d, _ = rough.ellipse(cx, cy, rx * 1.12, ry * 1.18, seed=37, overshoot=0.08); paths.append((f"{sid}ring", d, t_["accent"], 8))
    out.insert(0, f'<svg class="mark" viewBox="0 0 {tk.W} {tk.H}" style="left:0;top:0;width:{tk.W}px;height:{tk.H}px">' + "".join(
        f'<path id="{i}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1" d="{dd}" stroke="{c}" stroke-width="{sw}"/>' for i, dd, c, sw in paths) + "</svg>")
    out.append(f'<div class="a hd" id="{sid}ag" style="left:{cx - 200 * u:.0f}px;top:{cy - 46 * u:.0f}px;width:{400 * u:.0f}px;text-align:center;font-size:{round(72 * u)}px">{center}</div>')
    if title_html:
        out.append(f'<div class="a hd" id="{sid}t" style="left:{x}px;top:{y}px;width:{w}px;font-size:{round(92 * u)}px">{title_html}</div>')
        reveal(tk, f"#{sid}t", t_title if t_title is not None else t0 + 0.3)
    tk.add(f"tl.fromTo('#{sid}c',{{attr:{{'stroke-dashoffset':1}}}},{{attr:{{'stroke-dashoffset':0}},duration:0.6,ease:'power2.inOut',immediateRender:false}},{t0 + 0.15:.3f});")
    rise(tk, f"#{sid}ag", t0 + 0.25)
    for k, (label, t) in enumerate(items):
        tk.add(f"tl.fromTo('#{sid}s{k}',{{attr:{{'stroke-dashoffset':1}}}},{{attr:{{'stroke-dashoffset':0}},duration:0.35,ease:'power2.out',immediateRender:false}},{t - 0.12:.3f});")
        pop(tk, f"#{sid}g{k}", t, 0.3)
    if t_ring is not None:
        tk.add(f"tl.fromTo('#{sid}ring',{{attr:{{'stroke-dashoffset':1}}}},{{attr:{{'stroke-dashoffset':0}},duration:1.0,ease:'power2.inOut',immediateRender:false}},{t_ring:.3f});")
    return _scene(sid, "".join(out))

def image_cta(tk, sid, box, img, url, t0, t1):
    """A screenshot on a card plus the URL typed underneath and highlighted (for 'the link I have on screen')."""
    x, y, w, h = box; u = unit(box); fs = round(42 * u)
    # fit width AND height: in a 16:9 card the width-only size ran the caption off the bottom
    iw = round(min(w, (h - fs * 2.6) / 0.58)); ih = round(iw * 0.58); x = x + (w - iw) // 2; w = iw
    out = (f'<div class="a card" id="{sid}p" style="left:{x}px;top:{y}px;width:{w}px;height:{ih}px;padding:12px;box-sizing:border-box">'
           f'<img src="{img}" style="width:100%;height:100%;object-fit:cover;object-position:top;display:block;border-radius:8px"></div>'
           f'<div class="a" id="{sid}u" style="left:{x}px;top:{y + ih + round(40 * u)}px;width:{w}px;text-align:center">'
           f'<span class="mk" id="{sid}k"><span class="hl"></span><span class="mono" id="{sid}ut" style="font-size:{fs}px"></span></span></div>')
    pop(tk, f"#{sid}p", t0 + 0.1, 0.34); tk.add(f"tl.set('#{sid}u',{{opacity:1}},{t0 + 0.6:.3f});")
    typeon(tk, f"#{sid}ut", url, t0 + 0.6, 40); marker(tk, f"#{sid}k", t0 + 0.6 + len(url) / 40 + 0.1, 0.4); drift(tk, f"#{sid}p", t0 + 0.5, t1)
    return _scene(sid, out)

def link_pill(tk, url, t_from):
    """Persistent URL pill above the captions in FACE mode, from t_from to the end. Returns (css, html)."""
    t_ = tk.T; top = tk.cap_top - (round(tk.H * 0.06) if tk.vertical else round(tk.H * 0.1))
    css = (f"#linkpill{{position:absolute;left:0;top:{top}px;width:{tk.W}px;display:flex;justify-content:center;z-index:45;opacity:0}}"
           f"#linkpill span{{font-family:'{t_['mono']}';font-weight:600;font-size:{round(min(tk.W, tk.H) * 0.037)}px;color:{t_['ink']};padding:14px 28px;border-radius:999px;"
           f"background:rgba(7,9,15,.82);border:2px solid {t_['accent']};box-shadow:0 0 24px rgba(59,130,246,.45)}}")
    tk.add(f"tl.fromTo('#linkpill',{{opacity:0,y:16}},{{opacity:1,y:0,duration:0.35,ease:'power3.out',immediateRender:false}},{t_from + 0.35:.3f});")
    return css, f'<div id="linkpill"><span>{url}</span></div>'

# a terminal look that matches a typical dark slide deck (match the speaker's own slides when there are any): a
# near-black panel, three dots, an accent pill top right, the prompt in light accent, commands grey, output near-white, all mono
TERM = {"panel": "#0D1117", "edge": "rgba(148,163,184,.24)", "cmd": "#8B949E", "out": "#FAFAFA", "pill": "#3B82F6"}

def terminal(tk, sid, box, prompt, t_prompt, lines, t0, title="Terminal"):
    """A coding-agent or shell window in the terminal style above: the prompt types on its word, then each line lands on its
    spoken time. lines: [(text, kind, t)], kind = 'cmd' (a command it ran, grey, '$ ' added) | 'out' (output) |
    'tool' (a tool or skill call, light blue) | 'dim' (a quiet note) | 'gap' (an empty line, t ignored).
    Use real output from the run being described: a made-up command or result is decoration and gets cut."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; pad = round(40 * u); hb = round(64 * u); cw = w - 2 * pad
    longest = max([len(("$ " if k == "cmd" else "") + tx) for tx, k, _ in lines] + [24]) + 2
    n_est = len(lines) + 1 + math.ceil(len(prompt) * 0.6 * 34 * u / cw)    # rows: the lines, one blank, the prompt
    fs = round(min(34 * u, cw / (longest * 0.6), (h - hb - 2 * pad) / (n_est * 1.55)))   # fit: never clip a line or a row
    lh = round(fs * 1.55); per = max(8, int(cw / (fs * 0.6)))        # mono advance ~0.6 em: wrap the prompt by hand
    words, rows, cur = prompt.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > per - 2 and cur: rows.append(cur); cur = wd
        else: cur = (cur + " " + wd).strip()
    rows.append(cur)
    ph = min(h, hb + pad + (len(rows) + 1 + len(lines)) * lh + pad)
    dot = round(14 * u)
    dots = "".join(f'<span style="width:{dot}px;height:{dot}px;border-radius:50%;background:{c};display:inline-block;margin-right:{round(10 * u)}px"></span>'
                   for c in ("#F87171", "#FBBF24", "#34D399"))
    pill = (f'<span style="margin-left:auto;background:{TERM["pill"]};color:#fff;border-radius:{round(10 * u)}px;padding:{round(6 * u)}px {round(16 * u)}px;'
            f'font-family:\'{t_["mono"]}\';font-weight:500;font-size:{round(22 * u)}px">{title}</span>')
    out = [f'<div class="a" id="{sid}p" style="left:{x}px;top:{y}px;width:{w}px;height:{ph}px;overflow:hidden;background:{TERM["panel"]};'
           f'border:2px solid {TERM["edge"]};border-radius:{round(18 * u)}px;box-shadow:0 18px 50px rgba(0,0,0,.45)">'
           f'<div style="position:absolute;left:0;top:0;right:0;height:{hb}px;display:flex;align-items:center;padding:0 {pad}px;box-sizing:border-box">{dots}{pill}</div></div>']
    yy = y + hb + round(pad * 0.4)
    for r, row in enumerate(rows):                                     # the prompt, typed row by row
        lead = "&gt; " if r == 0 else "&nbsp;&nbsp;"
        out.append(f'<div class="a mono" id="{sid}g{r}" style="left:{x + pad}px;top:{yy + r * lh}px;font-size:{fs}px;color:{t_["accent_light"]};white-space:pre">{lead}</div>')
        out.append(f'<div class="a mono" id="{sid}pr{r}" style="left:{x + pad + round(fs * 1.2)}px;top:{yy + r * lh}px;font-size:{fs}px;color:{t_["accent_light"]};white-space:pre"></div>')
    tr = t_prompt
    for r, row in enumerate(rows):
        fade(tk, f"#{sid}g{r}", tr - 0.1, 0.15); typeon(tk, f"#{sid}pr{r}", row, tr, 52); tr += len(row) / 52
    yy += (len(rows) + 1) * lh
    for i, (txt, kind, t) in enumerate(lines):
        if kind == "gap": continue
        col = {"cmd": TERM["cmd"], "out": TERM["out"], "tool": t_["accent_light"], "dim": t_["ink2"]}[kind]
        txt = ("$ " + txt) if kind == "cmd" else txt
        out.append(f'<div class="a mono" id="{sid}x{i}" style="left:{x + pad + round(fs * 1.2)}px;top:{yy + i * lh}px;width:{cw - round(fs * 1.2)}px;'
                   f'font-size:{fs}px;color:{col};white-space:pre;overflow:hidden;text-overflow:ellipsis">{txt}</div>')
        rise(tk, f"#{sid}x{i}", t - 0.05, 0.28, 8)
    pop(tk, f"#{sid}p", t0 + 0.1, 0.34)
    return _scene(sid, "".join(out), tk, box, ph)

def file_tree(tk, sid, box, name, tree, t0, preview=None):
    """A notes-app or editor file explorer on the left, files lighting up on their words, and an optional note open
    on the right. When the subject IS a folder of files, showing it beats any metaphor.
    tree: [(label, depth, kind, t)], kind = 'dir' | 'file'; t = when it lights (None: shown from the start, dim).
    preview: (title, [(line, t)], t_open): the open note, its first real lines, typed as they are mentioned."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; pad = round(34 * u); hb = round(60 * u)
    fs = round(min(30 * u, (h - hb - 2 * pad) / (len(tree) * 1.75))); lh = round(fs * 1.75)   # fit every row in the panel
    ew = round(w * (0.42 if preview else 1.0))
    ph = min(h, hb + pad + len(tree) * lh + pad)
    out = [f'<div class="a" id="{sid}p" style="left:{x}px;top:{y}px;width:{w}px;height:{ph}px;overflow:hidden;background:#11151E;'
           f'border:2px solid rgba(148,163,184,.22);border-radius:{round(18 * u)}px;box-shadow:0 18px 50px rgba(0,0,0,.45)">'
           f'<div style="position:absolute;left:0;top:0;width:{ew}px;height:{hb}px;display:flex;align-items:center;padding:0 {pad}px;box-sizing:border-box;'
           f'font-family:\'{t_["font"]}\';font-weight:700;font-size:{round(24 * u)}px;color:{t_["ink2"]};letter-spacing:.02em">{name}</div>'
           + (f'<div style="position:absolute;left:{ew}px;top:0;bottom:0;width:2px;background:rgba(148,163,184,.18)"></div>' if preview else "")
           + '</div>']
    yy = y + hb + round(pad * 0.3)
    for i, (label, depth, kind, t) in enumerate(tree):
        chev = "&#9662;&nbsp;" if kind == "dir" else "&nbsp;&nbsp;&nbsp;"
        weight = 700 if kind == "dir" else 500
        lx = x + pad + depth * round(fs * 1.1)
        out.append(f'<div class="a" id="{sid}f{i}" style="left:{lx}px;top:{yy + i * lh}px;font-family:\'{t_["font"]}\';font-weight:{weight};font-size:{fs}px;'
                   f'color:{t_["ink2"] if t is None else t_["ink"]};white-space:pre"><span style="color:{t_["ink2"]}">{chev}</span>{label}</div>')
        if t is None: fade(tk, f"#{sid}f{i}", t0 + 0.25 + i * 0.03, 0.25, to=0.75)
        else:
            out.append(f'<div class="a" id="{sid}h{i}" style="left:{x + round(pad * 0.4)}px;top:{yy + i * lh - round(lh * 0.16)}px;width:{ew - round(pad * 0.8)}px;'
                       f'height:{round(lh * 0.92)}px;border-radius:{round(10 * u)}px;background:rgba(59,130,246,.22)"></div>')
            fade(tk, f"#{sid}f{i}", t0 + 0.25, 0.25, to=0.75); fade(tk, f"#{sid}h{i}", t - 0.05, 0.2)
            tk.add(f"tl.to('#{sid}f{i}',{{opacity:1,duration:0.2}},{max(t - 0.05, tk.ready):.3f});")
    if preview:
        title, plines, t_open = preview; px = x + ew + pad; pw = w - ew - 2 * pad; pfs = round(min(26 * u, fs * 0.9))
        out.append(f'<div class="a hd" id="{sid}pt" style="left:{px}px;top:{y + hb + round(pad * 0.3)}px;width:{pw}px;font-size:{round(40 * u)}px">{title}</div>')
        rise(tk, f"#{sid}pt", t_open, 0.35, 10)
        tnl = max(1, math.ceil(est_w(title, round(40 * u)) / pw))   # a title that wraps pushes the lines down (it overlapped them)
        py = y + hb + round(pad * 0.3) + round(40 * u * (1.7 + 1.15 * (tnl - 1)))
        for j, (ln, tl_) in enumerate(plines):
            nl = max(1, math.ceil(est_w(ln, pfs) / pw))
            out.append(f'<div class="a tx" id="{sid}pl{j}" style="left:{px}px;top:{py:.0f}px;width:{pw}px;font-size:{pfs}px;font-weight:500;color:{t_["ink2"]}">{ln}</div>')
            rise(tk, f"#{sid}pl{j}", tl_, 0.3, 8); py += pfs * 1.3 * nl + round(pfs * 0.6)
    pop(tk, f"#{sid}p", t0 + 0.1, 0.34)
    return _scene(sid, "".join(out), tk, box, ph)

def columns(tk, sid, box, cols, t0, title=None, t_title=None):
    """2-4 titled columns of short items (a stack, a before/after, the tools vs where I work). Each column's title
    lands on its word with an accent rule over it; items land on theirs. cols: [(title, t, [(item, t), ...])]"""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []; yy = y
    if title:
        tf = round(76 * u); out.append(f'<div class="a hd" id="{sid}t" style="left:{x}px;top:{yy}px;width:{w}px;font-size:{tf}px">{title}</div>')
        reveal(tk, f"#{sid}t", t_title if t_title is not None else t0 + 0.2); yy += round(tf * 1.55)
    n = len(cols); gap = round(46 * u); cw = (w - gap * (n - 1)) / n
    fs_t = round(min(52 * u, cw / 6.2)); fs_i = round(min(40 * u, cw / 7.2)); ymax = yy   # cw/9 read tiny in a 3-column FULL
    for k, (ct, tc, items) in enumerate(cols):
        cx = x + k * (cw + gap)
        out.append(f'<div class="rule" id="{sid}r{k}" style="left:{cx:.0f}px;top:{yy}px;width:{cw:.0f}px;height:5px;background:{t_["accent"]}"></div>')
        out.append(f'<div class="a hd" id="{sid}h{k}" style="left:{cx:.0f}px;top:{yy + round(26 * u)}px;width:{cw:.0f}px;font-size:{fs_t}px;color:{t_["accent_light"]}">{ct}</div>')
        rule(tk, f"#{sid}r{k}", tc - 0.15); rise(tk, f"#{sid}h{k}", tc, 0.4)
        tl_ = max(1, math.ceil(est_w(ct, fs_t) / cw))                  # a title that wraps pushes its items down
        iy = yy + round(26 * u) + round(fs_t * (1.7 + 1.1 * (tl_ - 1)))
        for j, (it, ti) in enumerate(items):
            nl = max(1, math.ceil(est_w(it, fs_i) / cw))
            out.append(f'<div class="a tx" id="{sid}i{k}_{j}" style="left:{cx:.0f}px;top:{iy:.0f}px;width:{cw:.0f}px;font-size:{fs_i}px;font-weight:600">{it}</div>')
            rise(tk, f"#{sid}i{k}_{j}", ti - 0.05, 0.35, 14); iy += fs_i * 1.22 * nl + round(fs_i * 0.55)
        ymax = max(ymax, iy)
    return _scene(sid, "".join(out), tk, box, ymax - y)

def quote(tk, sid, box, text, key, t, t_key=None, sub=None, t_sub=None):
    """One big statement, the key phrase marker-swept as it is said; optional quiet line under it (a source, a
    takeaway). The thesis of a talk, a rule worth remembering."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; fs = round(96 * u); out = []
    pre, _, post = text.partition(key)
    out.append(f'<div class="a hd" id="{sid}g" style="left:{x}px;top:{y}px;font-size:{round(170 * u)}px;line-height:.8;color:{t_["accent"]}">&ldquo;</div>')
    ty = y + round(140 * u)
    out.append(f'<div class="a hd" id="{sid}q" style="left:{x}px;top:{ty}px;width:{w}px;font-size:{fs}px">{pre}{mk_text(key, f"{sid}k", fs, hl=True)}{post}</div>')
    nl = max(1, math.ceil(est_w(text, fs) / w)); yy = ty + fs * 1.1 * nl + round(48 * u)
    fade(tk, f"#{sid}g", t - 0.3, 0.3); reveal(tk, f"#{sid}q", t - 0.1, 0.7); marker(tk, f"#{sid}k", t_key if t_key is not None else t + 0.8, 0.4)
    if sub:
        out.append(f'<div class="rule" id="{sid}u" style="left:{x}px;top:{yy:.0f}px;width:{round(90 * u)}px;height:5px;background:{t_["accent"]}"></div>')
        out.append(f'<div class="a mono" id="{sid}s" style="left:{x}px;top:{yy + round(30 * u):.0f}px;width:{w}px;font-size:{round(38 * u)}px;color:{t_["accent_light"]}">{sub}</div>')
        ts = t_sub if t_sub is not None else t + 1.2; rule(tk, f"#{sid}u", ts - 0.2); rise(tk, f"#{sid}s", ts, 0.4); yy += round(30 * u) + round(38 * u) * 1.3
    return _scene(sid, "".join(out), tk, box, yy - y)

def title_card(tk, sid, box, title, t0, kicker=None, sub=None, t_sub=None):
    """A held topic card: an optional small kicker, the section title, an accent rule, an optional quiet line. For the
    stacked layout's graphics band while no other beat is up (an empty band reads as unfinished in a vertical frame).
    Everything but `sub` lands at t0, so it can sit for several seconds without a cue; `sub` lands on its own word."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []; yy = y
    if kicker:
        fk = round(46 * u)
        out.append(f'<div class="a mono" id="{sid}c" style="left:{x}px;top:{yy}px;width:{w}px;font-size:{fk}px;color:{t_["accent_light"]};'
                   f'letter-spacing:.08em;text-transform:uppercase">{kicker}</div>')
        rise(tk, f"#{sid}c", t0, 0.4); yy += round(fk * 1.9)
    fs = round(104 * u)
    while fs > 40 and max(1, math.ceil(est_w(title, fs) / w)) * fs * 1.12 > h * 0.6: fs = round(fs * 0.94)
    out.append(f'<div class="a hd" id="{sid}t" style="left:{x}px;top:{yy}px;width:{w}px;font-size:{fs}px">{title}</div>')
    reveal(tk, f"#{sid}t", t0 + 0.05, 0.6); yy += fs * 1.12 * max(1, math.ceil(est_w(title, fs) / w)) + round(36 * u)
    out.append(f'<div class="rule" id="{sid}u" style="left:{x}px;top:{yy:.0f}px;width:{round(110 * u)}px;height:6px;background:{t_["accent"]}"></div>')
    rule(tk, f"#{sid}u", t0 + 0.35); yy += round(40 * u)
    if sub:
        fsub = round(54 * u)
        out.append(f'<div class="a sub" id="{sid}s" style="left:{x}px;top:{yy:.0f}px;width:{w}px;font-size:{fsub}px;color:{t_["ink2"]}">{sub}</div>')
        rise(tk, f"#{sid}s", t_sub if t_sub is not None else t0 + 0.6, 0.4)
        yy += fsub * 1.15 * max(1, math.ceil(est_w(sub, fsub) / w))
    return _scene(sid, "".join(out), tk, box, yy - y)

def stats(tk, sid, box, items, t0, mark_i=None, t_mark=None):
    """One to three big figures side by side, each with a short label under it, landing on the word that says the
    number. Optional hand circle on one of them (the surprising one). items: [(value, label, t)]. Only figures the
    speaker says, written the way they are said ("100,000"), never a rounded or derived number. Two or three figures sit
    centred in their columns; a single one is left-aligned (a SPLIT panel)."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []; n = len(items); gap = round(70 * u); cw = (w - gap * (n - 1)) / n
    fv = round(min(230 * u, cw / max(2.4, max(len(v) for v, _, _ in items) * 0.62))); fl = round(min(48 * u, cw / 8))
    al = "center" if n > 1 else "left"
    for i, (val, label, t) in enumerate(items):
        cx = x + i * (cw + gap); vw = est_w(val, fv) * 1.05
        circ = mark("circle", f"{sid}c{i}", t_["accent_light"], 7, (-0.18 * vw, -0.12 * fv, vw * 1.36, fv * 1.3)) if i == mark_i else ""
        out.append(f'<div class="a hd" id="{sid}v{i}" style="left:{cx:.0f}px;top:{y}px;width:{cw:.0f}px;font-size:{fv}px;color:{t_["accent_light"]};text-align:{al}">'
                   f'<span style="position:relative;display:inline-block">{val}{circ}</span></div>')
        rw = round(cw * 0.5); rx = cx + (cw - rw) / 2 if n > 1 else cx
        out.append(f'<div class="rule" id="{sid}r{i}" style="left:{rx:.0f}px;top:{y + round(fv * 1.1)}px;width:{rw}px;height:5px;background:{t_["accent"]}"></div>')
        out.append(f'<div class="a tx" id="{sid}l{i}" style="left:{cx:.0f}px;top:{y + round(fv * 1.1) + round(32 * u)}px;width:{cw:.0f}px;font-size:{fl}px;'
                   f'font-weight:600;text-align:{al}">{label}</div>')
        reveal(tk, f"#{sid}v{i}", t - 0.1, 0.5); rule(tk, f"#{sid}r{i}", t + 0.15); rise(tk, f"#{sid}l{i}", t + 0.25, 0.4, 14)
        if i == mark_i: ink(tk, f"#{sid}c{i}", t_mark if t_mark is not None else t + 0.8, 0.45)
    nl = max(max(1, math.ceil(est_w(lb, fl) / cw)) for _, lb, _ in items)
    used = round(fv * 1.1) + round(32 * u) + fl * 1.25 * nl
    return _scene(sid, "".join(out), tk, box, used)
