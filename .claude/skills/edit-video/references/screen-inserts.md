# Screen inserts: animated product shots over a recorded screen

For a talk taught from slides or a diagram, recorded as separate camera and screen files, where the speaker leaves the
slides now and then to show the product (a browser, an editor, a terminal). Those spans become animated inserts built
from frames of the screen recording: push-ins, rings and a spotlight timed to the words. The slide or diagram spans
stay as recorded, and the face stays on screen throughout. Nothing is re-recorded or clicked again.

## Contents
- The rule: the edit fits the recording
- 1. Find the spans
- 2. Captures
- 3. The look
- 4. Schedule and boundaries
- 5. Render and check

## The rule: the edit fits the recording

The speaker talks naturally, in their own words, order and length. Read what was said in each span, then choose the
shots and their order from it, make each insert as long as its span, and anchor every move to a spoken phrase
(`tk.at(phrase, after=<the beat's start>)`; without `after` it finds the first mention in the whole video). Never ask
for a re-record or for set lines to say: an edit that needs the speaker to fit it defeats the purpose.

## 1. Find the spans

```
uv run --project $S python $S/screen_spans.py <ws> --tag <tag> --ref <s> --region x,y,w,h
```

`--ref` is a cut time on the slides or diagram; `--region` is a part of the frame only that app draws (its toolbar or
tool palette, read one frame to pick it). It prints every AWAY run with its nearest take joins. Most runs start and
end on a join (the speaker switched apps between takes); a run that starts mid-take is a real mid-sentence switch.
Read a contact sheet at each run's edges before trusting it.

## 2. Captures

- Grab frames from the cut screen track at the moment each state is settled (page loaded, no hover tooltip, no
  half-scrolled list): `ffmpeg -ss <cut s> -i <ws>/cut/screen_<tag>.mp4 -frames:v 1 <ws>/shots/<name>.png`. Full
  resolution, PNG. One capture per state; a state change (Approved, a new row, an error appearing) is a `swaps` entry.
- Reject a capture with a crushed pane, text wrapping word by word, a button label broken over two lines, or the
  element you will point at cut off. When the recording only has a bad one, push in on the part that reads.
- Personal data (emails, IPs, keys, city) is blurred in the capture before it goes on screen.
- Every name and number on screen comes from the footage. Code and terminal shots keep their real lines.

## 3. The look

`S.shot(tk, sid, tk.pip_box, png, t0, crop=..., zooms=[(t, rect)], rings=[(t, rect)], spots=[(t0, t1, rect)],
swaps=[(t, png)])`, rects in the capture's pixels:

- **Push-ins** ease 0.9 s onto the region being talked about, at most 1.9x the capture's own pixels (softer beyond).
  The camera is clamped to the capture, so a held frame never slices text at its edge; frame whole elements.
- **Rings** draw on around the one element the words name, on that word. A ring, never an underline or a box edge
  across lines of code: a mark through text reads as a strikethrough.
- **Spotlight** dims everything else to half for the one thing that matters; **swaps** crossfade to the next state.
- **No headlines, place labels, badges or numbering** above or on a shot. They land on the app's own controls and the
  voice already says where we are; a headline over every insert was the first thing a real review rejected.
- A text-only card belongs only where the words carry an idea nothing on screen shows, and never over a slide span.
- Hold the current shot to the end of its span rather than cutting to another in the last ~2 s (two cuts under 3 s
  read as choppy). Check the smallest text at the size it plays, not at full frame.

## 4. Schedule and boundaries

- SCREEN for the slide spans (the recorded screen + the face), PIP for the inserts. A recording that opens on the
  slides starts the page with `tk.screen(0.0)`: the screen and the small face are there from the first frame.
- The recorded screen changes at the take joins, not at the words. `tk.pip` and `tk.screen` near a join snap to it:
  the insert has fully covered the screen 0.05 s before the join and the screen returns exactly on it, so the wrong
  take's raw screen never shows (it read as a glitch). For a mid-take switch, start the insert at least 0.55 s
  before the AWAY start that `screen_spans.py` printed.
- The face over the slides: a corner bubble or the panel sits over the slide's right side. Read the slide frames
  under it; a full-width diagram had its last caption covered in 40% of sampled frames. Move or size the face where
  the slides leave room, and say in the report what it still covers.

## 5. Render and check

- Build, then `render.py <ws> broll --fps 6` and read `review.py --beats` sheets before any full render.
- At 60 fps a 15-minute page renders for hours (about 2 h on one GPU machine). Start the high render detached, in
  its own shell with its output in a log, so an agent session ending does not kill it:
  `render.py <ws> broll --quality high --out <ws>/hf/broll/out/broll_final_raw.mp4 --skip-inspect`. Review each chunk
  as it lands, then `finalize.py <ws> broll <Name> --use-raw` picks that file up instead of rendering again.
- Read a frame grid at every span boundary of the final (±0.1 s): no raw product frame, no flash of the slides.
