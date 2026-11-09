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
    covered text on most slides of one real deck.
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
  override, `--face-side top` if the camera is on top). The camera region is not 9:16, so for a vertical cut pass
  `--reframe 1080x1920`: it crops the camera region to 9:16 around the measured face and scales it up (a 1080x780
  region is ~2.5x, visibly softer; say so in the report). Split every clip into one folder with `--out-dir`, keep the
  screen files apart with `--screen-dir`, then `init_workspace.py <that folder>`. Never let a recorder's script
  view reach the cut.
- `--backup` (side by side only) makes the plain "slides with a face cam" version immediately, so a human editor has something to cut if
  the motion edit is not used. Keep the slides' bottom-right corner clear for the bubble, or use `--inset`.

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
