# Transitions

A push and a quiet whoosh where a recording changes scene, plus everything that keeps them invisible as edits. The
same rules apply to a screen recording with a face-cam bubble, a face panel over slides, or a plain talking head.

## Contents
- Where transitions go
- The push (default)
- Pacing at a transition join
- The face bubble across a wipe
- Separate face and screen files
- Wipe speed and style
- The whoosh
- Changing the list later
- Lower-third card
- ffmpeg traps

## Where transitions go

- **Only at a clip join where the scene changes** (a different app, page or diagram) **and a thought ends.** A
  scene change where the sentence carries on into the next clip gets a plain cut: a whoosh mid-sentence reads as an
  error. Expect about one every couple of minutes, plus both joins of any inserted segment.
- **Never inside a clip.** A tab switch the speaker made while recording plays as recorded. Wiping every in-clip tab
  switch is the classic overdone first draft.
- A join that stays on the same screen (a scroll, a panel opening, a popover) is a plain cut.
- `transitions.py detect` proposes joins by pixel difference, but a panel opening scores the same as a page change.
  Read `check/transition_joins.png` AND the words across each join, then edit `transitions.json` by hand. The agent
  decides, not the threshold.

## The push (default)

`transitions.py render` (`--kind push`, `scripts/push.py`): the whole frame slides out to the right while the next
clip slides in from the left, locked edge to edge.

| Setting | Value | Why |
|---|---|---|
| Length | `--dur 0.35`, rounded to whole frames | 0.30-0.45 s all read well; shorter keeps the pace |
| Ease | smoothstep, fastest on the picture cut | the cut itself lands inside the fastest frames |
| Motion blur | rendered at 480 fps, 8 sub-frames averaged per 60 fps frame | blending neighbouring 60 fps frames gives ghosted copies, not blur |
| Edge holds | outgoing held from 3 frames before the cut, incoming from 3 frames after | separate screen files can switch 1-3 frames off the picture cut; holding the frame right at the cut can put the next screen on both halves (a white flash with both halves sliding the same way) |
| Whoosh | `assets/sfx/whoosh.wav` at -6.4 dB, peak on the picture cut | the push's fastest point |
| Where | the picture cut (timeline `v_out_start`) | a split edit moves the picture cut; anchoring to the audio cut shows a hard cut and then a transition over the same screen |

**Why it is the default:** while the whole frame is moving, the speaker's glance at the record button at the end of a
take and their settling at the start of the next cannot be seen. So there is no `room` step, no held face and no
per-join look-away fix: transition joins keep ordinary cut tails (the last word's full decay plus ~0.08 s, ~0.15 s of
lead-in), a heard pause of about 0.2-0.35 s. Padding a transition join with room tone makes it hang, and holding a
large face (a panel rather than a small bubble) reads as a freeze.

**Layouts:** the push moves the whole picture, so it works the same over a baked-in bubble (for a fraction of a
second two bubbles pass each other, which reads as part of the motion), a face-panel composite and a plain talking
head. Separate face and screen files: run `screen_bubble.py` first, then `render`; the composite is kept as
`cut/composite_<tag>.mp4` so a re-render never pushes an already-pushed file. A `"card"` in transitions.json is drawn
ending as that join's push starts.

**Check every push:** a frame strip across each one (incoming on the left and outgoing on the right at mid-push, never
the next screen on both halves), the frames just outside each window equal to the untouched cut, and
`validate_cut.py` for the tails.

Everything from "Pacing at a transition join" to "Wipe speed and style" below is the **soft wipe**
(`--kind smoothleft`): its room tone, its pause centring and its bubble hold do not apply to the push.

## Pacing at a transition join

| Join | Heard pause |
|---|---|
| Plain cut | 0.15-0.25 s (references/cutting.md) |
| Transition join | 0.5-0.8 s; at 0.1-0.2 s the wipe feels rushed and the whoosh lands on the talking |

- `transitions.py room` adds up to `--tail` (0.45 s) of the outgoing clip's own room tone after the last word's
  decay. Heads are left alone by default: the second before someone speaks is usually a breath, and a breath is
  within a few dB of room tone. validate flags these joins `DEAD AIR`; expected.
- `render` centres each wipe and whoosh in the middle of the pause (last word -> next word), not on the picture cut:
  the room sits on the outgoing tail, so a wipe on the cut puts the whoosh tail over the next word.
- Never start a head inside a breath (broadband, little 100-900 Hz voicing). Move the in point to just before voicing.

## The face bubble across a wipe

Set `"bubble": [cx, cy, r]` in config.json (measured on a full-resolution crop) and assemble with `--no-punch`.

- **Both sides of the pause look away.** The speaker turns to stop the outgoing take right after the last word, and
  the incoming pre-roll starts with them still turning back from the record button: measured over 13 joins, only the
  last ~0.3 s before the first word was on the lens every time. So the bubble is **live, HELD, live**: the outgoing
  face plays until the last word ends (`--out-keep` 0.04 s), that frame holds through the middle of the pause (the
  wipe draws the eye), and the incoming pre-roll plays live for only `--in-pre` 0.30 s before the picture cut.
- A speaker who glances down before the last word ends gets a per-join freeze on the last on-lens frame:
  `"bubble": {"<incoming key>": {"out_keep": -0.33}}` in transitions.json.
- **Check every wipe, every time:** save render's output to `<ws>/transitions_<tag>.log`, run
  `wipe_bubbles.py <ws> <tag>`, and read every row. The look-away is invisible at contact-sheet scale; only the crop
  shows it. This is the most repeated failure of the stitch edit.
- (Soft wipe only.) The wipe keeps content in place, and the bubble is overlaid from the untouched cut so it never
  moves. The push instead moves everything, bubble included, which is why it needs none of this section.
- Mask the bubble out of every frame-difference measurement, or a talking face reads as a scene change.

## Separate face and screen files

A recorder that writes the camera and the screen as separate files per take (`assemble.py --screen`) gets the same
wipe, applied where it belongs:

```
transitions.py <ws> detect                     # compares the SCREEN files at every join (lag-shifted)
transitions.py <ws> room                       # then assemble.py <ws> --no-punch --level --screen <folder> --tag a2
transitions.py <ws> render --tag a2 > <ws>/transitions_a2.log
screen_bubble.py <ws> --tag a2 --panel         # uses the wiped cuts, writes cut/transitions_a2.mp4
wipe_bubbles.py <ws> a2                        # face crop + whole-frame thumbnail across every wipe
```

- `render` wipes `cut/screen_<tag>.mp4` into `cut/screen_wiped_<tag>.mp4` and writes `cut/face_wiped_<tag>.mp4`: the
  face cut with the whooshes mixed in and **live, HELD, live** at every join (outgoing face live to the last word,
  that frame held, the incoming pre-roll live for `--in-pre` before the picture cut), over the whole camera frame.
  Both are recorded in config.json `"wiped_cuts"`; `screen_bubble.py` uses them when they are newer than the plain
  cut and prints which it used.
- **The face switches inside the wipe.** With a baked bubble the face and screen are one picture; with separate files
  the panel could show the incoming take while the outgoing screen is still whole. `render` clamps the switch into
  the wipe window, so the panel and the screen change take together. Per-join `"bubble": {"<incoming key>":
  {"in_pre": 0.2}}` still applies (one test take was still settling its gaze 0.3 s before the cut; 0.2 s was on the lens).
- `screen_bubble.py` records the panel or bubble box as config.json `"face_box"`, which `wipe_bubbles.py` crops.
  Read every row: eyes on the lens on both sides, the thumbnail below each crop shows which screen is up.
- Lower-third cards come from `screen_bubble.py --card` here, not from transitions.json.
- Most joins in a run of takes over one document are scrolls: plain cuts, even when `detect` scores them as high as
  the real section change (7.1 vs 7.7 on one set). Decide from the sheet and the words.

## Wipe speed and style

- 0.34 s (`--dur`). 0.40 s read slow; under ~0.30 s a wipe reads as a jump cut with a sound effect. Change speed in
  small steps.
- `smoothleft` by default. `hblur` smears the whole frame and drags the bubble edge.

## The whoosh

`assets/sfx/whoosh.wav` is the default: synthesised pink noise, 0.33 s, peak at 0.21 s, band-pass opening from
140-300 Hz to 220-880 Hz at the peak, spectral centroid ~560 Hz, panned left to right. `render` mixes it at
`--whoosh-db -6.4`, peak on the wipe centre: about -30 dB in the pause against a -14 LUFS voice, felt more than heard.
`make_whoosh.py` reproduces it bit for bit (seeded) and is where a new one is tuned.

What the search for that sound taught: bright sweeps (centroid ~3 kHz) read as "whish"; brown noise and long
(~1 s) sounds read as deep and exaggerated; ~850-930 Hz read as too high. Subtle, short, airy and mid-low won.

**Auditioning a new sound:** never swap blind. Cut a 6 s clip around one real transition per candidate (same picture
and voice, only the sound changes), loudness-match them, name files `<round>_<letter>_<description>.mp4`, report
length and spectral centroid per option, and let the speaker pick. Give every synthesised option its own seed, or
adding options silently changes earlier files. If a sound must match a library one, ask for the file (and check its
licence) rather than iterating synthesis. Applying the pick is an audio-only remix (`-c:v copy`).

## Changing the list later

- `room` extends EVERY join in transitions.json from its current out point. To add one join, run `room` with only
  that join in the file, then restore the full list.
- To remove one, delete it and set the outgoing `out` back to a plain-cut tail (`end` + ~0.15) in both cuts.json and
  overrides.json.
- Re-assemble with a new `--tag`, re-validate, re-render, re-run `wipe_bubbles.py`.

## Lower-third card

An optional line of text before a join, for example "Up next: the architecture" before an inserted segment. In
transitions.json:

```json
"card": {"before": "m01_s01", "text": "Up next: the full architecture", "secs": 6}
```

White text in a black box, bottom centre, fading in, ending as that join's wipe starts so it never hangs over the
transition. `screen_bubble.py --card` draws the same thing for the slides + face version. Font: `"font": "<path>"`
in the card, else the first bold system font found (`EDIT_VIDEO_FONT` overrides). Check it in the frames: readable at
phone size, clear of the bubble and of anything important on screen, gone before the wipe.

## ffmpeg traps

- `xfade` custom `expr` with `st()`/`ld()` races across slice threads: garbage stripes and ghosting. Inline the
  expression, and run xfade in `yuv444p` so every plane has the same size.
- `zoompan` on video: `d=1`, set `fps`, and upscale 2x before it to halve integer-position stepping.
- `crop` past the frame edge is clamped without an error, moving the box. Use `exact=1` and assert it fits.
- `alimiter` adds a 5 ms lookahead delay unless `latency=1`; the sync probe catches it.
- Old exports with millisecond-rounded timestamps repeat and skip frames when reused: retime by frame number
  (`setpts=N/(FPS*TB)`) first.
