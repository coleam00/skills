"""Frame-exact renderer for website screen footage (see references/advanced/dynamic-screen.md).

Every output frame is a real headless-Chromium render at an exact scroll position and an exact page
time. The page clock is ours: each frame, every CSS animation/transition and every <video> on the page
is set to that frame's time, so the page moves at true speed however long a screenshot takes. Without
this, looping videos and typing effects play several times too fast during a scroll.

Zoom shots use a page rendered at device_scale_factor 2 and a clipped screenshot, so a 2x punch-in stays
sharp. Frames stream straight into ffmpeg.

Use it from a build script in the edit's workspace (not from the skill folder):

    import sys; sys.path.insert(0, "<skill>/scripts"); from page_render import Site, Cam, Writer, render, act
    s = Site(browser, "https://example.com/page", dsf=2)          # dsf=2 only if the shot zooms
    w = Writer(Path("screen_a.mkv"))
    render(w, s, t0, t1, Cam([(t0, y0, (960, 540, 1)), (t2, y1, (cx, cy, 1.5))]),
           [(t_click, act("open row", lambda: s.click("Row title")))], clock0=t0 + OFF)
    w.close()

Run with: uv run --with playwright --with pillow python -I build.py
PREVIEW="12.6,14.6" renders only those times as PNGs in ./preview (framing review in minutes).
"""
import io, os, subprocess
from pathlib import Path
from PIL import Image

# PREVIEW="12.6,14.6,..." renders only the frames at those times, as PNGs in ./preview (framing review)
PREVIEW = [float(x) for x in os.environ.get("PREVIEW", "").split(",") if x.strip()]
PREVIEW_DIR = Path.cwd() / "preview"                       # the edit workspace, never the skill folder

FPS, W, H = 60, 1920, 1080
CSS = """
html{scrollbar-width:none!important;scroll-behavior:auto!important} ::-webkit-scrollbar{display:none!important}
.cky-consent-container,.cky-overlay,.cky-btn-revisit-wrapper{display:none!important}
"""
JS_TOP = """(t)=>{const e=[...document.querySelectorAll('h1,h2,h3,h4,button,summary,p,span,div')]
  .find(x=>x.offsetParent&&x.childElementCount<4&&x.textContent.trim().startsWith(t));
  return e?Math.round(e.getBoundingClientRect().top+scrollY):-1}"""
JS_BOX = """(t)=>{const e=[...document.querySelectorAll('h1,h2,h3,h4,button,summary,p,span,div,a,li')]
  .find(x=>x.offsetParent&&x.childElementCount<4&&x.textContent.trim().startsWith(t));
  if(!e) return null; const r=e.getBoundingClientRect(); return [r.left, r.top+scrollY, r.width, r.height]}"""
JS_CLOCK = """() => {
  if (window.__clk) return;
  const base = new WeakMap(), vbase = new WeakMap();
  // the page re-plays videos when they scroll into view; once we own the clock, nothing plays on its own
  HTMLMediaElement.prototype.play = function () { this.pause(); return Promise.resolve(); };
  window.__clk = async (T, Y) => {          // T: page time in ms, Y: scroll position
    if (Y !== null && Y !== undefined && scrollY !== Y) { scrollTo(0, Y);
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); }
    // First call: every running animation and video is anchored to page time 0, so phases are a pure
    // function of T (repeatable). Anything that starts later (hover, click, scroll transitions) starts now.
    const first = !window.__clkInit; window.__clkInit = true;
    for (const a of document.getAnimations()) {
      if (!base.has(a)) { a.pause(); base.set(a, first ? 0 : -T); }
      a.currentTime = Math.max(0, base.get(a) + T);
    }
    const waits = [];
    for (const v of document.querySelectorAll('video')) {
      if (!vbase.has(v)) { v.pause(); vbase.set(v, first ? 0 : -T / 1000); }
      if (!v.paused) v.pause();
      const d = v.duration;
      if (!d || !isFinite(d)) continue;
      const fps = window.__videoFps || 24;     // the page's clips' frame rate: check with ffprobe, pass Site(video_fps=)
      let t = vbase.get(v) + T / 1000; t = ((t % d) + d) % d;
      const fi = Math.min(Math.floor(t * fps), Math.floor(d * fps) - 1);
      if (v.__fi === fi) continue;             // same source frame as last time: nothing to do
      v.__fi = fi;
      waits.push(new Promise(r => {
        let done = false; const fin = () => { if (!done) { done = true; r(); } };
        if (v.requestVideoFrameCallback) v.requestVideoFrameCallback(() => fin());
        else v.addEventListener('seeked', fin, { once: true });
        setTimeout(fin, 1500);
      }));
      v.currentTime = (fi + 0.5) / fps;        // middle of the source frame: no boundary ambiguity
    }
    await Promise.all(waits);
    // let every layer (card, nav, decorations) commit at this scroll position and time before the capture
    for (let i = 0; i < 3; i++) await new Promise(r => requestAnimationFrame(r));
    await new Promise(r => setTimeout(r, 20));
  };
}"""


def ease(p):
    return 4 * p ** 3 if p < .5 else 1 - (-2 * p + 2) ** 3 / 2


class Site:
    """One loaded page. `dsf=2` for shots that zoom."""

    def __init__(self, browser, url, dsf=1, video_fps=24):
        self.pg = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=dsf)
        self.dsf = dsf
        self.pg.goto(url, wait_until="networkidle", timeout=90000)
        self.pg.add_style_tag(content=CSS)
        h = self.pg.evaluate("document.body.scrollHeight")
        for y in range(0, h, 500):                      # load lazy images / reveal-on-scroll once
            self.pg.evaluate(f"scrollTo(0,{y})"); self.pg.wait_for_timeout(90)
        self.pg.wait_for_load_state("networkidle")
        self.pg.evaluate("scrollTo(0,0)"); self.pg.wait_for_timeout(800)
        self.pg.mouse.move(1900, 1000)
        self.pg.evaluate(f"window.__videoFps = {video_fps}")
        self.pg.evaluate(JS_CLOCK)
        self.y = None

    def top(self, text):
        y = self.pg.evaluate(JS_TOP, text)
        if y < 0:
            raise SystemExit(f"not found: {text}")
        return y

    def box(self, text):
        b = self.pg.evaluate(JS_BOX, text)
        if b is None:
            raise SystemExit(f"not found: {text}")
        return b                                         # [x, page_y, w, h]

    def find(self, text):
        """Smallest visible element whose text contains `text`: [x, page_y, w, h]."""
        b = self.pg.evaluate("""(t)=>{let best=null,ba=1e18;
          for(const e of document.querySelectorAll('body *')){ if(!e.offsetParent||!e.textContent.includes(t)) continue;
            const r=e.getBoundingClientRect(), a=r.width*r.height; if(a>0&&a<ba){ba=a;best=[r.left,r.top+scrollY,r.width,r.height];}}
          return best}""", text)
        if b is None:
            raise SystemExit(f"not found: {text}")
        return b

    def click(self, text):
        self.pg.get_by_text(text, exact=True).first.evaluate("e => (e.closest('button') || e).click()")

    def frame(self, y, T, zoom=None):
        """Render one frame: scroll y (page px), page time T (s), zoom=(cx, cy, s) in viewport px."""
        y = round(y)
        self.pg.evaluate("([T, Y]) => window.__clk(T, Y)", [T * 1000, y])
        if y != self.y:
            got = self.pg.evaluate("scrollY")
            if abs(got - y) > 1:
                raise SystemExit(f"scroll to {y} landed at {got}")
            self.y = y
        clip = None
        if zoom and zoom[2] > 1.0001:
            if self.dsf < 2:
                raise SystemExit("zoom needs a dsf=2 page")
            cx, cy, s = zoom
            w, h = W / s, H / s
            x0 = min(max(cx - w / 2, 0), W - w); y0 = min(max(cy - h / 2, 0), H - h)
            clip = {"x": x0, "y": y0, "width": w, "height": h}
        img = Image.open(io.BytesIO(self.pg.screenshot(type="jpeg", quality=95, clip=clip))).convert("RGB")
        if img.size != (W, H):
            img = img.resize((W, H), Image.LANCZOS)
        return img


class Cam:
    """Keyframes (t, y, (cx, cy, s)). Between two keys the values ease; two keys at one t are a cut."""

    def __init__(self, keys):
        self.keys = sorted(keys, key=lambda k: k[0])

    def at(self, t):
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1], ks[0][2]
        for a, b in zip(ks, ks[1:]):
            if a[0] <= t < b[0]:
                if b[0] - a[0] < 1e-9:
                    continue
                e = ease((t - a[0]) / (b[0] - a[0]))
                y = a[1] + (b[1] - a[1]) * e
                z = tuple(a[2][i] + (b[2][i] - a[2][i]) * e for i in range(3))
                return y, z
        return ks[-1][1], ks[-1][2]


class Writer:
    def __init__(self, path):
        self.path, self.n = path, 0
        if PREVIEW:
            self.p = None
            return
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                   "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                                   "-crf", "10", "-pix_fmt", "yuv420p", str(path)], stdin=subprocess.PIPE)

    def put(self, img):
        self.p.stdin.write(img.tobytes()); self.n += 1

    def close(self):
        if self.p is None:
            return
        self.p.stdin.close()
        if self.p.wait():
            raise SystemExit(f"ffmpeg failed: {self.path}")
        print(f"wrote {self.path.name}: {self.n} frames ({self.n / FPS:.3f}s)", flush=True)


def render(writer, site, t0, t1, cam, actions=(), clock0=0.0, log=None):
    """Frames for timeline time [t0, t1). Page time = clock0 + (t - t0). actions: [(t, fn)] run once at t."""
    todo = sorted(actions, key=lambda a: a[0])
    n0 = round(t0 * FPS); n1 = round(t1 * FPS)
    for k in range(n0, n1):
        t = k / FPS
        while todo and todo[0][0] <= t + 1e-9:
            at, fn = todo.pop(0)
            fn()
            if log is not None:
                log.append((t, getattr(fn, "label", "action")))
        y, z = cam.at(t)
        if PREVIEW:
            hit = [p for p in PREVIEW if abs(p - t) < 0.5 / FPS]
            if hit:
                PREVIEW_DIR.mkdir(exist_ok=True)
                site.frame(y, clock0 + (t - t0), z).save(PREVIEW_DIR / f"p_{hit[0]:06.2f}.png")
            continue
        writer.put(site.frame(y, clock0 + (t - t0), z))
        if (k - n0) % 600 == 0:
            print(f"  {t:6.2f}s", flush=True)


def act(label, fn):
    fn.label = label
    return fn


if __name__ == "__main__":
    print(__doc__.strip())
