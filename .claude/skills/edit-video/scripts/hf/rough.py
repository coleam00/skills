"""Hand-drawn SVG marks: seeded wobble so they are deterministic but imperfect. Each returns (d, length)."""
import math, random

def _len(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))

def _d(pts):
    # smooth through points with quadratic midpoints
    if len(pts) < 3:
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    s = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(1, len(pts) - 1):
        mx = (pts[i][0] + pts[i + 1][0]) / 2; my = (pts[i][1] + pts[i + 1][1]) / 2
        s += f" Q{pts[i][0]:.1f},{pts[i][1]:.1f} {mx:.1f},{my:.1f}"
    s += f" L{pts[-1][0]:.1f},{pts[-1][1]:.1f}"
    return s

def ellipse(cx, cy, rx, ry, seed=1, overshoot=0.18, wobble=0.035, n=60):
    """A loop drawn by hand: starts upper-left, goes round a bit more than once, radius wobbles."""
    r = random.Random(seed); pts = []
    a0 = -2.4 + r.uniform(-0.2, 0.2); total = 2 * math.pi * (1 + overshoot)
    ph1, ph2 = r.uniform(0, 6.28), r.uniform(0, 6.28)
    for i in range(n + 1):
        t = i / n; a = a0 + total * t
        k = 1 + wobble * math.sin(3 * a + ph1) + wobble * 0.6 * math.sin(5 * a + ph2) + 0.04 * t
        pts.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a)))
    return _d(pts), _len(pts)

def underline(x0, x1, y, seed=2, sag=6, n=18):
    r = random.Random(seed); pts = []
    for i in range(n + 1):
        t = i / n
        pts.append((x0 + (x1 - x0) * t, y + sag * math.sin(math.pi * t) * r.uniform(0.6, 1.0) + r.uniform(-1.2, 1.2) - 4 * t))
    return _d(pts), _len(pts)

def strike(x0, x1, y, seed=3, passes=3, amp=10):
    """A scribbled strike-through: zig-zag back and forth across the text."""
    r = random.Random(seed); pts = []
    for p in range(passes):
        xs = (x0, x1) if p % 2 == 0 else (x1, x0)
        for i in range(9):
            t = i / 8
            pts.append((xs[0] + (xs[1] - xs[0]) * t, y + r.uniform(-amp, amp) * 0.5 + (p - passes / 2) * 5))
    return _d(pts), _len(pts)

def check(x, y, s=1.0, seed=4):
    r = random.Random(seed)
    pts = [(x, y + 18 * s), (x + 14 * s + r.uniform(-2, 2), y + 34 * s), (x + 20 * s, y + 30 * s), (x + 48 * s + r.uniform(-3, 3), y - 6 * s + r.uniform(-3, 3))]
    return _d(pts), _len(pts)

def arrow(x0, y0, x1, y1, seed=5, bend=0.18, head=26):
    """Curved hand arrow; returns (shaft_d, shaft_len, head_d, head_len)."""
    r = random.Random(seed); pts = []
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2; dx, dy = x1 - x0, y1 - y0; L = math.hypot(dx, dy)
    nx, ny = -dy / L, dx / L; off = L * bend
    for i in range(21):
        t = i / 20; b = math.sin(math.pi * t) * off
        pts.append((x0 + dx * t + nx * b + r.uniform(-1, 1), y0 + dy * t + ny * b + r.uniform(-1, 1)))
    ex, ey = pts[-1]; px, py = pts[-3]; ang = math.atan2(ey - py, ex - px)
    h1 = (ex - head * math.cos(ang - 0.5), ey - head * math.sin(ang - 0.5)); h2 = (ex - head * math.cos(ang + 0.5), ey - head * math.sin(ang + 0.5))
    hd = f"M{h1[0]:.1f},{h1[1]:.1f} L{ex:.1f},{ey:.1f} L{h2[0]:.1f},{h2[1]:.1f}"
    return _d(pts), _len(pts), hd, 2 * head + 4

def box(x, y, w, h, seed=6):
    """Hand-drawn checkbox square."""
    r = random.Random(seed); j = lambda: r.uniform(-2.5, 2.5)
    pts = [(x + j(), y + j()), (x + w + j(), y + j()), (x + w + j(), y + h + j()), (x + j(), y + h + j()), (x + j() + 3, y + j() - 1)]
    return "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in pts), _len(pts)

def signature(x, y, w=260, seed=8):
    """A loopy hand signature."""
    r = random.Random(seed); pts = []
    for i in range(70):
        t = i / 69
        pts.append((x + w * t + 18 * math.sin(t * 22 + r.uniform(-0.2, 0.2)), y + 26 * math.sin(t * 9) * (1 - t * 0.5) + 16 * math.cos(t * 22) + r.uniform(-1.5, 1.5)))
    pts.append((x + w * 0.2, y + 40)); pts.append((x + w * 1.05, y + 28))
    return _d(pts), _len(pts)

def circle_path(cx, cy, R, seed=9):
    """A loop around (cx,cy) radius R, hand-drawn, roughly one turn (for the lifecycle)."""
    return ellipse(cx, cy, R, R * 0.97, seed=seed, overshoot=0.04, wobble=0.012, n=90)
