"""A video model watches the finished video (picture and sound) and returns timestamped notes, like an editor's.
Full pipeline only (OpenRouter). Run it on the exported file, after the skill's own gates pass.

Usage: python video_review.py <ws> <video> [--model <id>] [--from <s> --to <s>] [--notes "<what this video is>"] [--tag <tag>]

- The video is sent as a small proxy (854x480, 10 fps, mono audio) so a 20-minute export fits one request; the
  model watches at about 1 frame a second anyway.
- --model swaps the reviewer for this run (default: config.json openrouter.review). Same video, same prompt, so two
  runs compare like for like: notes and cost.
- The edit's own cut list (cut/timeline_<tag>.json; the tag is read from the file name, `<Name>_<tag>.mp4`, or --tag)
  goes to the model with the video, so it knows where the joins are. Without it, one reviewer reported cuts inside
  words where the take was continuous (7 of 8 notes false on a 16-minute video). Every note about a cut is also
  marked with the nearest real join, and `NO CUT HERE` when none is within 1.5 s.
- Writes check/review_<model>.json and prints every note with its time.

Every note is a lead, not a verdict. Before acting on a note, read the frames
at its time (sheets from review.py or a single frame) and listen to that stretch.
"""
import base64, json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import ws, save, p
import openrouter

RUBRIC = """You are the final reviewer on a finished video before it is published. Watch the picture and listen to the
sound. Report only real problems a viewer would notice, at most 15, most important first:
- a word cut off at a cut (start or end clipped), a breath or dead air left at a cut, a doubled or repeated phrase
- a jump at a cut: the face jumps, blinks, looks away or flashes for a frame; a frozen frame; a glitch at a transition
- audio: a level jump between takes, a click, a dropout, music or sound effects too loud UNDER SPEECH (a transition
  sound that sits in the pause between two sentences, with no word under it, is deliberate: do not report it)
- graphics or captions: text appears before it is said, covers the face, is clipped at the frame edge, overlaps other
  text, misspells a name, or sits on screen too briefly to read; a screen left empty or stale for a long time; the
  same words on screen twice at once (a caption repeating the text a graphic is showing at that moment); in a
  vertical video, the top area left empty for a second or more
- anything private on screen that should be blurred (keys, emails, phone numbers, addresses, IPs), even partly
- the speaker saying something that contradicts what is on screen (read numbers carefully: if the mouse pointer
  covers part of a number, or the text is too small to read, do not report a mismatch)
Do not report style preferences or things that are deliberate (a slow section, a long screen recording).
Return JSON only: {"notes": [{"t": "m:ss", "end": "m:ss or null", "type": "cut|audio|picture|graphics|captions|privacy|content",
"what": "what you see or hear", "why": "why it is a problem", "fix": "the fix"}], "overall": "one sentence"}.
If there is nothing worth fixing, return {"notes": [], "overall": "..."}."""


def mmss(s):
    return f"{int(s // 60)}:{s % 60:04.1f}"


def secs(t):
    t = str(t).strip()
    if ":" in t:
        m, s = t.rsplit(":", 1); return int(m) * 60 + float(s)
    return float(t)


def joins(d, video, tag):
    """Times of the cuts between segments, on the export's clock (assemble.py's timeline), or None."""
    if not tag:
        m = re.search(r"_([A-Za-z0-9]+)\.[a-z0-9]+$", os.path.basename(video)); tag = m.group(1) if m else None
    f = p(d, "cut", f"timeline_{tag}.json") if tag else None
    if not f or not os.path.exists(f):
        # the export's version (<Name>_v2) need not be the cut's tag (v1): match the cut by length instead (export =
        # cut + the 1 s end hold). MongoDB Shorts 11/14: every re-export needed --tag by hand.
        import glob, subprocess
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                                   capture_output=True, text=True).stdout or 0)
        cands = []
        for g in glob.glob(p(d, "cut", "timeline_*.json")):
            t_ = json.load(open(g, encoding="utf-8"))
            if t_ and abs(t_[-1]["out_end"] + 1.0 - dur) < 0.15 or t_ and abs(t_[-1]["out_end"] - dur) < 0.15: cands.append(g)
        if len(cands) != 1: return None
        f = cands[0]; print(f"  cut list: {os.path.basename(f)} (matched by length; pass --tag to choose another)")
    tl = json.load(open(f, encoding="utf-8"))
    return [round(s["out_end"], 2) for s in tl[:-1]]


def main():
    a = sys.argv
    if len(a) < 3 or a[1] in ("-h", "--help"): sys.exit(__doc__)
    d, cfg = ws(); video = os.path.abspath(a[2])
    model = a[a.index("--model") + 1] if "--model" in a else openrouter.settings(cfg)["review"]
    t0 = float(a[a.index("--from") + 1]) if "--from" in a else 0.0
    t1 = float(a[a.index("--to") + 1]) if "--to" in a else None
    tmp = os.path.join(tempfile.mkdtemp(prefix="review_"), "proxy.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-i", video] + (["-t", f"{t1 - t0:.3f}"] if t1 else []) + \
          ["-vf", "scale=-2:480,fps=10", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-b:a", "64k", "-ac", "1", tmp]
    subprocess.run(cmd, check=True)
    mb = os.path.getsize(tmp) / 1e6
    print(f"review {os.path.basename(video)} {mmss(t0)}-{mmss(t1) if t1 else 'end'} with {model} ({mb:.1f} MB proxy)")
    text = RUBRIC + (f"\n\nAbout this video: {a[a.index('--notes') + 1]}" if "--notes" in a else "")
    cuts = joins(d, video, a[a.index("--tag") + 1] if "--tag" in a else None)
    if cuts is not None:
        mine = [c - t0 for c in cuts if c >= t0 and (t1 is None or c <= t1)]
        text += ("\n\nThe edit's cuts (joins between takes) in this video are ONLY at these times: "
                 + (", ".join(mmss(c) for c in mine) or "none") + ". Everywhere else the speech and picture are one "
                 "continuous recording: do not report a cut, a word clipped at a cut, or a jump at a cut anywhere else.")
    else:
        print("  (no cut/timeline_<tag>.json for this file, so the reviewer is not told where the cuts are; pass --tag)")
    j = openrouter.call(d, "review", "/chat/completions", {
        "model": model, "usage": {"include": True},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": text},
            {"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + base64.b64encode(open(tmp, "rb").read()).decode()}}]}]},
        timeout=600)
    raw = j["choices"][0]["message"]["content"] or ""
    m = re.search(r"\{.*\}", raw, re.S)
    try: res = json.loads(m.group(0)) if m else {"notes": [], "overall": raw[:500]}
    except json.JSONDecodeError: res = {"notes": [], "overall": "unparsed: " + raw[:800]}
    for n in res.get("notes", []):        # times on the whole video's clock when a section was reviewed
        try: n["t_s"] = round(secs(n["t"]) + t0, 1); n["t"] = mmss(n["t_s"])
        except (ValueError, KeyError): pass
    if cuts is not None:
        for n in res.get("notes", []):
            if "t_s" in n and (n.get("type") == "cut" or "cut" in (str(n.get("what", "")) + str(n.get("why", ""))).lower()):
                near = min(cuts, key=lambda c: abs(c - n["t_s"]), default=None)
                n["nearest_cut"] = mmss(near) if near is not None else None
                if near is None or abs(near - n["t_s"]) > 1.5: n["check"] = "NO CUT HERE"
    cost = (j.get("usage") or {}).get("cost")
    res.update(model=model, video=video, section=[t0, t1], cost=cost)
    slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
    save(res, d, "check", f"review_{slug}.json")
    for n in res.get("notes", []):
        flag = f"  ({n['check']}: nearest cut {n.get('nearest_cut')})" if n.get("check") else ""
        print(f"  {n.get('t', '?'):>7}  [{n.get('type', '')}] {n.get('what', '')}{flag}\n           fix: {n.get('fix', '')}")
    print(f"  overall: {res.get('overall', '')}")
    print(f"  {len(res.get('notes', []))} notes, cost ${cost if cost is not None else '?'} -> {p(d, 'check', f'review_{slug}.json')}")
    print("  Each note is a lead: read the frames at its time and listen before acting on it.")


if __name__ == "__main__":
    main()
