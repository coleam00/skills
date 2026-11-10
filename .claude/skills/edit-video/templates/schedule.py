"""B-roll schedule for ONE video. Copy to <ws>/schedule_<name>.py, then edit the beats.

Run:  EDIT_VIDEO_SCRIPTS=$S uv run --project $S python <ws>/schedule_<name>.py <ws> [--tag v1]
Then: python $S/render.py <ws> <name> --quality standard  ->  review.py --beats  ->  iterate.

Rules of thumb (references/captions-and-broll.md has the full list):
- Anchor every time to a spoken phrase with tk.at("..."). Never hard-code seconds: a re-cut moves everything.
- Enter a layout ~0.5 s (SPLIT) or ~0.4 s (FULL) before the first word it illustrates; leave on the phrase that ends the idea.
- 55-70% of runtime in B-roll, ~1/3 of it full-screen; never more than ~12 s without the face returning,
  never a face gap shorter than ~1.5 s between two B-roll segments (merge them instead).
- Long-form talk (10+ min, 16:9): 50-65% graphics counting PIP/SCREEN, which keep the face on as a bubble; FULL
  stays short (the report flags any FULL over 12 s). references/captions-and-broll.md.
- Stacked layout (face in its own band): the graphics band is never empty. Chain beats with tk.band(t, sid) from
  0.0 and hold S.title_card where nothing new is said; the report flags EMPTY BAND over 2 s.
- One idea per scene. If a scene needs more than ~6 labels, split it or cut words.
"""
import os, sys

# The skill's scripts folder. This file lives in the workspace, so it cannot find the skill from its own path:
# run it as  EDIT_VIDEO_SCRIPTS=$S uv run --project $S python <ws>/schedule_<name>.py <ws>
SKILL = os.environ.get("EDIT_VIDEO_SCRIPTS") or (os.path.join(os.environ["CLAUDE_SKILL_DIR"], "scripts") if os.environ.get("CLAUDE_SKILL_DIR") else "")
if not os.path.isfile(os.path.join(SKILL, "common.py")): sys.exit("set EDIT_VIDEO_SCRIPTS to the edit-video skill's scripts folder")
sys.path.insert(0, SKILL); sys.path.insert(0, os.path.join(SKILL, "hf"))
from common import ws
import engine, scenes as S, style

NAME = "broll"          # HyperFrames project name -> <ws>/hf/<NAME>/

def beats(tk):
    """Return (page_scenes, full_scenes, overlay_html, extra_css). Each beat: enter a layout, build its scene."""
    P, F = [], []; at = tk.at
    PB, FB = tk.page_box, tk.full_box

    # --- example: a split-screen statement on the hook ------------------------------------------------
    s = tk.split(at("there is this assumption") - 0.5); tk.pscene(s, "hook")
    P.append(S.statement(tk, "hook", PB, [
        dict(text="More secure", t=at("secure"), kind="head", hl=True),
        dict(text="Less capable.", t=at("less capable"), kind="line", mark="strike", t_mark=at("but the real goal")),
        dict(text="Keep the useful capability.", t=at("useful"), kind="accent", key="capability.", mark="underline"),
    ], s))
    tk.face(at("capability away", end=True) + 0.3)

    # --- example: a full-screen checklist -------------------------------------------------------------
    s = tk.full(at("it means scanning") - 0.4, "scan")
    F.append(S.checklist(tk, "scan", FB, [("The model", at("model")), ("Skills", at("skills")), ("Tools", at("tools"))],
                         s, title="Before you trust it"))
    tk.face(at("trusting them", end=True) + 0.3)

    # --- long-form 16:9 only (references/captions-and-broll.md): PIP keeps the face on as a bubble -------------
    # PIP scenes go in F (they share the full layer) and are laid out in tk.pip_box, which keeps clear of the bubble.
    # s = tk.pip(at("the first thing") - 0.4, "ctx")
    # F.append(S.columns(tk, "ctx", tk.pip_box, [("The tools", at("tools"), [("Your editor", at("editor"))])], s))
    # SCREEN shows the recorded slides/demo (assemble.py --screen first), face in the bubble; no scene to build:
    # tk.screen(at("look at this") - 0.4)
    # tk.face(at("and that is it", end=True) + 0.3)

    return P, F, "", ""

def main():
    d, cfg = ws(); tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "v1"
    tk = engine.Track(d, cfg, tag)
    P, F, overlay, extra = beats(tk)
    js = tk.finish(); tk.report()
    css = tk.css() + S.base_css(tk.T) + extra
    proj = style.page(d, cfg, tag, NAME, tk.cap, css, "".join(P), "".join(F), overlay, js, tk.D, tk=tk)
    print("wrote", proj)

if __name__ == "__main__":
    main()
