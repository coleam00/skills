"""Thumbnail concepts from several image models at once, from one brief, with the cost of every image.
Full pipeline only (OpenRouter image generation). The agent reads the results itself and picks with the user.

Usage: python thumbnails.py <ws> "<brief>" [--face <photo>] [--models a,b,c] [--n 1] [--tag t1]

- brief: what the thumbnail shows and the exact words on it, e.g. 'Me pointing at a film strip being cut by a robot
  arm. Text, exactly: "IT EDITS MY VIDEOS"'. Exact wording goes in quotes; models add taglines nobody asked for.
- --face: a photo of the speaker to keep their likeness (default: a frame from the middle of the first clip).
  Models that take image input get it as a reference; the others get the brief alone (said in the output).
- --models: default config.json openrouter.images. `python openrouter.py models image` lists the catalog.
- Writes thumbs/<tag>/<model>_<i>.png, a labelled grid thumbs/<tag>/grid.png (model and cost under each) and a
  phone-size grid thumbs/<tag>/grid_phone.png (each concept at 246x138, how most people first see it).
"""
import base64, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import ws, p, find_font
import openrouter

STYLE = ("A YouTube thumbnail, 16:9, bold and simple: one clear subject, high contrast, readable at phone size. "
         "Any text in the image must be exactly the words given in quotes, spelled exactly, nothing added. ")


def main():
    a = sys.argv
    if len(a) < 3 or a[1] in ("-h", "--help"): sys.exit(__doc__)
    d, cfg = ws(); brief = a[2]
    models = a[a.index("--models") + 1].split(",") if "--models" in a else openrouter.settings(cfg)["images"]
    n = int(a[a.index("--n") + 1]) if "--n" in a else 1
    tag = a[a.index("--tag") + 1] if "--tag" in a else "t1"
    out = os.path.join(d, "thumbs", tag); os.makedirs(out, exist_ok=True)
    face = a[a.index("--face") + 1] if "--face" in a else None
    if not face:
        c = cfg["clips"][0]; face = os.path.join(out, "_face_ref.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{c['dur'] / 2:.2f}", "-i", c["path"], "-frames:v", "1", "-q:v", "2", face], check=True)
    ref = {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(open(face, "rb").read()).decode()}}
    try:
        takes_image = {m["id"] for m in openrouter._req("GET", "/images/models").get("data", [])
                       if "image" in (m.get("architecture") or {}).get("input_modalities", [])}
    except RuntimeError:
        takes_image = set(models)

    def one(model):
        body = {"model": model, "prompt": STYLE + ("Keep the person from the reference photo, same face. " if model in takes_image else "")
                + brief, "aspect_ratio": "16:9", "n": n}
        if model in takes_image: body["input_references"] = [ref]
        try:
            j = openrouter.call(d, "thumbnails", "/images", body, timeout=400)
        except RuntimeError as e:
            return model, [], None, str(e)[:200]
        files = []
        for i, img in enumerate(j.get("data", [])):
            ext = (img.get("media_type") or "image/png").split("/")[-1].replace("jpeg", "jpg")
            f = os.path.join(out, f"{re.sub(r'[^a-z0-9]+', '-', model.lower())}_{i + 1}.{ext}")
            open(f, "wb").write(base64.b64decode(img["b64_json"])); files.append(f)
        return model, files, (j.get("usage") or {}).get("cost"), ""

    with ThreadPoolExecutor(len(models)) as ex:
        res = list(ex.map(one, models))
    from PIL import Image, ImageDraw, ImageFont
    tiles = [(f, m, c, m in takes_image) for m, fs, c, _ in res for f in fs]
    fp = find_font("arial.ttf", "DejaVuSans.ttf", "Helvetica.ttc")
    font = ImageFont.truetype(fp, 22) if fp else ImageFont.load_default()
    for name, (tw, th), lab in (("grid.png", (640, 360), True), ("grid_phone.png", (246, 138), False)):
        cols = min(3, max(1, len(tiles))); rows = (len(tiles) + cols - 1) // cols; lh = 34 if lab else 0
        g = Image.new("RGB", (cols * (tw + 12) + 12, rows * (th + lh + 12) + 12), (18, 18, 22)); dr = ImageDraw.Draw(g)
        for k, (f, m, c, used_face) in enumerate(tiles):
            x, y = 12 + (k % cols) * (tw + 12), 12 + (k // cols) * (th + lh + 12)
            g.paste(Image.open(f).convert("RGB").resize((tw, th)), (x, y))
            if lab:
                cost = f"${c:.3f}" if c is not None else "$?"
                dr.text((x, y + th + 6), f"{m}  {cost}{'' if used_face else '  (no face ref)'}", fill=(220, 220, 230), font=font)
        g.save(os.path.join(out, name))
    for m, fs, c, err in res:
        print(f"  {m:40s} {len(fs)} image(s)  ${c if c is not None else '?'}  {'face reference' if m in takes_image else 'brief only'}  {err}")
    print(f"  total ${sum(c or 0 for _, _, c, _ in res):.3f} -> {os.path.join(out, 'grid.png')} and grid_phone.png")
    print("  Read the grid at full size: exact text, the face, anything added that was not asked for.")


if __name__ == "__main__":
    main()
