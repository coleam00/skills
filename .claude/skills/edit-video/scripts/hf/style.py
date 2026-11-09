"""Design tokens, caption layer and the HyperFrames page shell. One place to change the look.

Default look: neutral dark (near-black #07090F, a deep blue gradient, accent #3B82F6 / light #60A5FA, Inter for
words, JetBrains Mono for anything technical). Override per project with <ws>/brand.json (examples/brand.json):
{"bg": "...", "accent": "...", "accent_light": "...", "accent_deep": "...", "font": "...", "mono": "...", "caption_active": "..."}
The scene kit is drawn in the default colours; page() re-tints every default accent and background colour in the
finished HTML to the brand's, so one brand.json changes the whole page.
"""
import json, os, shutil, sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import canvas, stacked

TOKENS = {"bg": "#07090F", "surface": "#0E1525", "ink": "#F5F7FB", "ink2": "#93A1B8", "accent": "#3B82F6", "accent_light": "#60A5FA",
          "accent_deep": "#1E3A8A", "marker": "rgba(37,99,235,.62)", "bad": "#F87171", "font": "Inter", "mono": "JetBrains Mono",
          "caption_active": "#5aa9ff", "caption_ink": "#f4f6fb"}

def tokens(d):
    t = dict(TOKENS)
    b = os.path.join(d, "brand.json")
    if os.path.exists(b): t.update(json.load(open(b, encoding="utf-8")))
    return t

# The kit's built-in colours, and the brand token each one follows. retint() maps them in the finished page.
_DEFAULTS = {"accent": "#3B82F6", "accent_light": "#60A5FA", "accent_deep": "#1E3A8A", "bg": "#07090F"}

def _rgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def retint(html, t):
    """Swap the kit's default accent/background colours (hex and rgba forms) for the brand's. A no-op on the defaults."""
    import re
    for k, old in _DEFAULTS.items():
        new = t.get(k, old)
        if not isinstance(new, str) or not new.startswith("#") or len(new) != 7 or new.lower() == old.lower(): continue
        html = re.sub(re.escape(old), new, html, flags=re.I)
        r, g, b = _rgb(old); nr, ng, nb = _rgb(new)
        html = re.sub(rf"rgba\(\s*{r}\s*,\s*{g}\s*,\s*{b}\s*,", f"rgba({nr},{ng},{nb},", html)
    return html

def caption_geom(cfg):
    """(top, height, font_px, max_width) of the caption band when the face is full frame (stacked layout: on the
    graphics side of the seam, never over the face band)."""
    W, H = canvas(cfg); G = stacked(cfg)
    if G: return G["cap_top"], G["cap_h"], round(W * 0.059), round(W * 0.89)
    if H > W: return round(H * 0.66), 150, round(W * 0.059), round(W * 0.89)      # on the shirt, below the chin
    return round(H * 0.80), round(H * 0.13), round(H * 0.054), round(W * 0.78)    # lower third

def grain(path):
    if os.path.exists(path): return
    rng = np.random.default_rng(7)
    n = np.clip(128 + rng.normal(0, 22, (1080, 1080)), 0, 255).astype(np.uint8)
    Image.fromarray(n).save(path)

def css(t, cfg):
    W, H = canvas(cfg); top, ch, fs, mw = caption_geom(cfg); G = stacked(cfg)
    # stacked: the face video is the camera band at native size, parked in its band; overflow keeps a punch-in drift
    # inside the band instead of over the graphics
    band = (f"#facewrap {{ top:{G['band_y']}px; width:{round(G['fw'] * G['s'])}px; height:{G['bh']}px; overflow:hidden; }}"
            f"#facewrap video {{ object-fit:fill; }}") if G else ""
    return f"""
html,body {{ margin:0; padding:0; background:{t['bg']}; }}
#root {{ position:relative; width:{W}px; height:{H}px; overflow:hidden; background:{t['bg']}; }}
#stage {{ position:absolute; inset:0; background:linear-gradient(to bottom, #07090f 0%, rgba(30,58,138,.55) 52%, #080a13 100%), {t['bg']}; }}
.grain {{ position:absolute; inset:0; background:url(grain.png); mix-blend-mode:overlay; opacity:.10; pointer-events:none; }}
#facewrap {{ position:absolute; left:0; top:0; width:{W}px; height:{H}px; transform-origin:0 0; z-index:5; }}
#facezoom {{ position:absolute; inset:0; transform-origin:50% 36%; }}
#facewrap video {{ width:100%; height:100%; object-fit:cover; display:block; }}
#edge {{ position:absolute; z-index:6; opacity:0; pointer-events:none; }}
#caps {{ position:absolute; left:0; top:{top}px; width:{W}px; height:{ch}px; z-index:50; pointer-events:none; transform-origin:0 0; }}
.cg {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; opacity:0; visibility:hidden; }}
.cg .line {{ max-width:{mw}px; text-align:center; font-family:'{t['font']}'; font-weight:800; font-size:{fs}px; line-height:1.08;
  letter-spacing:-0.5px; color:{t['caption_ink']}; text-shadow:0 3px 14px rgba(0,0,0,.85), 0 0 2px rgba(0,0,0,.9); }}
.cg .w {{ display:inline-block; margin:0 0.13em; }}
#page, #full {{ position:absolute; inset:0; pointer-events:none; }}
#page {{ z-index:20; }}
#full {{ z-index:30; clip-path:inset(100% 0% 0% 0%); }}
#fullbg {{ position:absolute; inset:0; opacity:0; background:linear-gradient(to bottom, #07090f 0%, rgba(30,58,138,.5) 55%, #080a13 100%), {t['bg']}; }}
.scene {{ position:absolute; inset:0; opacity:0; color:{t['ink']}; font-family:'{t['font']}'; }}
""" + band

def captions_html(cap):
    ws_ = cap["words"]; out = ['<div id="caps">']
    for gi, g in enumerate(cap["groups"]):
        out.append(f'<div class="cg" id="cg{gi}"><div class="line">' + "".join(f'<span class="w" id="w{j}">{ws_[j]["w"]}</span>' for j in g["words"]) + "</div></div>")
    return "\n".join(out + ["</div>"])

def captions_js(cap, t):
    g = [{"s": x["s"], "e": x["e"], "w": x["words"]} for x in cap["groups"]]; w = [{"s": x["s"], "e": x["e"]} for x in cap["words"]]
    return f"""
var CG={json.dumps(g)}, CW={json.dumps(w)};
CG.forEach(function(g,gi){{ var el=document.getElementById('cg'+gi);
  tl.set(el,{{visibility:'visible'}},g.s); tl.fromTo(el,{{opacity:0,y:14}},{{opacity:1,y:0,duration:0.12,ease:'power3.out'}},g.s);
  g.w.forEach(function(j){{ var w=document.getElementById('w'+j); tl.set(w,{{color:'{t['caption_active']}'}},CW[j].s);
    tl.set(w,{{color:'{t['caption_ink']}'}},Math.min(CW[j].e+0.05,g.e)); }});
  tl.set(el,{{opacity:0,visibility:'hidden'}},g.e); }});
"""

def page(d, cfg, tag, name, cap, extra_css, page_html, full_html, overlay_html, js, duration, tk=None):
    """Write <ws>/hf/<name>/ (index.html + face.mp4 + assets). Returns the project dir.
    tk (optional): the engine.Track, for the PIP bubble ring and the SCREEN track (screen.mp4) when the schedule used
    them. config.json "captions": "srt" leaves captions out of the picture (long-form YouTube uploads the .srt);
    the default "burn" burns them in as before."""
    t = tokens(d); W, H = canvas(cfg)
    proj = os.path.join(d, "hf", name); os.makedirs(proj, exist_ok=True)
    src = os.path.join(d, "cut", f"clean_{tag}.mp4"); dst = os.path.join(proj, "face.mp4")
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src): shutil.copy2(src, dst)
    lay_css, lay_html = tk.layers() if tk is not None else ("", "")
    if tk is not None and tk.used_screen:
        ssrc = os.path.join(d, tk.screen_src) if not os.path.isabs(tk.screen_src) else tk.screen_src; sdst = os.path.join(proj, "screen.mp4")
        if not os.path.exists(sdst) or os.path.getmtime(sdst) < os.path.getmtime(ssrc): shutil.copy2(ssrc, sdst)
    burn = cfg.get("captions", "burn") == "burn"
    grain(os.path.join(proj, "grain.png"))
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>{css(t, cfg)}{extra_css}{lay_css}</style>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script></head><body>
<div id="root" data-composition-id="{name}" data-start="0" data-duration="{duration}" data-width="{W}" data-height="{H}">
<div id="stage"><div class="grain"></div></div>
<div id="facewrap"><div id="facezoom"{' data-layout-allow-overflow' if stacked(cfg) else ''}><video id="face" data-start="0" data-duration="{duration}" data-track-index="0" src="face.mp4" muted playsinline></video></div></div>
<div id="edge"></div>
<audio id="vo" data-start="0" data-duration="{duration}" data-track-index="1" src="face.mp4" data-volume="1"></audio>
<div id="page">{page_html}</div><div id="full"><div id="fullbg"></div><div class="grain"></div>{getattr(tk, "full_pre", "")}{full_html}</div>{lay_html}{overlay_html}
{captions_html(cap) if burn else '<div id="caps"></div>'}
</div><script>window.__timelines=window.__timelines||{{}};gsap.config({{force3D:true}});var tl=gsap.timeline({{paused:true}});
{js}
{captions_js(cap, t) if burn else ""}
window.__timelines["{name}"]=tl;</script></body></html>"""
    open(os.path.join(proj, "index.html"), "w", encoding="utf-8").write(retint(html, t))
    json.dump({"id": name, "name": name}, open(os.path.join(proj, "meta.json"), "w"))
    return proj
