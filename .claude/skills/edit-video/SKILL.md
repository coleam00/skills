---
name: edit-video
description: Edit talking-head footage into a finished video with a script-driven pipeline the agent can verify without watching. Takes one recording or a folder of numbered clips, cuts it tight (no dead air, no breaths, no clipped words), places cut points with forced alignment instead of trusting Whisper timestamps, removes pauses and slips inside takes, hides jump cuts with punch-ins and split edits, adds scene-change transitions to screen recordings, burns in word-highlighted captions, builds motion-graphics B-roll with HyperFrames, inserts finished segments such as an ad read, and exports a loudness-normalised, sync-checked MP4 plus an .srt. Works for vertical Shorts, Reels and LinkedIn, 16:9 YouTube, course lessons and workshops. Use when the user says "edit this video", "cut these clips", "tighten this recording", "make a short from this", "add captions", "add B-roll" or "motion graphics", "stitch my screen recording", "insert this ad read", or runs /edit-video.
argument-hint: "<video file | folder of numbered clips>"
---

# Edit video

**Input:** `$ARGUMENTS`, one recording or a folder of clips named in order (`1.mkv`, `2.mkv` or `take_03.mp4`).

The job is a video the speaker would upload without re-cutting it. The agent cannot play video, so every stage
ends with a check that produces something readable: a word diff, a table of numbers, a frame grid. A stage is done
when its check passes and the evidence has been read, not when the script exits 0.

`S` below is `${CLAUDE_SKILL_DIR}/scripts` (set it in each shell call; it does not persist). Every script takes the
workspace as its first argument and runs the same way: `uv run --project $S python $S/<script>.py <ws> ...`.
Every script prints its usage with `--help`.

**One Python environment for every edit:** `$S/.venv`, built from `$S/pyproject.toml`. Never create a venv in a
workspace. Optional extras: `cuda` (Windows + NVIDIA) and `align` (torch for forced alignment); install them with
`uv sync --project $S --extra <name> --inexact`. Installed as a plugin, `$S` is inside the plugin's versioned cache folder, so the
environment (about 500 MB) is rebuilt after each plugin update; uv's cache makes that take seconds, but re-add any extras.

**On a new machine, run `doctor.py` first.** It checks ffmpeg and its filters, CUDA, NVENC, Node, fonts and the
Python packages, and says which parts of the pipeline will work. Everything runs on CPU; a GPU makes
transcription several times faster.

## Which edit is this?

Decide from what the user gave and said. If it is not clear, ask one question.

| Content | Steps | Read |
|---|---|---|
| **Clean talking-head cut** (one take or many, no graphics) | 1-5, 9 | `references/cutting.md` |
| **Screen recording + face bubble**, stitched with scene-change transitions (a push) | 1-6, 9 (`--no-punch`) | `references/transitions.md` |
| **Separate face and screen files per take** (face panel or bubble over the screen) | 1-5 (`--no-punch --screen <folder>`), `screen_bubble.py`, 6 (a push on the composite, if it changes scene), 9 (`export_final.py`) | `references/formats.md`, Talking head + slides; `references/transitions.md`, Separate face and screen files |
| **Same, with animated inserts where the speaker leaves the slides to show the product** | 1-5 (`--no-punch --screen <folder>`), 7, `screen_spans.py`, 8 (SCREEN + PIP with `S.shot`), 9 | `references/screen-inserts.md` |
| **Vertical Short** with captions, optional B-roll | 1-5, 7, 8, 9 | `references/captions-and-broll.md`, `references/formats.md` |
| **Vertical Short from a stacked canvas** (screen/script on top, camera band below) | `split_wide.py`, then 1-5, 7, 8 (contiguous SPLIT beats, the band never empty), 9 | `references/formats.md`, Stacked layout |
| **Long-form with motion-graphics B-roll** (16:9 talk, course, workshop) | 1-5, 7, 8, 9, one section first | `references/formats.md`, `references/captions-and-broll.md` |
| **Inserting a finished segment** (ad read, intro) into any of the above | after step 2: `insert_segment.py` | `references/cutting.md`, Inserts |

**Look at one frame of every source before step 1.** The pipeline assumes the camera fills the frame. Separate
camera and screen files per take are supported (`assemble.py --screen`, synced by their audio), as is one recorder
canvas holding both, side by side or stacked (`split_wide.py`): split those first and run everything else on the face
files. A stacked canvas keeps its camera band at native size (the stacked layout, written to config.json by
`split_wide.py` + `init_workspace.py`) instead of being upscaled to full frame. See `references/formats.md`.

Rarer jobs, each with its own file in `references/advanced/`: premium 3D-styled motion graphics
(`motion-graphics-3d.md`), re-rendering a website so a locked voiceover gets new screen visuals (`dynamic-screen.md`),
and repairing recorder audio dropouts (`audio-repair.md`).

## Basic or full

**Basic is the default:** everything runs on this machine and nothing leaves it. **Full** adds models through one
OpenRouter key, and runs only when the user asks for the full pipeline or names one of its steps. Never because a key
happens to be set: full sends the unpublished footage, and for a voice fix a sample of the speaker's voice, to outside
providers.

| Full step | What it does | Run |
|---|---|---|
| Transcription | Every transcription in the pipeline (first pass, cut-point checks, validation) goes to an OpenRouter model instead of the local GPU | `openrouter.py <ws> enable`, before `transcribe.py` |
| Video review | A video model watches the export and returns timestamped notes; `--model` swaps the reviewer | `video_review.py <ws> <export>` after step 9 |
| Thumbnail concepts | One brief, the speaker's face as a reference, several image models, the cost of each image | `thumbnails.py <ws> "<brief>"` |
| Fixing a word | A misspoken word or line regenerated in the speaker's cloned voice and spliced in, verified by transcription | `fix_word.py <ws> <clip> <start> <end> "<line>"` (consent first) |

`openrouter.py <ws> costs` prints what every call cost. Models, measured costs and the traps: `references/openrouter.md`.

## 0. Ask first (one message, then go)

1. **Deliverables:** clean cut, captions, B-roll? One version or variants to compare? Burned captions or an .srt?
2. **Approved script?** Copy approved by a client or brand partner is reproduced verbatim. Nothing added (no disclosure
   line, no call to action) unless asked.
3. **Brand:** neutral dark by default; otherwise colours and fonts go in `<ws>/brand.json` (`examples/brand.json`).

Then work without further check-ins until there is something to show.

## 1. Workspace and transcript

```
uv run --project $S python $S/init_workspace.py "$ARGUMENTS" --out <ws>   # config.json; --match "<glob>" picks the camera files
uv run --project $S python $S/pad_takes.py <ws> [--long "<glob>"]        # separate camera files: takes cut off at either end
uv run --project $S python $S/transcribe.py <ws>                          # faster-whisper large-v3, word timestamps
```

Pass `--out`: the default workspace is `<folder>/_edit` and finals default to `<folder>/final`, inside the source
folder, where another edit of the same footage may already live. A recorder that writes camera, screen and composite
files per take into one folder takes `--match` (`references/formats.md`, Talking head + slides). With separate camera
files, `pad_takes.py` runs before transcribing: a camera file that starts late or stops early while the speaker is
talking clips those words, and no later gate can hear it (`--apply` rebuilds those takes from the longer recording;
`--inset x,y,w,h`, the camera's box inside it, keeps the face moving over a restored head).

**Pass:** the printed transcript is read end to end. Retakes, false starts, asides and contradictions (a date or
price said two ways) are noted. Contradictions go in the report as questions; the edit keeps what was said.

## 2. Cut points

```
uv run --project $S python $S/cutpoints.py <ws>           # heads, tails, joins; RETAKE? lines
uv run --project $S --extra align python $S/align.py <ws> <segment> head|tail   # before hand-moving any cut
```

Decisions go in `<ws>/overrides.json` (`drop`, `in`, `out`, `video_out`, `splice`; `examples/overrides.json`).
Keep the better take of every `RETAKE?` pair (usually the later). Never drop a sentence for redundancy alone.

**Pass:** every `RETAKE?` resolved; every hand-set `in`/`out` placed with `align.py`, not with Whisper's times.

## 3. Dead air and slips inside takes (every edit)

```
uv run --project $S python $S/pauses.py <ws>                        # quiet stretches >= 0.6 s, REPEAT / RESTART lines
uv run --project $S python $S/pauses.py <ws> --min 0.55 --apply     # splice each to 0.25 s, then re-run cutpoints.py
```

`cutpoints.py` only trims heads and tails; the swallow or the second spent remembering a line sits mid-take. A pause
waiting for something on screen is still cut; only a deliberate beat stays. Repeats are candidates: Whisper invents
doubled words, so confirm each on the raw audio before splicing (`retranscribe.py <ws> <clip> <start> <end> --no-prompt`;
`references/cutting.md`, Slips).

**Pass:** no internal pause over ~0.6 s left except deliberate beats; every splice confirmed on the raw clip.

## 4. Eyes and split edits

```
uv run --project $S python $S/eye_strip.py <ws>      # check/eyes_<seg>_{tail,head}.png
```

Read every strip. If the speaker looks away before a segment's last word ends, set its `video_out` to the last frame
with eyes on the lens: the picture cuts early, the audio plays on.

**Pass:** eyes on the lens through every picture out point.

## 5. Assemble and validate

```
uv run --project $S python $S/assemble.py <ws> [--level] [--no-punch] [--tag v1]
uv run --project $S python $S/validate_cut.py <ws> [--tag v1]
```

**Pass (all, every time):** word diff shows only ASR spelling variants; 0 joins flagged (`DEAD AIR` > 0.3 s,
`ON SOUND` < 0.03 s); 0 `TAIL ON SOUND`; `check/joins_<tag>.png` shows no blink, look-away or mid-gesture jump;
per-segment loudness within ~1.5 LU (otherwise `--level`). Never override `TAIL ON SOUND` because a re-transcription
still prints the word. Pacing targets and the failure table: `references/cutting.md`.

A finished segment goes in with `insert_segment.py <ws> <file> --after <segment>` before this step; assemble with
`--level`.

## 6. Scene-change transitions (screen recordings)

```
uv run --project $S python $S/transitions.py <ws> detect                  # -> transitions.json + check/transition_joins.png
uv run --project $S python $S/transitions.py <ws> render --tag v1         # a push at every join -> cut/transitions_v1.mp4
```

The default transition is a **push**: the whole frame slides out to the right while the next clip slides in from the
left, motion-blurred, about 0.35 s, with a quiet whoosh peaking on the picture cut. Because everything is moving, the
speaker's glance at the record button at the end of a take, or their settling at the start of the next, cannot be
seen: no room tone, no held face, and transition joins keep ordinary cut tails (heard pause ~0.2-0.35 s). Separate
face and screen files: run `screen_bubble.py <ws> --tag v1 [--panel]` first, then `render`; the push moves the whole
composite. The agent decides the joins from the contact sheet, not the threshold: only where the scene changes AND a
thought ends. **Pass:** every remaining join is a real scene change at a sentence end; a frame strip across every push
shows the incoming clip on the left and the outgoing on the right at mid-push (never the next screen on both halves),
and the frames just outside each push match the untouched cut. The soft wipe (`--kind smoothleft`, with `room` and the
bubble hold) is still available; `references/transitions.md`.

## 7. Captions

```
uv run --project $S python $S/captions.py <ws> [--tag v1]
```

Captions show what was said. Fix ASR spellings in `<ws>/caption_fixes.json`, never by paraphrase.
**Pass:** every printed phrase read; names spelled right and never split; nothing on screen under 0.5 s.

## 8. B-roll (HyperFrames)

```
cp ${CLAUDE_SKILL_DIR}/templates/schedule.py <ws>/schedule_broll.py      # write the plan table first, then the beats
EDIT_VIDEO_SCRIPTS=$S uv run --project $S python <ws>/schedule_broll.py <ws>
uv run --project $S python $S/render.py <ws> broll --quality draft
uv run --project $S python $S/review.py <ws>/hf/broll/out/broll_draft.mp4 <ws>/check/rev.png --beats <ws> broll
```

Anchor every element to a spoken phrase (`tk.at("...")`), never typed seconds. Long-form: render one section first.
**Pass:** lint 0 errors, inspect clean, 0 `SHORT DWELL`, 0 `EMPTY BAND` (stacked layout: the graphics band always
holds a beat or a topic card; the report, then `empty_card.py <render> --ws <ws> --min 2`), every beat grid read: each graphic matches its words, lands
on its word, nothing clipped or overlapping, the face never covered or flashed at a cut.

## 9. Finalize and verify the exported file

```
uv run --project $S python $S/finalize.py <ws> broll <Name> [--tag v1]    # B-roll page: high render, loudness, sync, .srt
uv run --project $S python $S/finalize.py <ws> --clean <Name> [--tag v1]  # the clean cut alone (the tag defaults to v1)
uv run --project $S python $S/export_final.py <ws> <tag> <dest> <Name>    # transitions render (step 6) or screen_bubble.py output
uv run --project $S python $S/insert_segment.py <ws> --check <file> --tag <tag>   # only if a segment was inserted
```

Run `captions.py` for the tag first even when nothing is burned in: the .srt comes from it.
**Pass:** sync `0.0 ms` at all four probes; about -14 LUFS, true peak at or under -1.5 dBTP; duration equals the clean
cut (plus the 1 s end hold where used); `ffprobe` shows source resolution and fps, H.264 + AAC; frames read from
the exported file itself, not an intermediate.

## Hard rules

- **Never overwrite** a source file or an earlier export. Every version gets a new number or folder.
- **Whisper's timestamps place nothing.** Word ends run 50-300 ms early and Whisper completes words from their first
  half. Cuts between words come from `align.py` plus the waveform; ASR is a second check, never proof.
- **Read the evidence.** Frame grids, word diffs and numbers are how the agent watches. Never call a cut or a render
  good without having read the PNGs and the diff.
- **Prove the output, not the plan:** re-transcribe the cut and diff the words; check the exported file.
- **Gates before slow renders.** Lint, inspect, a sample window or one section, then the full render.
- **Approved copy is verbatim.** List every wording difference in the report; never fix one silently.
- **One heavy GPU job at a time.** Check `nvidia-smi` before starting a render or transcription on a shared machine.

How the agent sees, gate by gate: `references/verification.md`. The reasons behind every rule: `references/lessons.md`.

## Report

Lead with the output paths. Then duration, loudness, sync result, what was checked and how (which sheets, which
numbers), every wording difference from an approved script, and anything not verified or deliberately left. Name
anything that only a human can judge (motion feel, sound) as theirs to check.

## Resources

- `scripts/`: the pipeline, in the order above. `doctor.py` (environment check), `align.py` (forced-alignment cut
  points), `retranscribe.py` (re-transcribe any window: a suspected repeat, a word-diff line), `insert_segment.py` (finished segments, and the post-export check around them), `split_wide.py` and
  `screen_bubble.py` (side-by-side recordings, slides + face version), `pad_takes.py` (camera files that start late or stop early),
  `screen_spans.py` (where the screen leaves the slides), `face_track.py` (face panel follows the face),
  `empty_card.py` (blank-card stretches), `flicker_check.py`, `fix_skips.py` and `swap_audio.py`
  (`advanced/audio-repair.md`), `page_render.py` (`advanced/dynamic-screen.md`), `make_whoosh.py`.
  `scripts/hf/`: the HyperFrames B-roll kit (`engine.py` layouts, `scenes.py` and `motion.py` scene library,
  `style.py` tokens and captions, `rough.py` hand-drawn marks).
- `templates/schedule.py`: starting point for a B-roll schedule. `assets/sfx/whoosh.wav`: the default transition sound.
- `examples/`: `brand.json`, `config.json`, `overrides.json`, and a README explaining every key.
- `references/cutting.md`: the cut-point algorithm, overrides, pacing, slips, levels, inserts, failure table.
- `references/verification.md`: frame grids, word diffs, crops, every gate in one table, checking the export.
- `references/transitions.md`: where transitions go, the face bubble across a wipe, the whoosh, ffmpeg traps.
- `references/captions-and-broll.md`: caption rules, layouts, timing, scene catalogue, HyperFrames traps.
- `references/screen-inserts.md`: animated product shots (`S.shot`) over the spans a recorded screen leaves the slides.
- `references/formats.md`: vertical vs 16:9 vs long-form, recording setups, render economics.
- `references/lessons.md`: the lessons behind the rules, grouped by topic.
- `references/openrouter.md`: the full pipeline: models per step, what each sends out, measured costs, traps.
- `references/advanced/`: `motion-graphics-3d.md`, `dynamic-screen.md`, `audio-repair.md`.
