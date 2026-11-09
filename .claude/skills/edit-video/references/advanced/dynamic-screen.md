# Dynamic screen: re-rendering a website so the screen follows the words

For a stitch edit whose screen is a website (a product page, docs, a landing page) and whose voiceover is locked:
a reviewer wants different visuals; the audio and the face must not change. Every rule below names the failure that
produced it.

## Contents
- When this applies
- 1. Map every line to something the site shows
- 2. Two cuts: safe and dynamic
- 3. Render, never capture
- 4. Moves that work
- 5. Framing
- 6. Assemble over the locked cut
- 7. Validate with numbers, then with eyes

## When this applies

- The voiceover and face are approved and must stay byte-identical; only the screen changes.
- The screen is a page that loads in Chromium (public, or a logged-in session that can be scripted).
- Not for app demos or terminals: record those live.

## 1. Map every line to something the site shows

A cut that opened one accordion for a sentence naming three different things, one of which was not on that page, was
rejected as "not aligned with what I'm saying".

1. Get word times from the cut's transcript; split the script into phrases.
2. Dump the site headless before deciding anything: every heading with its page y, every accordion's contents (open
   each, read the text), every link, every `<video>`, `<canvas>` and `document.getAnimations()` entry. Do it for every
   page the voiceover refers to.
3. Build a table: phrase, start time, the best matching on-page element. Literal beats thematic: "their two
   programs" -> the menu that lists exactly those two; "a couple of years of experience" -> the quote that says
   "two years".
4. A phrase the main page cannot show gets its own short shot on the page that can. Say so in the plan; never cover
   it with the nearest unrelated section.
5. Check the reviewer's exact asks against the table, from their message, not from memory.

## 2. Two cuts: safe and dynamic

Every added move is a chance for a new mistake, so make both:

- **Safe:** only the reviewer's asks plus the fixes that make each phrase match. Cuts, accordion opens, a few slow
  scrolls, no zooms. Shippable on its own.
- **Dynamic:** one camera idea per phrase (push-in, hover, zoom, scroll), smooth eases, each tied to a word time.

Both share one renderer and one validator; the dynamic spec is the safe spec plus camera keys.

## 3. Render, never capture

Live capture of a scripted scroll dropped every other frame under encoder load (per-frame steps 0, 6, 0, 6, 22 px)
and clicks fired a second late. `scripts/page_render.py` renders instead:

- **One real render per output frame** at an exact scroll position: `Site.frame(y, T, zoom)`.
- **The page clock is yours.** Each frame pauses every `document.getAnimations()` entry and sets its time to the
  frame's page time, and seeks every `<video>`. Otherwise the page runs on wall-clock time while a frame takes
  0.1-0.9 s, and looping videos and typing effects play several times too fast. Phases are anchored to page time 0,
  so a cycling element shows the same thing every render; offset the shot's clock to land a cycle on a word. Read
  cycle lengths from `getAnimations()[i].effect.getTiming()`.
- **Videos:** stub `HTMLMediaElement.play`, seek to the middle of the source frame, wait for
  `requestVideoFrameCallback`. Pass `Site(video_fps=)` from ffprobe of the clip.
- **Zoom shots** load at `dsf=2` and screenshot a clip, so a 2x push-in stays sharp (about 3x the cost per frame).
- **Clicks** are DOM clicks (`Site.click`), never pointer clicks: the pointer leaves hover styling that pops off
  mid-scroll. Hovers that should show (a menu) are `page.mouse.move`.
- **Preview first:** `PREVIEW="t1,t2,..."` renders only those frames as PNGs in `./preview`. Review every camera
  key's start, middle and end there; a framing fix costs minutes, not an hour.

Run a build script from the workspace: `uv run --with playwright --with pillow python -I build.py $S` (install the
browser once with `uv run --with playwright playwright install chromium`). `-I` drops the script's own folder from
the import path, so the build script adds the skill's scripts folder itself. A complete build script (a local file
works as well as a URL: `Path("page.html").resolve().as_uri()`):

```python
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])                          # $S, the skill's scripts folder
from playwright.sync_api import sync_playwright
from page_render import Site, Cam, Writer, render, act

with sync_playwright() as p:
    b = p.chromium.launch()
    s = Site(b, "https://example.com/page", dsf=2)        # dsf=2 only if a shot zooms
    y1 = s.top("Pricing") - 80                             # page y of a heading, minus some headroom
    w = Writer(Path("screen_a.mkv"))                        # 1920x1080, 60 fps
    render(w, s, 0.0, 4.0,
           Cam([(0.0, 0, (960, 540, 1)), (1.0, 0, (960, 540, 1)),      # hold, then scroll 1.0-2.2 s
                (2.2, y1, (960, 540, 1)), (3.0, y1, (960, 540, 1)),
                (3.8, y1, (700, 300, 1.5))]),                          # push in 1.5x
           [(2.4, act("open plans", lambda: s.click("Show the plans")))])
    w.close(); b.close()
```

`render()` times are seconds on the screen track you are building; place them from the cut's word times.

## 4. Moves that work

| Move | How | Timing |
|---|---|---|
| Push-in | camera key from `(960,540,1)` to `(cx,cy,1.5-1.7)` | ease over 0.8-2.0 s, starting a beat before the word |
| Pull back | the reverse | 0.7-1.0 s, right after the phrase ends |
| Scroll | camera key y0 -> y1 | 1.0-1.6 s; jumps over ~3000 px are cuts, not scrolls |
| Accordion open | `Site.click` action | on the word, or on the cut frame itself for a cut-in |
| Menu hover | `mouse.move` onto each item as it is named | menu open ~0.3 s before the first name |
| Cut | two camera keys at the same time | on a phrase boundary; one shot per phrase, none under ~2.5 s |

- A cut-in to a section that opens: fire the click on the cut frame. Two frames late showed an unrelated closed list.
- Easing is cubic in-out; its ends move under a pixel per frame. That is invisible; the validator ignores it.

## 5. Framing

- Nothing that matters under the face bubble: test the rendered PNG for text pixels inside the circle.
- Keep the whole element and its heading in a zoom; a zoom that cuts a heading in half reads as a mistake.
- Zoom 1.35-1.7 for a card or block; 2.0 is the sharp limit at dsf=2. Scroll first if the target is near an edge.

## 6. Assemble over the locked cut

- Render the screen in parts around any section of the old cut that stays.
- Concat the parts with the kept sections, overlay the face bubble lifted from the old export with a circular alpha
  mask, copy the old audio (`-c:a copy`).
- **The crop must stay inside the frame.** A crop past the edge is clamped silently; the bubble landed 4 px off with a
  ring of background around it. Use `exact=1` and assert `x+w<=W and y+h<=H`.
- Retime the old export by frame number (`setpts=N/(FPS*TB)`) first: millisecond-rounded timestamps made the bubble
  repeat and skip frames.
- Never overwrite an export.

## 7. Validate with numbers, then with eyes

On every frame of the final, not a few thumbnails:

1. Duration and fps match; audio MD5 equals the approved cut's.
2. Face: inside the circle, final vs the retimed old cut, small mean absolute difference.
3. Ring: the band just outside the circle, final vs the clean screen, near zero.
4. Motion: per-frame mean change of the screen, bubble masked. Every big change must be an intended cut; inside a
   camera move, flag any frame over 1.6x or under 0.5x its neighbours' median.
5. Videos: a 24 fps clip at 60 fps repeats exactly 60% of frames.
6. Tracking: in a scroll, two columns of the page move by the same pixels every frame.
7. Eyes: a frame per second for the whole cut, then full-size frames at every event, labelled with the word each is
   meant to land on.
