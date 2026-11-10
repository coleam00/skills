"""Motion scenes: an idea shown as something moving, not a text card (text cards alone read as a slide deck, not an
edit). Same contract as scenes.py: (tk, sid, box, ..., t0) -> HTML, every
element lands on its spoken time, positions are real pixels inside box, GSAP tweens on x/y/scale/opacity only.

  system_map    a four-part framework as a system around a centre; lines draw on, packets flow; focus= flies into one node
  load_context  files leave a folder and land in a session's context window, one per spoken name
  flow_hub      sources around a centre, data packets travelling in along each spoke
  counter       a figure that counts (10 -> 30) with a bar filling under it
  model_slot    model names cycling through one slot while "Your context" stays put
  gate          chips travel to a wrapper: allowed ones pass, blocked ones bounce back struck out
  pulse         an ECG-style line drawing across; each beat drops a label under it
  test_runner   rows spin, then flip to PASS one by one, then the tally
  kinetic, window_grid, foundation, tiles, converge, declutter, bars, stack_tower, chat, steps, palette
  face_pop / face_shake   punch-in words beside the face, FACE layout only (overlay HTML)
"""
import json, math
import scenes as S
from scenes import unit, est_w, rise, fade, pop, ink, marker, reveal, mk_text, _scene

BLUE, LIGHT, GREEN, RED = "#3B82F6", "#60A5FA", "#34D399", "#F87171"

def _cam(tk, sid, t0, t1, amt=1.035):
    """Was a slow push-in on the whole scene. Off: the renderer snaps text to whole pixels, so a creep under a pixel
    per frame shows as the text sitting still, then hopping 1 px every 2-4 s (measured with phase correlation on a
    real render). Motion comes from the entrances."""
    return
    if t1 - t0 > 0.6:
        tk.add(f"tl.fromTo('#{sid}cam',{{scale:1}},{{scale:{amt},duration:{t1 - t0:.3f},ease:'sine.inOut',immediateRender:false}},{t0:.3f});")

def _wrap(sid, body, ox, oy, clip=None):
    """clip = (x, y, w, h): the scene never draws outside it (a camera move inside the card)."""
    cs = ""
    if clip:
        X, Y, Wc, Hc = clip; cs = f' style="clip-path:inset({Y}px calc(100% - {X + Wc}px) calc(100% - {Y + Hc}px) {X}px round 18px)"'
    return (f'<div class="scene" id="{sid}"{cs}><div id="{sid}cam" style="position:absolute;inset:0;transform-origin:{ox:.0f}px {oy:.0f}px">'
            f'{body}</div></div>')

def _node(nid, x, y, w, h, title, sub, u, t_, accent=False):
    bc = "rgba(96,165,250,.85)" if accent else "rgba(148,163,184,.35)"
    ft = round(min(44 * u, w / 7.0)); fsub = round(min(24 * u, w / 13.5))   # type fits the node (a narrow box shrank the nodes)
    return (f'<div class="a" id="{nid}" style="left:{x - w / 2:.0f}px;top:{y - h / 2:.0f}px;width:{w:.0f}px;height:{h:.0f}px;border-radius:{18 * u:.0f}px;'
            f'background:#0E1525;border:2px solid {bc};box-shadow:0 14px 40px rgba(0,0,0,.45);display:flex;flex-direction:column;justify-content:center;'
            f'align-items:center;text-align:center;gap:{6 * u:.0f}px">'
            f'<div class="hd" style="font-size:{ft}px;color:{t_["accent_light"] if not accent else t_["ink"]}">{title}</div>'
            + (f'<div class="sub" style="font-size:{fsub}px">{sub}</div>' if sub else "") + '</div>')

def _packet(tk, pid, x0, y0, x1, y1, t, n=3, gap=0.75, dur=0.7):
    """A glowing dot travelling x0,y0 -> x1,y1, n times."""
    for i in range(n):
        tt = t + i * gap
        tk.add(f"tl.fromTo('#{pid}',{{x:{x0:.0f},y:{y0:.0f},opacity:0}},{{x:{x1:.0f},y:{y1:.0f},opacity:1,duration:{dur},ease:'power1.in',immediateRender:false}},{tt:.3f});"
               f"tl.to('#{pid}',{{opacity:0,duration:0.12}},{tt + dur:.3f});")

def _dot(pid, r=9):
    return (f'<div id="{pid}" style="position:absolute;left:{-r}px;top:{-r}px;width:{2 * r}px;height:{2 * r}px;border-radius:50%;opacity:0;'
            f'background:{LIGHT};box-shadow:0 0 18px 6px rgba(96,165,250,.6)"></div>')

# ------------------------------------------------------------------ a four-part framework (a video's recurring picture)
def system_map(tk, sid, box, items, t0, center="The system", focus=None, t_focus=None, t_end=None):
    """items: [(title, sub, t)], four of them, placed as a diamond: left, top, right,
    bottom. t=None shows the node from the start. focus=i flies the camera into node i at t_focus and dims the rest."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; cx, cy = x + w / 2, y + h / 2
    rx, ry = w * 0.38, h * 0.36; pos = [(cx - rx, cy), (cx, cy - ry), (cx + rx, cy), (cx, cy + ry)]
    cw_ = min(300 * u, w * 0.24)                                      # centre node; side nodes get the rest of the gap
    nw, nh = min(300 * u, 2 * (rx - cw_ / 2 - 28 * u)), 120 * u; out = []   # 300u side nodes touched the centre
    paths = "".join(f'<path id="{sid}l{i}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1" d="M{cx:.0f} {cy:.0f} L{px:.0f} {py:.0f}" '
                    f'stroke="rgba(96,165,250,.55)" stroke-width="3" fill="none"/>' for i, (px, py) in enumerate(pos))
    out.append(f'<svg class="mark" style="left:0;top:0;width:{tk.W}px;height:{tk.H}px" viewBox="0 0 {tk.W} {tk.H}">{paths}</svg>')
    out.append(_node(f"{sid}c", cx, cy, cw_, 150 * u, center, None, u, t_, accent=True))
    for i, ((title, sub, t), (px, py)) in enumerate(zip(items, pos)):
        out.append(_node(f"{sid}n{i}", px, py, nw, nh, title, sub, u, t_)); out.append(_dot(f"{sid}p{i}"))
    pop(tk, f"#{sid}c", t0 + 0.1, 0.4)
    for i, ((title, sub, t), (px, py)) in enumerate(zip(items, pos)):
        ta = t0 + 0.2 + 0.08 * i if t is None else t
        tk.add(f"tl.fromTo('#{sid}l{i}',{{attr:{{'stroke-dashoffset':1}}}},{{attr:{{'stroke-dashoffset':0}},duration:0.4,ease:'power2.out',immediateRender:false}},{max(ta - 0.2, tk.ready):.3f});")
        pop(tk, f"#{sid}n{i}", ta, 0.35)
        _packet(tk, f"{sid}p{i}", px, py, cx, cy, ta + 0.5, n=2, gap=0.9)
    ox, oy = (pos[focus] if focus is not None else (cx, cy))
    if focus is not None and t_focus is not None:
        # the fly-in waits for every node to land: a node popping in after the dim stayed bright
        t_focus = max(t_focus, max(t0 + 0.2 + 0.08 * i if t is None else t for i, (_, _, t) in enumerate(items)) + 0.4)
        tk.add(f"tl.to('{','.join(f'#{sid}p{i}' for i in range(4) if i != focus)}',{{opacity:0,duration:0.2}},{t_focus:.3f});")
        for i in range(4):
            if i != focus: tk.add(f"tl.to('#{sid}n{i},#{sid}l{i}',{{opacity:0.06,duration:0.4}},{t_focus:.3f});")   # 0.18 read as clutter at 1.9x
        tk.add(f"tl.to('#{sid}c',{{opacity:0.08,duration:0.4}},{t_focus:.3f});")
        # the camera brings the node to the middle as it zooms; on the card the scene is clipped to it (a side
        # node zoomed in place ran past the card and under the face panel)
        tk.add(f"tl.fromTo('#{sid}cam',{{scale:1,x:0,y:0}},{{scale:1.9,x:{cx - ox:.0f},y:{cy - oy:.0f},duration:1.0,ease:'power3.inOut',immediateRender:false}},{t_focus:.3f});")
    elif t_end: _cam(tk, sid, t0, t_end)
    card = getattr(tk, "card", None) if box == getattr(tk, "pip_box", None) else None
    return _wrap(sid, "".join(out), ox, oy, clip=card)

# ------------------------------------------------------------------ files flying into a session's context
def load_context(tk, sid, box, files, t0, t_end=None, title="New session", rest=(), folder="Project files"):
    """files: [(name, what it holds, t)]. The folder on the left, the context window on the right; each file's chip
    flies across on its word and its line lands in the window. rest: entries that stay in the folder."""
    x, y, w, h = box; u = unit(box); t_ = tk.T
    vw = w * 0.34; vx = x; gap = w * 0.08; cwx = x + vw + gap; cww = w - vw - gap
    fs = round(30 * u); lh = round(fs * 1.9); top = y + round(80 * u); out = []
    out.append(f'<div class="a" id="{sid}v" style="left:{vx:.0f}px;top:{y:.0f}px;width:{vw:.0f}px;height:{h:.0f}px;border-radius:{18 * u:.0f}px;'
               f'background:#11151E;border:2px solid rgba(148,163,184,.22)"></div>')
    out.append(f'<div class="a sub" id="{sid}vt" style="left:{vx + 30 * u:.0f}px;top:{y + 22 * u:.0f}px;font-size:{round(24 * u)}px">{folder}</div>')
    out.append(f'<div class="a" id="{sid}w" style="left:{cwx:.0f}px;top:{y:.0f}px;width:{cww:.0f}px;height:{h:.0f}px;border-radius:{18 * u:.0f}px;'
               f'background:#0D1117;border:2px solid rgba(96,165,250,.5);box-shadow:0 18px 50px rgba(0,0,0,.45)"></div>')
    out.append(f'<div class="a mono" id="{sid}wt" style="left:{cwx + 30 * u:.0f}px;top:{y + 22 * u:.0f}px;font-size:{round(24 * u)}px;color:{LIGHT}">&gt; {title}</div>')
    rows = [n for n, _, _ in files] + list(rest)
    for i, name in enumerate(rows):
        out.append(f'<div class="a tx" id="{sid}r{i}" style="left:{vx + 34 * u:.0f}px;top:{top + i * lh:.0f}px;font-size:{fs}px;color:{t_["ink2"]}">'
                   f'{"&#9662; " if i >= len(files) else ""}{name}</div>')
    for i, (name, what, t) in enumerate(files):
        sy = top + i * lh; dy = top + i * round(lh * 1.45)
        out.append(f'<div class="a" id="{sid}k{i}" style="left:{vx + 24 * u:.0f}px;top:{sy - 8 * u:.0f}px;padding:{6 * u:.0f}px {16 * u:.0f}px;border-radius:{10 * u:.0f}px;'
                   f'background:{BLUE};font-family:\'{t_["font"]}\';font-weight:700;font-size:{fs}px;color:#fff;white-space:nowrap">{name}</div>')
        out.append(f'<div class="a sub" id="{sid}d{i}" style="left:{cwx + 34 * u:.0f}px;top:{dy + fs * 1.5:.0f}px;width:{cww - 60 * u:.0f}px;font-size:{round(24 * u)}px">{what}</div>')
        tk.add(f"tl.set('#{sid}k{i}',{{opacity:1}},{t:.3f});"
               f"tl.fromTo('#{sid}k{i}',{{x:0,y:0}},{{x:{cwx + 10 * u - vx - 24 * u:.0f},y:{dy - sy:.0f},duration:0.75,ease:'power3.inOut',immediateRender:false}},{t:.3f});")
        tk.add(f"tl.to('#{sid}r{i}',{{opacity:0.25,duration:0.3}},{t + 0.1:.3f});")
        rise(tk, f"#{sid}d{i}", t + 0.7, 0.35, 10)
    fade(tk, f"#{sid}v", t0 + 0.05, 0.3); fade(tk, f"#{sid}vt", t0 + 0.15); fade(tk, f"#{sid}w", t0 + 0.2, 0.3); fade(tk, f"#{sid}wt", t0 + 0.3)
    for i in range(len(rows)): fade(tk, f"#{sid}r{i}", t0 + 0.3 + 0.05 * i, 0.3)
    _cam(tk, sid, t0, t_end or t0 + 6)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

# ------------------------------------------------------------------ sources feeding a centre
def flow_hub(tk, sid, box, center, items, t0, t_end=None):
    """items: [(label, t)] round an ellipse; each spoke draws on its word, then packets run in along it."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; cx, cy = x + w / 2, y + h / 2; rx, ry = w * 0.40, h * 0.38; out = []; n = len(items)
    pos = [(cx + rx * math.cos(math.radians(-90 + k * 360 / n)), cy + ry * math.sin(math.radians(-90 + k * 360 / n))) for k in range(n)]
    paths = "".join(f'<path id="{sid}s{k}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1" d="M{px:.0f} {py:.0f} L{cx:.0f} {cy:.0f}" '
                    f'stroke="rgba(148,163,184,.45)" stroke-width="3" fill="none"/>' for k, (px, py) in enumerate(pos))
    out.append(f'<svg class="mark" style="left:0;top:0;width:{tk.W}px;height:{tk.H}px" viewBox="0 0 {tk.W} {tk.H}">{paths}</svg>')
    out.append(_node(f"{sid}c", cx, cy, 340 * u, 140 * u, center, None, u, t_, accent=True))
    fs = round(40 * u)
    for k, ((label, t), (px, py)) in enumerate(zip(items, pos)):
        tw = est_w(label, fs, True) + 60 * u
        out.append(f'<div class="a mono" id="{sid}g{k}" style="left:{px - tw / 2:.0f}px;top:{py - fs:.0f}px;width:{tw:.0f}px;height:{fs * 2:.0f}px;display:flex;'
                   f'align-items:center;justify-content:center;font-size:{fs}px;border-radius:12px;background:#0E1525;border:2px solid rgba(96,165,250,.55)">{label}</div>')
        out.append(_dot(f"{sid}p{k}"))
    pop(tk, f"#{sid}c", t0 + 0.15, 0.4)
    for k, ((label, t), (px, py)) in enumerate(zip(items, pos)):
        tk.add(f"tl.fromTo('#{sid}s{k}',{{attr:{{'stroke-dashoffset':1}}}},{{attr:{{'stroke-dashoffset':0}},duration:0.35,ease:'power2.out',immediateRender:false}},{max(t - 0.1, tk.ready):.3f});")
        pop(tk, f"#{sid}g{k}", t, 0.3); _packet(tk, f"{sid}p{k}", px, py, cx, cy, t + 0.35, n=3, gap=1.1)
    _cam(tk, sid, t0, t_end or t0 + 8)
    return _wrap(sid, "".join(out), cx, cy)

# ------------------------------------------------------------------ a figure that counts
def counter(tk, sid, box, start, end, label_from, label_to, t_from, t_to, t0, prefix="", suffix="", t_end=None):
    """Shows start (label_from) on t_from, then counts to end (label_to) on t_to with a bar filling to match."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; fv = round(min(260 * u, w / 4)); out = []
    out.append(f'<div class="a hd" id="{sid}v" style="left:{x}px;top:{y + h * 0.12:.0f}px;width:{w}px;text-align:center;font-size:{fv}px;color:{LIGHT}">'
               f'{prefix}<span id="{sid}n">{start}</span>{suffix}</div>')
    out.append(f'<div class="a sub" id="{sid}l" style="left:{x}px;top:{y + h * 0.12 + fv * 1.1:.0f}px;width:{w}px;text-align:center;font-size:{round(44 * u)}px">{label_from}</div>')
    bw = w * 0.6; bx = x + (w - bw) / 2; by = y + h * 0.12 + fv * 1.1 + 110 * u
    out.append(f'<div class="a" id="{sid}b" style="left:{bx:.0f}px;top:{by:.0f}px;width:{bw:.0f}px;height:{14 * u:.0f}px;border-radius:99px;background:rgba(148,163,184,.18)"></div>')
    out.append(f'<div class="a" id="{sid}f" style="left:{bx:.0f}px;top:{by:.0f}px;width:{bw:.0f}px;height:{14 * u:.0f}px;border-radius:99px;background:{BLUE};transform-origin:0 50%"></div>')
    reveal(tk, f"#{sid}v", t_from - 0.1, 0.5); rise(tk, f"#{sid}l", t_from + 0.2, 0.4, 12); fade(tk, f"#{sid}b", t_from + 0.2)
    frac0 = start / max(end, 1)
    tk.add(f"tl.fromTo('#{sid}f',{{opacity:1,scaleX:0}},{{opacity:1,scaleX:{frac0:.3f},duration:0.6,ease:'power2.out',immediateRender:false}},{t_from + 0.3:.3f});")
    steps = 24
    for i in range(1, steps + 1):
        v = round(start + (end - start) * (1 - (1 - i / steps) ** 2))
        tk.add(f"tl.set('#{sid}n',{{textContent:'{v}'}},{t_to + i * 1.1 / steps:.3f});")
    tk.add(f"tl.to('#{sid}f',{{scaleX:1,duration:1.1,ease:'power2.out'}},{t_to:.3f});")
    tk.add(f"tl.to('#{sid}l',{{opacity:0,duration:0.15}},{t_to:.3f});tl.set('#{sid}l',{{textContent:'{label_to}'}},{t_to + 0.16:.3f});"
           f"tl.to('#{sid}l',{{opacity:1,duration:0.25}},{t_to + 0.17:.3f});")
    _cam(tk, sid, t0, t_end or t_to + 3)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

# ------------------------------------------------------------------ the model changes, the context does not
def model_slot(tk, sid, box, models, t0, fixed="Your context", t_fixed=None, t_end=None, slot_label="The model"):
    """models: [(name, t)] cycling through one slot (each pushes the last one up and out); the context block lands
    under it on t_fixed and never moves."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []
    sw, sh_ = w * 0.62, 150 * u; sx = x + (w - sw) / 2; sy = y + h * 0.08
    out.append(f'<div class="a sub" id="{sid}ml" style="left:{sx:.0f}px;top:{sy - 46 * u:.0f}px;font-size:{round(28 * u)}px">{slot_label}</div>')
    out.append(f'<div class="a" id="{sid}s" style="left:{sx:.0f}px;top:{sy:.0f}px;width:{sw:.0f}px;height:{sh_:.0f}px;border-radius:{18 * u:.0f}px;overflow:hidden;'
               f'background:#0E1525;border:2px solid rgba(148,163,184,.35)">')
    fs = round(76 * u)
    for i, (name, t) in enumerate(models):
        out.append(f'<div id="{sid}m{i}" style="position:absolute;left:0;top:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;'
                   f'font-family:\'{t_["font"]}\';font-weight:800;font-size:{fs}px;color:{t_["ink"]};opacity:0">{name}</div>')
    out.append('</div>')
    cy_ = sy + sh_ + 70 * u
    out.append(f'<div class="a" id="{sid}c" style="left:{sx:.0f}px;top:{cy_:.0f}px;width:{sw:.0f}px;height:{sh_ * 1.15:.0f}px;border-radius:{18 * u:.0f}px;'
               f'background:{BLUE};display:flex;align-items:center;justify-content:center;font-family:\'{t_["font"]}\';font-weight:800;font-size:{fs}px;color:#fff;'
               f'box-shadow:0 18px 50px rgba(59,130,246,.35);white-space:nowrap"><span style="font-size:{round(min(fs, (sw - 40 * u) / (0.58 * len(fixed))))}px">{fixed}</span></div>')
    fade(tk, f"#{sid}ml", t0 + 0.1); fade(tk, f"#{sid}s", t0 + 0.1, 0.3)
    for i, (name, t) in enumerate(models):
        tk.add(f"tl.fromTo('#{sid}m{i}',{{opacity:0,y:{sh_:.0f}}},{{opacity:1,y:0,duration:0.35,ease:'power3.out',immediateRender:false}},{max(t, tk.ready):.3f});")
        if i + 1 < len(models):
            tk.add(f"tl.to('#{sid}m{i}',{{opacity:0,y:{-sh_:.0f},duration:0.35,ease:'power3.in'}},{max(models[i + 1][1], tk.ready) - 0.05:.3f});")
    if t_fixed is not None: pop(tk, f"#{sid}c", t_fixed, 0.4)
    _cam(tk, sid, t0, t_end or t0 + 6)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

# ------------------------------------------------------------------ the wrapper as a gate
def gate(tk, sid, box, label, passes, blocks, t0, t_end=None):
    """passes/blocks: [(text, t)]. A gate stands in the middle; each chip slides in from the left on its word: a
    pass goes through to the right with a check, a block hits the gate, bounces back and is struck out."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []; gx = x + w * 0.55
    out.append(f'<div class="a" id="{sid}g" style="left:{gx - 8 * u:.0f}px;top:{y + 40 * u:.0f}px;width:{16 * u:.0f}px;height:{h - 80 * u:.0f}px;border-radius:99px;'
               f'background:{BLUE};box-shadow:0 0 30px rgba(59,130,246,.55)"></div>')
    out.append(f'<div class="a lab" id="{sid}gl" style="left:{gx - 200 * u:.0f}px;top:{y:.0f}px;width:{400 * u:.0f}px;text-align:center;font-size:{round(30 * u)}px">{label}</div>')
    rows = [(tx, t, True) for tx, t in passes] + [(tx, t, False) for tx, t in blocks]
    fs = round(46 * u); lh = (h - 120 * u) / max(len(rows), 1)
    for i, (tx, t, ok) in enumerate(rows):
        ry = y + 80 * u + i * lh + lh / 2 - fs; cw = est_w(tx, fs) + 60 * u
        out.append(f'<div class="a" id="{sid}c{i}" style="left:{x:.0f}px;top:{ry:.0f}px;padding:{12 * u:.0f}px {28 * u:.0f}px;border-radius:{14 * u:.0f}px;white-space:nowrap;'
                   f'background:#0E1525;border:2px solid rgba(148,163,184,.4);font-family:\'{t_["font"]}\';font-weight:700;font-size:{fs}px;color:{t_["ink"]}">'
                   + mk_text(tx, f"{sid}k{i}", fs, None if ok else "strike", RED) + '</div>')
        if ok:
            tk.add(f"tl.set('#{sid}c{i}',{{opacity:1}},{t:.3f});tl.fromTo('#{sid}c{i}',{{x:{-60 * u:.0f}}},{{x:{gx - x + 60 * u:.0f},duration:1.0,ease:'power2.inOut',immediateRender:false}},{t:.3f});"
                   f"tl.to('#{sid}c{i}',{{borderColor:'{GREEN}',duration:0.2}},{t + 0.9:.3f});")
        else:
            stop = gx - x - cw - 14 * u
            tk.add(f"tl.set('#{sid}c{i}',{{opacity:1}},{t:.3f});tl.fromTo('#{sid}c{i}',{{x:{-60 * u:.0f}}},{{x:{stop:.0f},duration:0.55,ease:'power2.in',immediateRender:false}},{t:.3f});"
                   f"tl.to('#{sid}c{i}',{{x:{stop - 140 * u:.0f},duration:0.5,ease:'power3.out'}},{t + 0.55:.3f});"
                   f"tl.to('#{sid}c{i}',{{borderColor:'{RED}',duration:0.2}},{t + 0.55:.3f});")
            ink(tk, f"#{sid}k{i}m", t + 0.75, 0.4)
    fade(tk, f"#{sid}g", t0 + 0.1, 0.3); fade(tk, f"#{sid}gl", t0 + 0.2)
    _cam(tk, sid, t0, t_end or t0 + 6)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

# ------------------------------------------------------------------ a pulse line
def pulse(tk, sid, box, title, beats, t0, t_end):
    """beats: [(label, t)]. An ECG trace draws across the box; its spikes are evenly spaced (labels placed by time
    collided when the beats were said close together) and the drawing is paced so it reaches each spike exactly
    on its word, where the label drops in under it."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []; base = y + h * 0.42; amp = h * 0.2; n = len(beats)
    xs = [x + w * (i + 0.5) / n for i in range(n)]
    pts = [f"M{x:.0f} {base:.0f}"]
    for bx in xs:
        pts += [f"L{bx - 30 * u:.0f} {base:.0f}", f"L{bx - 14 * u:.0f} {base + amp * 0.25:.0f}", f"L{bx:.0f} {base - amp:.0f}",
                f"L{bx + 14 * u:.0f} {base + amp * 0.45:.0f}", f"L{bx + 30 * u:.0f} {base:.0f}"]
    pts.append(f"L{x + w:.0f} {base:.0f}")
    out.append(f'<svg class="mark" style="left:0;top:0;width:{tk.W}px;height:{tk.H}px" viewBox="0 0 {tk.W} {tk.H}"><path id="{sid}ecg" pathLength="1" '
               f'stroke-dasharray="1" stroke-dashoffset="1" d="{" ".join(pts)}" stroke="{LIGHT}" stroke-width="5" fill="none" '
               f'style="filter:drop-shadow(0 0 8px rgba(96,165,250,.7))"/></svg>')
    out.append(f'<div class="a hd" id="{sid}t" style="left:{x:.0f}px;top:{y:.0f}px;width:{w:.0f}px;font-size:{round(70 * u)}px">{title}</div>')
    fs = round(30 * u); lw = w / n - 20 * u
    for i, (label, t) in enumerate(beats):
        out.append(f'<div class="a tx" id="{sid}b{i}" style="left:{xs[i] - lw / 2:.0f}px;top:{base + amp * 0.75:.0f}px;width:{lw:.0f}px;'
                   f'text-align:center;font-size:{fs}px">{label}</div>')
        rise(tk, f"#{sid}b{i}", t + 0.05, 0.35, -14)
    reveal(tk, f"#{sid}t", t0 + 0.1)
    # the trace is mostly horizontal: path fraction ~ x fraction. Keyframes: start, each spike on its beat, the end.
    keys = [(t0, 0.0)] + [(t, (bx - x) / w) for (_, t), bx in zip(beats, xs)] + [(max(t_end, beats[-1][1] + 0.5), 1.0)]
    for (ta, fa), (tb, fb) in zip(keys, keys[1:]):
        if tb <= ta: continue
        tk.add(f"tl.fromTo('#{sid}ecg',{{attr:{{'stroke-dashoffset':{1 - fa:.4f}}}}},{{attr:{{'stroke-dashoffset':{1 - fb:.4f}}},duration:{tb - ta:.3f},ease:'none',immediateRender:false}},{ta:.3f});")
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

# ------------------------------------------------------------------ evals as a test run
def test_runner(tk, sid, box, title, rows, t0, t_end=None):
    """rows: [(label, t)]: every row starts spinning when the scene opens and flips to PASS on its word; the tally
    lands after the last one. No timings or numbers that were not said."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []; fs = round(44 * u); lh = round(fs * 1.9); top = y + round(120 * u)
    out.append(f'<div class="a" id="{sid}p" style="left:{x:.0f}px;top:{y:.0f}px;width:{w:.0f}px;height:{min(h, top - y + lh * len(rows) + 120 * u):.0f}px;'
               f'border-radius:{18 * u:.0f}px;background:#0D1117;border:2px solid rgba(148,163,184,.24)"></div>')
    out.append(f'<div class="a mono" id="{sid}t" style="left:{x + 40 * u:.0f}px;top:{y + 36 * u:.0f}px;font-size:{round(32 * u)}px;color:{LIGHT}">$ {title}</div>')
    spin = "|/-\\"   # a CLI spinner, written through json.dumps
    for i, (label, t) in enumerate(rows):
        ry = top + i * lh
        out.append(f'<div class="a mono" id="{sid}s{i}" style="left:{x + 40 * u:.0f}px;top:{ry:.0f}px;font-size:{fs}px;color:{t_["ink2"]}">|</div>')
        out.append(f'<div class="a mono" id="{sid}k{i}" style="left:{x + 40 * u:.0f}px;top:{ry:.0f}px;font-size:{fs * 0.8:.0f}px;padding:2px 12px;border-radius:8px;'
                   f'background:{GREEN};color:#0D1117;font-weight:700">PASS</div>')
        out.append(f'<div class="a tx" id="{sid}r{i}" style="left:{x + 40 * u + fs * 3.4:.0f}px;top:{ry:.0f}px;font-size:{fs}px">{label}</div>')
        tstart = t0 + 0.4 + 0.08 * i; fade(tk, f"#{sid}s{i}", tstart, 0.15); fade(tk, f"#{sid}r{i}", tstart, 0.25)
        k = 0; tt = tstart
        while tt < t - 0.05:
            tk.add(f"tl.set('#{sid}s{i}',{{textContent:{json.dumps(spin[k % len(spin)])}}},{tt:.3f});"); tt += 0.12; k += 1
        tk.add(f"tl.set('#{sid}s{i}',{{opacity:0}},{t:.3f});"); pop(tk, f"#{sid}k{i}", t, 0.25)
    out.append(f'<div class="a mono" id="{sid}sum" style="left:{x + 40 * u:.0f}px;top:{top + len(rows) * lh + 10 * u:.0f}px;font-size:{round(34 * u)}px;color:{GREEN}">'
               f'{len(rows)} passed</div>')
    fade(tk, f"#{sid}p", t0 + 0.05, 0.3); fade(tk, f"#{sid}t", t0 + 0.2)
    rise(tk, f"#{sid}sum", rows[-1][1] + 0.5, 0.35, 10)
    _cam(tk, sid, t0, t_end or rows[-1][1] + 2.5)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

# ================================================================== denser motion from the first seconds
def kinetic(tk, sid, box, text, t_after, accent=(), fs=110, sub=None, t_sub=None, t_end=None):
    """Kinetic type: each word of `text` pops in on the moment it is SPOKEN (looked up in the transcript after
    t_after), accent words in light blue. text must be the speaker's own words, in order."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; fs = round(min(fs * u, w / 7)); out = []
    words = text.split(); times = []; cur = t_after
    for wd in words:
        try: tt = tk.at(wd, after=cur)
        except KeyError: tt = cur + 0.25
        if tt - cur > 4: tt = cur + 0.25                              # a word not said nearby: keep the rhythm
        times.append(tt); cur = tt + 0.01
    nl = max(1, math.ceil(sum(est_w(wd + " ", fs) * 0.92 for wd in words) / w))
    lh = fs * 1.12; top = y + max(0, (h - lh * nl - (fs * 0.7 if sub else 0)) * 0.42)
    acc = {a.lower().strip(".,?!") for a in accent}; spans = []
    for wi, (wd, tt) in enumerate(zip(words, times)):
        wid = f"{sid}w{wi}"; isacc = wd.lower().strip(".,?!") in acc
        spans.append(f'<span id="{wid}" style="display:inline-block;opacity:0;margin-right:0.24em;color:{LIGHT if isacc else t_["ink"]}">{wd}</span>')
        tk.add(f"tl.fromTo('#{wid}',{{opacity:0,y:{fs * 0.35:.0f},scale:1.18}},{{opacity:1,y:0,scale:1,duration:0.32,ease:'back.out(2)',immediateRender:false}},{max(tt - 0.04, tk.ready):.3f});")
    out.append(f'<div class="hd" style="position:absolute;left:{x}px;top:{top:.0f}px;width:{w}px;font-size:{fs}px;line-height:1.12">{"".join(spans)}</div>')
    lines = [None] * nl
    if sub:
        sy = top + lh * len(lines) + fs * 0.25
        out.append(f'<div class="a sub" id="{sid}s" style="left:{x}px;top:{sy:.0f}px;width:{w}px;font-size:{round(fs * 0.38)}px">{sub}</div>')
        rise(tk, f"#{sid}s", t_sub or times[-1] + 0.4, 0.4, 10)
    _cam(tk, sid, times[0], t_end or times[-1] + 2, 1.05)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

def face_pop(tk, sid, lines, t_in, t_out, side="left", accent_line=None):
    """Big words beside the face in a FACE shot (the bookshelf side) on a soft dark fade: an editor's punch-in text.
    lines: [str] stacked; accent_line: index shown in light blue. Returns HTML for the overlay layer (z 44-45: above #full,
    below the captions). Use only while the layout is FACE."""
    W, H = tk.W, tk.H; t_ = tk.T; fs = 108; pad = 56; lw = 610
    while fs > 60 and max(est_w(l, fs) for l in lines) > lw: fs -= 4          # the longest line fits the bookshelf side
    x = pad if side == "left" else W - pad - lw
    grad = ("linear-gradient(to right,rgba(7,9,15,.82) 0%,rgba(7,9,15,.55) 60%,rgba(7,9,15,0) 100%)" if side == "left"
            else "linear-gradient(to left,rgba(7,9,15,.82) 0%,rgba(7,9,15,.55) 60%,rgba(7,9,15,0) 100%)")
    gx = 0 if side == "left" else W - 760
    out = [f'<div id="{sid}bg" style="position:absolute;left:{gx}px;top:0;width:760px;height:{H}px;z-index:44;opacity:0;background:{grad}"></div>']
    ty = H / 2 - len(lines) * fs * 0.6
    for i, ln in enumerate(lines):
        out.append(f'<div id="{sid}l{i}" style="position:absolute;left:{x}px;top:{ty + i * fs * 1.08:.0f}px;width:{lw}px;z-index:45;opacity:0;'
                   f'font-family:\'{t_["font"]}\';font-weight:800;font-size:{fs}px;line-height:1.02;letter-spacing:-0.03em;white-space:nowrap;'
                   f'color:{LIGHT if i == accent_line else "#FFFFFF"};text-align:{"left" if side == "left" else "right"};'
                   f'text-shadow:0 6px 30px rgba(0,0,0,.6)">{ln}</div>')
    tk.add(f"tl.fromTo('#{sid}bg',{{opacity:0}},{{opacity:1,duration:0.3,immediateRender:false}},{t_in - 0.1:.3f});"
           f"tl.to('#{sid}bg',{{opacity:0,duration:0.3}},{t_out:.3f});")
    dx = -60 if side == "left" else 60
    for i in range(len(lines)):
        tk.add(f"tl.fromTo('#{sid}l{i}',{{opacity:0,x:{dx}}},{{opacity:1,x:0,duration:0.4,ease:'power3.out',immediateRender:false}},{t_in + i * 0.12:.3f});"
               f"tl.to('#{sid}l{i}',{{opacity:0,x:{dx / 2},duration:0.25}},{t_out:.3f});")
    return "".join(out)

def face_shake(tk, sid, word, t_in, t_out, side="left"):
    """One word beside the face that lands with a shake (chaos, overcomplication)."""
    html = face_pop(tk, sid, [word], t_in, t_out, side)
    for k, dx in enumerate((14, -12, 9, -6, 3, 0)):
        tk.add(f"tl.to('#{sid}l0',{{x:{dx},duration:0.05}},{t_in + 0.42 + k * 0.05:.3f});")
    return html

def window_grid(tk, sid, box, items, t0, prompt=None, t_prompt=None, t_end=None):
    """Mini app windows opening one per spoken job, each with its own motion (shapes only, no fake text).
    items: [(title, kind, t)], kind = feed | doc | diagram | code. prompt: an input bar typing at t_prompt."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []; gap = 26 * u
    ph = (56 * u + 20 * u) if prompt else 0
    cw, ch = (w - gap) / 2, (h - gap - ph) / 2
    for i, (title, kind, t) in enumerate(items):
        wx, wy = x + (i % 2) * (cw + gap), y + (i // 2) * (ch + gap); wid = f"{sid}g{i}"
        body = []; bx, by, bw, bh = 24 * u, 70 * u, cw - 48 * u, ch - 94 * u
        if kind == "feed":
            for r in range(6):
                body.append(f'<div id="{wid}r{r}" style="position:absolute;left:{bx:.0f}px;top:{by + r * bh / 4:.0f}px;width:{bw * (0.95 - 0.12 * (r % 3)):.0f}px;'
                            f'height:{bh / 9:.0f}px;border-radius:6px;background:rgba(148,163,184,{.35 if r % 3 else .6})"></div>')
                tk.add(f"tl.fromTo('#{wid}r{r}',{{y:{bh / 3:.0f}}},{{y:{-bh:.0f},duration:3.2,ease:'none',immediateRender:false}},{t + 0.2 + r * 0.25:.3f});")
        elif kind == "doc":
            for r in range(5):
                body.append(f'<div id="{wid}r{r}" style="position:absolute;left:{bx:.0f}px;top:{by + r * bh / 5:.0f}px;width:{bw * (0.92 if r % 4 else 0.6):.0f}px;'
                            f'height:{bh / 10:.0f}px;border-radius:6px;background:{"rgba(96,165,250,.8)" if r == 0 else "rgba(148,163,184,.45)"};transform-origin:0 50%"></div>')
                tk.add(f"tl.fromTo('#{wid}r{r}',{{scaleX:0}},{{scaleX:1,duration:0.5,ease:'power2.out',immediateRender:false}},{t + 0.25 + r * 0.32:.3f});")
        elif kind == "diagram":
            pts = [(bx + bw * 0.15, by + bh * 0.25), (bx + bw * 0.8, by + bh * 0.25), (bx + bw * 0.48, by + bh * 0.8)]
            nw_, nh_ = bw * 0.26, bh * 0.26
            sv = "".join(f'<path id="{wid}e{k}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1" d="M{pts[a][0]:.0f} {pts[a][1]:.0f} L{pts[b][0]:.0f} {pts[b][1]:.0f}" stroke="{LIGHT}" stroke-width="3" fill="none"/>'
                         for k, (a, b) in enumerate(((0, 1), (1, 2), (2, 0))))
            body.append(f'<svg style="position:absolute;left:0;top:0;width:{cw:.0f}px;height:{ch:.0f}px;overflow:visible" viewBox="0 0 {cw:.0f} {ch:.0f}">{sv}</svg>')
            for k, (px, py) in enumerate(pts):
                body.append(f'<div id="{wid}n{k}" style="position:absolute;left:{px - nw_ / 2:.0f}px;top:{py - nh_ / 2:.0f}px;width:{nw_:.0f}px;height:{nh_:.0f}px;border-radius:10px;'
                            f'background:#13203B;border:2px solid {LIGHT};opacity:0"></div>')
                tk.add(f"tl.fromTo('#{wid}n{k}',{{opacity:0,scale:0.6}},{{opacity:1,scale:1,duration:0.3,ease:'back.out(2)',immediateRender:false}},{t + 0.2 + k * 0.25:.3f});")
            for k in range(3):
                tk.add(f"tl.fromTo('#{wid}e{k}',{{attr:{{'stroke-dashoffset':1}}}},{{attr:{{'stroke-dashoffset':0}},duration:0.35,immediateRender:false}},{t + 0.95 + k * 0.25:.3f});")
        else:   # code
            for r in range(5):
                body.append(f'<div id="{wid}r{r}" style="position:absolute;left:{bx + (0 if r % 2 == 0 else 28 * u):.0f}px;top:{by + r * bh / 5:.0f}px;width:{bw * (0.5 + 0.08 * (r % 3)):.0f}px;'
                            f'height:{bh / 10:.0f}px;border-radius:4px;background:{GREEN if r == 4 else ("rgba(96,165,250,.7)" if r % 2 == 0 else "rgba(148,163,184,.4)")};transform-origin:0 50%"></div>')
                tk.add(f"tl.fromTo('#{wid}r{r}',{{scaleX:0}},{{scaleX:1,duration:0.25,ease:'none',immediateRender:false}},{t + 0.3 + r * 0.38:.3f});")
        hdr = (f'<div style="position:absolute;left:0;top:0;right:0;height:{52 * u:.0f}px;display:flex;align-items:center;gap:{8 * u:.0f}px;padding:0 {20 * u:.0f}px;'
               f'border-bottom:1px solid rgba(148,163,184,.18)">' + "".join(f'<span style="width:{11 * u:.0f}px;height:{11 * u:.0f}px;border-radius:50%;background:{c}"></span>' for c in ("#F87171", "#FBBF24", "#34D399"))
               + f'<span style="margin-left:{10 * u:.0f}px;font-family:\'{t_["font"]}\';font-weight:700;font-size:{round(24 * u)}px;color:{t_["ink"]}">{title}</span></div>')
        out.append(f'<div class="a" id="{wid}" style="left:{wx:.0f}px;top:{wy:.0f}px;width:{cw:.0f}px;height:{ch:.0f}px;border-radius:{16 * u:.0f}px;overflow:hidden;'
                   f'background:#0D1117;border:2px solid rgba(148,163,184,.24);box-shadow:0 14px 40px rgba(0,0,0,.45)">{hdr}{"".join(body)}</div>')
        tk.add(f"tl.fromTo('#{wid}',{{opacity:0,scale:0.85,y:{30 * u:.0f}}},{{opacity:1,scale:1,y:0,duration:0.4,ease:'back.out(1.6)',immediateRender:false}},{max(t - 0.05, tk.ready):.3f});")
    if prompt:
        py = y + h - 56 * u; fs = round(28 * u)
        out.append(f'<div class="a" id="{sid}pb" style="left:{x + w * 0.1:.0f}px;top:{py:.0f}px;width:{w * 0.8:.0f}px;height:{56 * u:.0f}px;border-radius:99px;background:#0E1525;'
                   f'border:2px solid {BLUE};box-shadow:0 0 30px rgba(59,130,246,.35);display:flex;align-items:center;padding:0 {28 * u:.0f}px">'
                   f'<span class="mono" id="{sid}pt" style="font-size:{fs}px;color:{t_["ink"]}"></span></div>')
        tk.add(f"tl.fromTo('#{sid}pb',{{opacity:0,y:{40 * u:.0f}}},{{opacity:1,y:0,duration:0.4,ease:'power3.out',immediateRender:false}},{t_prompt - 0.3:.3f});")
        S.typeon(tk, f"#{sid}pt", prompt, t_prompt, 30)
    _cam(tk, sid, t0, t_end or t0 + 12, 1.03)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

def foundation(tk, sid, box, title, t_title, t_blocks, build, t_build, audit, t_audit, t_scan, t_end=None):
    """Four blank blocks drop and lock into a foundation; 'build' and 'audit' lines land on their words; on t_scan a
    scanner sweeps the blocks and checks each one."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []
    fs = round(min(84 * u, w / 11)); out.append(f'<div class="a hd" id="{sid}t" style="left:{x}px;top:{y}px;width:{w}px;font-size:{fs}px">{title}</div>')
    reveal(tk, f"#{sid}t", t_title)
    bw = w * 0.52; bx = x + w - bw; by = y + h * 0.25; bh = h * 0.6; cw, chh = (bw - 20 * u) / 2, (bh - 20 * u) / 2
    for i in range(4):
        cx, cy = bx + (i % 2) * (cw + 20 * u), by + (1 - i // 2) * (chh + 20 * u)
        out.append(f'<div class="a" id="{sid}b{i}" style="left:{cx:.0f}px;top:{cy:.0f}px;width:{cw:.0f}px;height:{chh:.0f}px;border-radius:{14 * u:.0f}px;'
                   f'background:linear-gradient(160deg,#1B3A7A,#0E1F45);border:2px solid rgba(96,165,250,.7);box-shadow:0 12px 30px rgba(0,0,0,.45)"></div>')
        out.append(f'<div class="a" id="{sid}c{i}" style="left:{cx + cw / 2 - 30 * u:.0f}px;top:{cy + chh / 2 - 30 * u:.0f}px;width:{60 * u:.0f}px;height:{60 * u:.0f}px;'
                   f'border-radius:50%;background:{GREEN};color:#07090F;display:flex;align-items:center;justify-content:center;font-family:\'{t_["font"]}\';font-weight:900;font-size:{round(40 * u)}px">&#10003;</div>')
        tb = t_blocks + 0.18 * i
        tk.add(f"tl.fromTo('#{sid}b{i}',{{opacity:0,y:{-h * 0.6:.0f}}},{{opacity:1,y:0,duration:0.55,ease:'bounce.out',immediateRender:false}},{max(tb, tk.ready):.3f});")
        pop(tk, f"#{sid}c{i}", t_scan + 0.3 + 0.25 * i, 0.3)
    ly = y + h * 0.32; fl = round(min(60 * u, (w - bw) / 8))
    out.append(f'<div class="a hd" id="{sid}l0" style="left:{x}px;top:{ly:.0f}px;width:{w - bw - 40 * u:.0f}px;font-size:{fl}px">{build}</div>')
    out.append(f'<div class="a hd" id="{sid}l1" style="left:{x}px;top:{ly + fl * 2.6:.0f}px;width:{w - bw - 40 * u:.0f}px;font-size:{fl}px;color:{LIGHT}">{audit}</div>')
    rise(tk, f"#{sid}l0", t_build, 0.4); rise(tk, f"#{sid}l1", t_audit, 0.4)
    out.append(f'<div class="a" id="{sid}sc" style="left:{bx - 10 * u:.0f}px;top:{by - 10 * u:.0f}px;width:{8 * u:.0f}px;height:{bh + 20 * u:.0f}px;border-radius:99px;'
               f'background:{GREEN};box-shadow:0 0 30px 8px rgba(52,211,153,.55)"></div>')
    tk.add(f"tl.set('#{sid}sc',{{opacity:1}},{t_scan:.3f});tl.fromTo('#{sid}sc',{{x:0}},{{x:{bw + 12 * u:.0f},duration:1.2,ease:'power1.inOut',immediateRender:false}},{t_scan:.3f});"
           f"tl.to('#{sid}sc',{{opacity:0,duration:0.2}},{t_scan + 1.2:.3f});")
    _cam(tk, sid, t_title, t_end or t_scan + 3, 1.03)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

def tiles(tk, sid, box, n, t0, t_count, label, t_label):
    """A count rolling 1..n while n tiles pop in a row ('only four components')."""
    x, y, w, h = box; u = unit(box); out = []; fv = round(min(260 * u, h * 0.42))
    out.append(f'<div class="a hd" id="{sid}v" style="left:{x}px;top:{y + h * 0.05:.0f}px;width:{w * 0.3:.0f}px;font-size:{fv}px;color:{LIGHT};text-align:center">'
               f'<span id="{sid}n">1</span></div>')
    tw = (w * 0.66 - (n - 1) * 20 * u) / n; tx0 = x + w * 0.34
    for i in range(n):
        out.append(f'<div class="a" id="{sid}k{i}" style="left:{tx0 + i * (tw + 20 * u):.0f}px;top:{y + h * 0.1:.0f}px;width:{tw:.0f}px;height:{h * 0.42:.0f}px;border-radius:{16 * u:.0f}px;'
                   f'background:linear-gradient(160deg,#1B3A7A,#0E1F45);border:2px solid rgba(96,165,250,.7)"></div>')
        tt = t_count + i * 0.22
        tk.add(f"tl.fromTo('#{sid}k{i}',{{opacity:0,scale:0.5,y:{40 * u:.0f}}},{{opacity:1,scale:1,y:0,duration:0.4,ease:'back.out(2)',immediateRender:false}},{max(tt, tk.ready):.3f});"
               f"tl.set('#{sid}n',{{textContent:'{i + 1}'}},{tt:.3f});")
    fade(tk, f"#{sid}v", t_count - 0.05, 0.15)
    out.append(f'<div class="a hd" id="{sid}l" style="left:{x}px;top:{y + h * 0.66:.0f}px;width:{w}px;font-size:{round(min(70 * u, w / 14))}px">{label}</div>')
    reveal(tk, f"#{sid}l", t_label)
    _cam(tk, sid, t0, t_label + 4, 1.03)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

def converge(tk, sid, box, items, center, t_merge, t0, t_end=None, mono=True):
    """Chips land round the box on their words, then all fly into the centre and become one block (many -> one)."""
    x, y, w, h = box; u = unit(box); out = []; cx, cy = x + w / 2, y + h / 2; n = len(items)
    fs = round(46 * u)
    for i, (label, t) in enumerate(items):
        a = math.radians(-150 + i * (300 / max(n - 1, 1))) if n > 1 else 0
        px, py = cx + w * 0.34 * math.cos(a), cy + h * 0.32 * math.sin(a)
        cw = est_w(label, fs, mono) + 60 * u
        out.append(f'<div class="a {"mono" if mono else "tx"}" id="{sid}i{i}" style="left:{px - cw / 2:.0f}px;top:{py - fs:.0f}px;width:{cw:.0f}px;height:{fs * 2:.0f}px;display:flex;'
                   f'align-items:center;justify-content:center;font-size:{fs}px;border-radius:14px;background:#0E1525;border:2px solid rgba(148,163,184,.45)">{label}</div>')
        pop(tk, f"#{sid}i{i}", t, 0.3)
        tk.add(f"tl.to('#{sid}i{i}',{{x:{cx - px:.0f},y:{cy - py:.0f},scale:0.4,opacity:0,duration:0.6,ease:'power3.in'}},{t_merge + i * 0.05:.3f});")
    cfs = round(min(72 * u, w / 12)); cw = est_w(center, cfs) + 100 * u
    out.append(f'<div class="a hd" id="{sid}c" style="left:{cx - cw / 2:.0f}px;top:{cy - cfs:.0f}px;width:{cw:.0f}px;height:{cfs * 2:.0f}px;display:flex;align-items:center;'
               f'justify-content:center;font-size:{cfs}px;color:#fff;border-radius:18px;background:{BLUE};box-shadow:0 0 50px rgba(59,130,246,.55)">{center}</div>')
    tk.add(f"tl.fromTo('#{sid}c',{{opacity:0,scale:0.3}},{{opacity:1,scale:1,duration:0.5,ease:'back.out(2)',immediateRender:false}},{t_merge + 0.5:.3f});")
    _cam(tk, sid, t0, t_end or t_merge + 3, 1.04)
    return _wrap(sid, "".join(out), cx, cy)

def declutter(tk, sid, box, pile, keep, t0, t_drop, folder, files, t_folder, t_end=None):
    """A pile of tool chips; on t_drop everything not in keep falls away and the keepers slide into a row; on t_folder
    a folder card lands with its markdown files fanning out ('a few tools and a folder of markdown files')."""
    x, y, w, h = box; u = unit(box); out = []; fs = round(32 * u)
    cols = 4; cw = (w - 3 * 16 * u) / cols; fs = round(min(fs, (cw - 20 * u) / (0.6 * max(len(p) for p in pile)))); rh = max(fs * 2.2, 44 * u)
    for i, label in enumerate(pile):
        px, py = x + (i % cols) * (cw + 16 * u), y + (i // cols) * (rh + 14 * u)
        kept = label in keep
        out.append(f'<div class="a mono" id="{sid}p{i}" style="left:{px:.0f}px;top:{py:.0f}px;width:{cw:.0f}px;height:{rh:.0f}px;display:flex;align-items:center;'
                   f'justify-content:center;font-size:{fs}px;border-radius:12px;background:#0E1525;border:2px solid {"rgba(96,165,250,.8)" if kept else "rgba(148,163,184,.35)"}">{label}</div>')
        tk.add(f"tl.fromTo('#{sid}p{i}',{{opacity:0,scale:0.7}},{{opacity:1,scale:1,duration:0.25,ease:'back.out(2)',immediateRender:false}},{max(t0 + 0.2 + i * 0.07, tk.ready):.3f});")
        if not kept:
            tk.add(f"tl.to('#{sid}p{i}',{{y:{h:.0f},rotation:{(-1) ** i * (12 + i % 5 * 4)},opacity:0,duration:0.7,ease:'power2.in'}},{t_drop + (i % 5) * 0.04:.3f});")
        else:
            k = keep.index(label); tx, ty = x + k * (cw + 16 * u), y
            tk.add(f"tl.to('#{sid}p{i}',{{x:{tx - px:.0f},y:{ty - py:.0f},duration:0.6,ease:'power3.inOut'}},{t_drop + 0.4:.3f});")
    fx, fy, fw, fh = x + w * 0.18, y + rh * 1.9, w * 0.64, h - rh * 1.9
    out.append(f'<div class="a" id="{sid}f" style="left:{fx:.0f}px;top:{fy:.0f}px;width:{fw:.0f}px;height:{fh:.0f}px;border-radius:{18 * u:.0f}px;'
               f'background:linear-gradient(170deg,#1D3B7C,#0E1F45);border:2px solid {LIGHT};box-shadow:0 20px 50px rgba(0,0,0,.5)"></div>')
    out.append(f'<div class="a hd" id="{sid}ft" style="left:{fx + 28 * u:.0f}px;top:{fy + 18 * u:.0f}px;font-size:{round(40 * u)}px">{folder}</div>')
    tk.add(f"tl.fromTo('#{sid}f',{{opacity:0,y:{80 * u:.0f}}},{{opacity:1,y:0,duration:0.45,ease:'power3.out',immediateRender:false}},{t_folder - 0.1:.3f});")
    fade(tk, f"#{sid}ft", t_folder + 0.15)
    n = len(files); dw = fw * 0.28; dh = fh * 0.5; ffs = round(min(24 * u, (dw - 16 * u) / (0.6 * max(len(f) for f in files))))
    for i, name in enumerate(files):
        dx = fx + fw / 2 - dw / 2 + (i - (n - 1) / 2) * dw * 0.62; dy = fy + fh * 0.38
        out.append(f'<div class="a mono" id="{sid}d{i}" style="left:{dx:.0f}px;top:{dy:.0f}px;width:{dw:.0f}px;height:{dh:.0f}px;border-radius:10px;background:#F5F7FB;'
                   f'color:#0E1525;display:flex;align-items:flex-start;justify-content:center;padding-top:{18 * u:.0f}px;box-sizing:border-box;font-size:{ffs}px;'
                   f'font-weight:700;box-shadow:0 10px 24px rgba(0,0,0,.45)">{name}</div>')
        tk.add(f"tl.fromTo('#{sid}d{i}',{{opacity:0,y:{dh * 0.6:.0f},rotation:0}},{{opacity:1,y:0,rotation:{(i - (n - 1) / 2) * 7:.1f},duration:0.5,ease:'back.out(1.8)',immediateRender:false}},{t_folder + 0.35 + i * 0.12:.3f});")
    _cam(tk, sid, t0, t_end or t_folder + 4, 1.03)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

def bars(tk, sid, box, rows, t0, accent=None, t_accent=None, title=None, t_title=None, t_end=None):
    """Bars that grow then shrink on their words: rows [(label, t_in, frac_in, t_shrink, frac_out)]; accent line with a loop mark."""
    x, y, w, h = box; u = unit(box); out = []; fs = round(44 * u); top = y
    if title:
        tf = round(min(80 * u, w / 12)); out.append(f'<div class="a hd" id="{sid}t" style="left:{x}px;top:{y}px;width:{w}px;font-size:{tf}px">{title}</div>')
        reveal(tk, f"#{sid}t", t_title or t0 + 0.2); top = y + tf * 1.6
    bw = w * 0.62; bx = x + w - bw
    for i, (label, ti, fi, ts, fo) in enumerate(rows):
        ry = top + i * fs * 2.6
        out.append(f'<div class="a tx" id="{sid}l{i}" style="left:{x}px;top:{ry:.0f}px;width:{w - bw - 20 * u:.0f}px;font-size:{fs}px">{label}</div>')
        out.append(f'<div class="a" id="{sid}b{i}" style="left:{bx:.0f}px;top:{ry + fs * 0.1:.0f}px;width:{bw:.0f}px;height:{fs * 1.0:.0f}px;border-radius:10px;'
                   f'background:linear-gradient(90deg,{BLUE},{LIGHT});transform-origin:0 50%"></div>')
        rise(tk, f"#{sid}l{i}", ti, 0.35, 10)
        tk.add(f"tl.fromTo('#{sid}b{i}',{{opacity:1,scaleX:0}},{{opacity:1,scaleX:{fi},duration:0.6,ease:'power2.out',immediateRender:false}},{max(ti, tk.ready):.3f});"
               f"tl.to('#{sid}b{i}',{{scaleX:{fo},duration:0.7,ease:'power3.inOut'}},{ts:.3f});")
    if accent:
        ay = top + len(rows) * fs * 2.6 + 20 * u; af = round(min(72 * u, w / 13))
        out.append(f'<div class="a hd" id="{sid}a" style="left:{x}px;top:{ay:.0f}px;width:{w}px;font-size:{af}px;color:{LIGHT}">&#10227; {accent}</div>')
        tk.add(f"tl.fromTo('#{sid}a',{{opacity:0,scale:0.8}},{{opacity:1,scale:1,duration:0.45,ease:'back.out(2)',immediateRender:false}},{t_accent:.3f});")
    _cam(tk, sid, t0, t_end or (t_accent or t0) + 3, 1.03)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

def stack_tower(tk, sid, box, layers, title, t_title, t_end=None):
    """Blocks dropping onto a pile, bottom first: layers [(label, sub, t)] (layers[0] is the bottom)."""
    x, y, w, h = box; u = unit(box); out = []; tf = round(min(76 * u, w / 12))
    out.append(f'<div class="a hd" id="{sid}t" style="left:{x}px;top:{y}px;width:{w * 0.4:.0f}px;font-size:{tf}px">{title}</div>')
    reveal(tk, f"#{sid}t", t_title)
    n = len(layers); bw = w * 0.56; bx = x + w - bw; bh = (h - (n - 1) * 10 * u) / n; fs = round(min(40 * u, bh * 0.42))
    for i, (label, sub, t) in enumerate(layers):
        by = y + h - (i + 1) * bh - i * 10 * u
        shade = ["#0E1F45", "#13295A", "#18336D", "#1D3D80", "#234794", "#2A52A8"][i % 6]
        out.append(f'<div class="a" id="{sid}b{i}" style="left:{bx:.0f}px;top:{by:.0f}px;width:{bw:.0f}px;height:{bh:.0f}px;border-radius:{12 * u:.0f}px;background:{shade};'
                   f'border:2px solid rgba(96,165,250,.7);display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:{4 * u:.0f}px;'
                   f'padding:0 {26 * u:.0f}px;box-sizing:border-box">'
                   f'<span class="hd" style="font-size:{fs}px;line-height:1">{label}</span>'
                   + (f'<span class="sub" style="font-size:{round(fs * 0.6)}px;line-height:1.1;white-space:nowrap">{sub}</span>' if sub else "") + '</div>')
        tk.add(f"tl.fromTo('#{sid}b{i}',{{opacity:0,y:{-h:.0f}}},{{opacity:1,y:0,duration:0.6,ease:'bounce.out',immediateRender:false}},{max(t, tk.ready):.3f});")
    _cam(tk, sid, t_title, t_end or layers[-1][2] + 3, 1.03)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

def chat(tk, sid, box, msgs, t0, t_end=None):
    """Chat bubbles: msgs [(who, text, t)], who = 'me' (right, blue) | 'ai' (left, grey)."""
    x, y, w, h = box; u = unit(box); t_ = tk.T; out = []; fs = round(min(44 * u, w / 22)); yy = y + 10 * u
    for i, (who, text, t) in enumerate(msgs):
        bw = min(w * 0.7, est_w(text, fs) + 70 * u); bh = fs * 2.0; me = who == "me"
        bx = x + w - bw if me else x
        out.append(f'<div class="a" id="{sid}m{i}" style="left:{bx:.0f}px;top:{yy:.0f}px;width:{bw:.0f}px;height:{bh:.0f}px;border-radius:{26 * u:.0f}px;'
                   f'{"border-bottom-right-radius" if me else "border-bottom-left-radius"}:6px;background:{BLUE if me else "#1A2236"};display:flex;align-items:center;'
                   f'padding:0 {32 * u:.0f}px;box-sizing:border-box;font-family:\'{t_["font"]}\';font-weight:700;font-size:{fs}px;color:#fff;white-space:nowrap">{text}</div>')
        tk.add(f"tl.fromTo('#{sid}m{i}',{{opacity:0,y:{30 * u:.0f},scale:0.9}},{{opacity:1,y:0,scale:1,duration:0.35,ease:'back.out(2)',immediateRender:false}},{max(t - 0.05, tk.ready):.3f});")
        yy += bh + 26 * u
    _cam(tk, sid, t0, t_end or msgs[-1][2] + 3, 1.03)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

def steps(tk, sid, box, items, t0, title=None, t_title=None, t_end=None):
    """A path with a node per step; a glowing dot travels to each node on its word and lights it."""
    x, y, w, h = box; u = unit(box); out = []; n = len(items); top = y
    if title:
        tf = round(min(76 * u, w / 12)); out.append(f'<div class="a hd" id="{sid}t" style="left:{x}px;top:{y}px;width:{w}px;font-size:{tf}px">{title}</div>')
        reveal(tk, f"#{sid}t", t_title or t0 + 0.2); top = y + tf * 1.4
    ly = top + (y + h - top) * 0.38; xs = [x + w * (i + 0.5) / n for i in range(n)]
    out.append(f'<svg class="mark" style="left:0;top:0;width:{tk.W}px;height:{tk.H}px" viewBox="0 0 {tk.W} {tk.H}"><path id="{sid}ln" pathLength="1" stroke-dasharray="1" '
               f'stroke-dashoffset="1" d="M{xs[0]:.0f} {ly:.0f} L{xs[-1]:.0f} {ly:.0f}" stroke="rgba(148,163,184,.5)" stroke-width="4" fill="none"/></svg>')
    tk.add(f"tl.fromTo('#{sid}ln',{{attr:{{'stroke-dashoffset':1}}}},{{attr:{{'stroke-dashoffset':0}},duration:0.7,ease:'power2.out',immediateRender:false}},{t0 + 0.2:.3f});")
    r = 30 * u; fs = round(min(44 * u, w / n / 7.5))
    for i, (label, t) in enumerate(items):
        out.append(f'<div class="a" id="{sid}n{i}" style="left:{xs[i] - r:.0f}px;top:{ly - r:.0f}px;width:{2 * r:.0f}px;height:{2 * r:.0f}px;border-radius:50%;'
                   f'background:#0E1525;border:3px solid rgba(148,163,184,.6)"></div>')
        out.append(f'<div class="a tx" id="{sid}l{i}" style="left:{xs[i] - w / n / 2 + 8 * u:.0f}px;top:{ly + r + 24 * u:.0f}px;width:{w / n - 16 * u:.0f}px;text-align:center;font-size:{fs}px">{label}</div>')
        fade(tk, f"#{sid}n{i}", t0 + 0.3 + 0.1 * i, 0.2)
        tk.add(f"tl.to('#{sid}n{i}',{{backgroundColor:'{BLUE}',borderColor:'{LIGHT}',scale:1.25,duration:0.3,ease:'back.out(3)'}},{max(t, tk.ready):.3f});")
        rise(tk, f"#{sid}l{i}", t, 0.35, -12)
    out.append(_dot(f"{sid}d", 12))
    for i, (label, t) in enumerate(items):
        x0 = xs[i - 1] if i else xs[0]
        tk.add(f"tl.fromTo('#{sid}d',{{x:{x0:.0f},y:{ly:.0f},opacity:1}},{{x:{xs[i]:.0f},y:{ly:.0f},opacity:1,duration:0.45,ease:'power2.inOut',immediateRender:false}},{max(t - 0.45, tk.ready):.3f});")
    _cam(tk, sid, t0, t_end or items[-1][1] + 3, 1.03)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)

def palette(tk, sid, box, commands, t0, sub=None, t_sub=None, t_end=None):
    """A command palette: each command types into the bar on its word ([(text, t)])."""
    x, y, w, h = box; u = unit(box); out = []; fs = round(min(64 * u, w / 14)); bh = fs * 2.0
    out.append(f'<div class="a" id="{sid}b" style="left:{x}px;top:{y + h * 0.18:.0f}px;width:{w}px;height:{bh:.0f}px;border-radius:{20 * u:.0f}px;background:#0D1117;'
               f'border:2px solid {BLUE};box-shadow:0 0 40px rgba(59,130,246,.35);display:flex;align-items:center;padding:0 {34 * u:.0f}px;box-sizing:border-box">'
               f'<span class="mono" style="font-size:{fs}px;color:{LIGHT};margin-right:{14 * u:.0f}px">&gt;</span><span class="mono" id="{sid}c" style="font-size:{fs}px;color:#fff"></span></div>')
    fade(tk, f"#{sid}b", t0 + 0.1, 0.3)
    for cmd, t in commands:
        S.typeon(tk, f"#{sid}c", cmd, t, 26)
    if sub:
        out.append(f'<div class="a sub" id="{sid}s" style="left:{x}px;top:{y + h * 0.18 + bh + 40 * u:.0f}px;width:{w}px;font-size:{round(fs * 0.62)}px">{sub}</div>')
        rise(tk, f"#{sid}s", t_sub, 0.4, 10)
    _cam(tk, sid, t0, t_end or t0 + 6, 1.03)
    return _wrap(sid, "".join(out), x + w / 2, y + h / 2)
