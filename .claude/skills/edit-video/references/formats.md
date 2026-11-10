# Formats

The pipeline reads size and fps from the source and derives every layout from the measured face. What changes by
format is the density of the edit, what is worth rendering, and how the footage was recorded.

## Contents
- At a glance
- Vertical shorts
- Long-form economics
- Screen recordings with a face bubble
- Talking head + slides (separate camera and screen)
- One wide canvas
- Stacked layout (camera band at native size)
- Course and workshop footage
- Start and end

## At a glance

| | Vertical short (Shorts, Reels, LinkedIn, TikTok) | 16:9 short (promo, ad, landing page) | Long-form (YouTube, course lesson, workshop) |
|---|---|---|---|
| Length | 30-120 s | 30-180 s | 5-90 min |
| Cut | tight joins, every breath out | same | same algorithm; sentence ends at the top of the join range |
| Captions | burned in, 22-26 chars per phrase | burned in, 34-42 chars | usually an .srt upload (`"captions": "srt"`) |
| B-roll | 55-70% of runtime, a third FULL | 40-60% | targeted, or 50-65% counting PIP for a talk made into motion graphics |
| Graphic layout | face slides up, graphic below (SPLIT) | FACE / PIP / short FULL | FACE / PIP; FULL only with no PIP |
| Loudness | -14 LUFS | -14 LUFS | -14 LUFS (-16 if a platform asks) |

## Vertical shorts

- Captions sit on the shirt below the chin; the face keeps its headroom in SPLIT.
- The first graphic lands within ~10 s and every graphic beat moves; a short with long static text cards reads as
  slides.
- Do not end by snapping back to the full camera on the last word: hold the last graphic or the link.

## Long-form economics

- Renders are the cost. At ~3x real time a 30-minute B-roll page is a 90-minute draft. Render one section first,
  review it, fix the patterns, then render the rest; use `render.py --fps 6` previews for layout checks.
- The ASR tail probe costs a few seconds per segment and a long single recording has hundreds: run
  `cutpoints.py --no-asr` for a first pass to find retakes and structure, then the full probe for the final cut.
  On a CPU-only machine this matters more.
- Retakes are the main editing work in a long single recording. Read every `RETAKE?` pair, and run the slip search on
  every clip (`references/cutting.md`).
- Keep the word diff: it is the only practical proof that no sentence was lost.

## Screen recordings with a face bubble

The bubble is baked into the frames.

- `assemble.py --no-punch`: a punch-in would crop the screen content.
- `"bubble": [cx, cy, r]` in config.json, measured on a full-resolution crop. The transition renderer overlays the
  bubble from the untouched cut, and the eye check crops the bubble instead of the frame.
- Transitions only at scene changes that end a thought (`references/transitions.md`).
- Finish with `export_final.py` (no B-roll layer): hold + fade, loudness, sync check, .srt.

## Talking head + slides (separate camera and screen)

A recorder writing the camera and the screen as separate files per take (both carrying the mic) is the cleanest
setup: full-resolution face, full-resolution slides.

- Put the camera files in the clip folder (`clips/01_face.mkv`, ...) and the screen files in their own folder with
  matching names (`_face.` -> `_screen.` or `-face ` -> `-screen `), in recording order.
- `assemble.py <ws> --screen <screen folder>` cuts the screen track with the face's exact picture trims and syncs each
  pair by cross-correlating their audio: separate files start up to ~0.8 s apart, differently every take.
- Then either deliverable:
  - **Slides + face panel (no B-roll):** `assemble.py <ws> --no-punch --level --screen <folder> --tag a1`,
    `screen_bubble.py <ws> --tag a1 --panel` (check the look first with `--secs 20`), `export_final.py`.
    A deck that uses its full width needs the panel or `--inset 0.75`: a corner bubble over full-frame slides
    covered text on most slides of one real deck. `screen_bubble.py` samples the screen under the bubble and prints
    `WARN the face covers screen content` when text or UI sits there; a document column reaching the right edge
    triggered it, and `--panel` cleared it.
- `transitions.py detect` compares the SCREEN files at each join (the face files are one set and never change).
  A join that only scrolls the same document is a plain cut, so a run of takes over one document usually has no
  transition. Where the screen really changes (a new page, app or section) at the end of a thought, the wipe works
  on separate files too: `transitions.py room`, re-assemble with a new tag, `transitions.py render --tag <tag>` (wipes
  the screen cut, gives the face track the live, HELD, live switch inside each wipe), then `screen_bubble.py --tag
  <tag> --panel` picks both up. references/transitions.md, Separate face and screen files.
  - **Face + motion graphics:** the normal punch-in cut and a B-roll page, layouts FACE / PIP, SCREEN where the real
    slide or demo is the best picture.
- Recorded files can drift or end early; check the face file's duration against the screen file's, and read the
  sync of a few frames by eye.

## One wide canvas

The alternative: one 3840x1080 recording, camera on one half and screen on the other, one clock, no sync step.

```
uv run --project $S python $S/split_wide.py <recording.mkv> --backup   # <stem>_face.mp4, <stem>_screen.mp4, <stem>_backup.mp4
uv run --project $S python $S/init_workspace.py <stem>_face.mp4          # everything else runs on the face file
uv run --project $S python $S/assemble.py <ws> --screen
```

- Record the mic only (no desktop audio: notification sounds end up in the cut), NVENC or similar at high quality,
  keyframe every second, mkv (survives a crash).
- **Stacked canvas** (taller than wide: screen on top, camera below, common for a vertical recorder scene with the
  script or a teleprompter doc on screen): `split_wide.py` detects it, finds the seam and prints it (`--split-at Y` to
  override, `--face-side top` if the camera is on top). Use the stacked layout below. Never let a recorder's script
  view reach the cut.
- `--backup` (side by side only) makes the plain "slides with a face cam" version immediately, so a human editor has something to cut if
  the motion edit is not used. Keep the slides' bottom-right corner clear for the bubble, or use `--inset`.

## Stacked layout (camera band at native size)

A stacked recording's camera region is a band (1080x782 of a 1080x1920 canvas), not a 9:16 frame. Blowing it up to
full frame is a ~2.5x upscale: soft, and the strongest punch-in clips the hair. The stacked layout keeps the camera at
native size in its own band and uses the rest of the canvas for graphics:

```
uv run --project $S python $S/split_wide.py <clip> --out-dir <faces> --screen-dir <screens>   # per clip; writes <faces>/layout.json
uv run --project $S python $S/init_workspace.py <faces>      # prints "layout stacked: ..."; config.json gets "layout"
```

- The cut (steps 1-7) runs on the band itself. `layout.json` (`{"mode": "stacked", "w": 1080, "h": 1920,
  "face_side": "bottom", "seam": 1138}`) puts the canvas size in config.json; the band's height sets the seam, so a
  1080-wide band lands exactly where the recorder had it.
- B-roll page (step 8): the face sits in its band, unscaled, the whole video. `tk.split()` + `tk.pscene()` put a
  graphic in the band above the seam (`tk.page_box`, ~940x850); FACE leaves that band on the dark background; a thin
  lit line marks the seam. Captions sit just above the seam on the graphics side, never on the face. Use SPLIT for
  every beat: `tk.full()` works but hides the face, which is the point of the layout. `tk.pip()` / `tk.screen()` raise
  (the face already has its band; the screen half is usually a script view).
- **The graphics band is always occupied.** With the face parked in its band, a FACE beat leaves the other band as
  plain background, and in a vertical frame an empty band reads as unfinished (one test Short sat empty at 0-5 s,
  19-22 s and 48-57 s). Run beats back to back with `tk.band(t, sid)` (enters SPLIT or swaps the scene), start the
  first beat at 0.0, and where nothing new is said hold a topic card instead of calling `tk.face()`:
  `S.title_card(tk, sid, tk.page_box, "<section title>", t, kicker=..., sub=..., t_sub=tk.at(...))`, words from
  what is being said. The build report prints `EMPTY BAND a-b` for every stretch over 2 s without a beat, or
  `band occupied`; on the render, `empty_card.py <video> --ws <ws> --min 2` measures the band itself (it also
  catches a scene that swaps in long before its first element lands). The 55-70% B-roll target does not apply: the face is on screen the whole time, so ~100% is right.
- FACE beats grow the band to full frame only when that is an upscale of at most 1.2x (config.json `"layout"`
  `"max_upscale"`), i.e. when the band is nearly the canvas. For a 1080x782 band (2.46x) the band stays.
- The build report prints the geometry and the largest upscale: band scale x the largest take punch-in (the alternating
  punch-in that hides jump cuts is ~1.10x on alternate takes; `assemble.py --no-punch` keeps every take at 1.00x and
  shows the jump cuts). `UPSCALE` is printed over 1.2x.
- Deliverable: `finalize.py <ws> broll <Name>` renders the 1080x1920 canvas. `finalize.py --clean` exports the band
  alone (1080x782), which is not a vertical video.
- `--reframe 1080x1920` (the old route: crop the band to 9:16 and upscale) is only for a deliverable that must be a
  plain full-frame talking head; say in the report that the face is upscaled.

## Course and workshop footage

- Never cut a code walkthrough mid-command: a pause while typing is content. `cutpoints.py --max-pause 3`.
- Lists and frameworks are where B-roll pays off; a checklist or a map that matches the spoken structure helps people
  remember it. Talking points between them can stay on the face.
- The terminal scene should show the real commands and output from the run being described.

## Start and end

- The first word within ~0.1 s of frame one.
- Speakers look down to stop the recording right after the last word, so there is no real footage to extend.
  `export_final.py` (and `finalize.py --hold`) holds the last good frame 1 s under a 0.7 s fade instead.
- Deliverables: `final/<Name>_vN.mp4` plus `.srt`, never overwriting an earlier version.
