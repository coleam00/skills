# Verification: how the agent watches

The agent cannot play a video or hear it. Everything it knows about a cut comes from four kinds of evidence, and a
stage is done only when the evidence has been produced AND read. "The script exited 0" is not evidence.

## Contents
- The four ways to see
- Frame grids
- Word diffs
- Crops
- Numbers
- Every gate in one table
- Checking the exported file
- Before saying done

## The four ways to see

| Evidence | Answers | Tool |
|---|---|---|
| Frame grids | does it look right at this moment? | `review.py`, `eye_strip.py`, `validate_cut.py` (joins sheet), `transitions.py detect` sheet |
| Word diffs | was anything lost, doubled or clipped? | `validate_cut.py`, `retranscribe.py` (any window) |
| Crops | is the small thing right (a bubble's eyes, a caption edge)? | `wipe_bubbles.py`, `ffmpeg -vf crop=...` |
| Numbers | is the timing, level or sync right? | join table, LUFS, sync lags, `align.py`, `empty_card.py`, `flicker_check.py` |

Motion feel and sound quality are not on this list. Say so in the report; they are the human's to judge.

## Frame grids

- At most 18 frames per sheet, so each frame stays legible. `review.py` splits longer lists into numbered sheets.
- Choose times on purpose: a scene's entry (+0.15 s) and settled state (+1.2 s), ±2 frames around every picture cut,
  and the moment a word is supposed to land. `review.py --beats <ws> <name>` picks all of these from the page.
- Read them in time order. Name what each frame should show before looking, then check it does.
- Thumbnails mislead in both directions: a mid-move card can look like a jump, and a 250 px face bubble's look-away
  is invisible at sheet scale. When a thumbnail is ambiguous, render that frame full size.
- The sweep for dense problems (flicker, an element hopping a pixel) is a run of consecutive frames, not a grid.

## Word diffs

- `validate_cut.py` re-transcribes the finished cut and diffs it word by word against the source transcripts.
  On a long recording it is the only practical proof that no sentence was lost and none was repeated.
- Acceptable: ASR spelling variants (`lifecycle` / `life cycle`). Not acceptable: a missing or changed final word
  (a clipped tail), a doubled phrase (a cut that replays audio), a missing word inside a splice.
- A clean diff does NOT prove a word is whole: Whisper completes a word from its first half. That is why
  `TAIL ON SOUND` and `align.py` exist. Never override a waveform finding with a transcript.
- Before splicing out a "repeat", re-transcribe the raw window with no prompt: Whisper invents doubles.
- Settle every DIFF line the same way, on the raw clip AND on the cut: a word the raw clip says too is an ASR variant
  of the source transcript, not an edit error.

```
uv run --project $S python $S/retranscribe.py <ws> c03 16 21.6 --no-prompt    # a clip, seconds in the clip
uv run --project $S python $S/retranscribe.py <ws> cut:v1 52 57.2             # the cut, output timeline
uv run --project $S python $S/retranscribe.py <any file> 10 14                # an export, an insert, a raw file
```

  It pads 1 s of silence before the window (a first-frame word is otherwise misheard) and prints each word with its
  time and probability. The times are a second check, never cut points.

## Crops

Crop to the thing being judged, at full resolution:
- **Face bubble at a wipe:** `wipe_bubbles.py` crops the bubble from 0.4 s before the last word to past the picture
  cut, every 67 ms, one row per join. Every frame: eyes on the lens.
- **Eyes at a cut:** `eye_strip.py` crops the eye band every 2nd frame around each tail and head. With a face-cam
  bubble on a screen recording, crop the bubble instead (config.json `bubble`).
- **Captions and cards:** crop the caption band of the frames where a caption starts and ends; check nothing touches
  the frame edge or the face.
- **Anything near an edge:** crops in ffmpeg clamp silently at the frame edge (`crop` past the frame moves the box
  without an error). Use `exact=1` and assert `x+w<=W and y+h<=H`.

## Numbers

Report them as numbers, never summarised as "good": join pauses, LUFS per segment, integrated LUFS and true peak,
sync lags in ms, durations. A check is only useful if it has failed before: when changing a threshold (flicker,
spacing), run it on a known-bad render first and make sure it fails.

## Every gate in one table

| Stage | Check | Evidence | Pass |
|---|---|---|---|
| Transcript | complete lines, retakes found | printed transcript, `RETAKE?` | every retake resolved in `drop` |
| Cut | nothing lost | word diff | only ASR spelling variants |
| Cut | joins | join table | 0 flagged; plain 0.15-0.25 s; 0 `TAIL ON SOUND` |
| Cut | hand-placed cuts | `align.py` output | every `in`/`out`/splice edge from alignment + waveform |
| Cut | inside takes | `pauses.py` list | no pause over ~0.6 s left except deliberate beats |
| Cut | picture at joins | `check/joins_<tag>.png` | no blink, look-away or mid-gesture jump |
| Cut | eyes | `check/eyes_*.png` | eyes on lens through every picture out point |
| Cut | levels | per-segment `ebur128` | spread under ~1.5 LU, else `--level` |
| Transitions | where | `check/transition_joins.png` + the words | only scene changes at thought ends |
| Transitions | push | frame strip across every push + the frames just outside it | incoming left, outgoing right at mid-push; never the next screen on both halves; edges equal the untouched cut (soft wipe: `check/wipe_bubbles_<tag>.png`, eyes on lens) |
| Captions | verbatim, readable | printed phrases | names right and whole, nothing under 0.5 s |
| B-roll | lint / inspect | `render.py` | 0 errors, inspect clean |
| B-roll | dwell | build report | 0 `SHORT DWELL` |
| B-roll | every beat | `review.py --beats` | matches its words, lands on its word, nothing clipped or overlapping, no face flash at a cut |
| B-roll | empty cards (16:9 panel) | `empty_card.py` on a preview | no blank card over ~1 s |
| Export | loudness | `finalize.py` / `export_final.py` | about -14 LUFS, true peak at or under -1.5 dBTP |
| Export | sync | 4-probe cross-correlation | 0.0 ms at all four; duration equals the clean cut (+ end hold) |
| Export | around inserts | `insert_segment.py --check` | every probe within 5 ms |
| Export | file | `ffprobe` | source resolution and fps, H.264 + AAC, .srt beside it when asked |

## Checking the exported file

Run the last checks on the file that will be uploaded, not on the cut, the page or a preview:

- `ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate:format=duration <file>`
- A frame grid of the export at the start, the end, every transition and every inserted segment's joins.
- The export's sync probe compares against the clean cut. Anything assembled around an insert is checked against the
  source clips with `insert_segment.py --check`.
- The first word within ~0.1 s of the first frame; the ending held on a good frame, not a look-down.

## Before saying done

- Re-read the user's ask. Every deliverable exists, each in a new folder or with a new version number.
- Nothing earlier was overwritten.
- Anything not verified is named as not verified, first.
