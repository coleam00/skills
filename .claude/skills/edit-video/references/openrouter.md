# The full pipeline: OpenRouter

Basic runs everything on the machine. Full adds four kinds of model behind one OpenRouter key: transcription
(audio in), a video reviewer (video in), image generation (images out) and voice cloning (audio out). It runs only
when the user asks for it (SKILL.md, Basic or full).

## Contents
- Setup
- What each step sends out
- Transcription
- Video review
- Thumbnail concepts
- Fixing a word
- Costs

## Setup

- A key from https://openrouter.ai/settings/keys in `OPENROUTER_API_KEY`, or one line `OPENROUTER_API_KEY=...` in
  `scripts/.env` (git-ignored).
- `openrouter.py <ws> enable` turns full on for that workspace and prints the model for each step. Swap any of them
  with `--transcribe`, `--review`, `--voice` or `--images a,b,c`; `openrouter.py models image|video|speech|transcription`
  lists the current catalog. `disable` goes back to basic.

## What each step sends out

| Step | Leaves the machine |
|---|---|
| Transcription | the audio of every clip, the cut and every re-check window |
| Video review | a 480p, 10 fps proxy of the export, with its audio |
| Thumbnail concepts | the brief and one frame of the speaker (the face reference) |
| Fixing a word | about 8 s of the speaker's voice around the line, and the new words |

Unpublished footage and a voice sample are the user's to send. A voice fix needs the speaker's consent every time.

## Transcription

- Full mode moves every transcription to the OpenRouter model, not just the first pass: `transcribe.py`, the tail
  checks in `cutpoints.py`, `validate_cut.py` and `retranscribe.py` (when given a workspace). One switch,
  `common.asr_model()`; nothing loads on the local GPU.
- `elevenlabs/scribe-v2` by default; `microsoft/mai-transcribe-2` is half the price and as accurate. Both return
  word timestamps (`verbose_json`, word granularity). `openai/gpt-4o-transcribe` rejects word timestamps.
- Measured on 10 real pauses: word starts within ~0.035 s of the audio for both and for Whisper. Word ENDS: Whisper
  0.15-0.23 s early (the clipped-word trap), these 0.03-0.16 s late, the safe side. Neither printed the doubled words
  Whisper invents ("I I", "control control") nor its end-of-take "Thank you.".
- Long audio (over ~10 min, the validation pass) goes up in pieces split at the quietest moment near every 8 minutes.
- Cost: about 3-10 cents for a 17-minute recording; 2-5 s per take.
- `cutpoints.py` re-transcribes ~15 short windows at the end of every segment. In full mode that is one call per
  window, all of a segment's windows at once (about 30 s for 9 segments, a few cents). A remote model ignores
  `beam_size`, so the local two-beam agreement check would only pay twice for the same answer. One read per point
  varies call to call, so a lone miss among good reads is ignored (a clipped word fails several points in a row).
  Before that rule, one flaky read moved an end by up to 0.4 s between identical runs; with it, four runs matched.

## Video review

- `video_review.py <ws> <export>` after the skill's own gates pass. `--from/--to` reviews a section. `--model` swaps
  the reviewer: same proxy, same prompt, so two runs compare like for like.
- `google/gemini-4-argon` by default (9 of 10 notes true on a published 20-minute video, about $0.29; $0.21 for a
  16-minute export); `google/gemini-3.8-flash` costs about a third and invented one note. Every note is a lead: read
  the frames at its time and listen before acting on it. Real notes are not always worth acting on: a deliberate
  choice reads as a flaw.
- **It invents cuts.** On a clean 16-minute edit, 7 of Argon's 8 notes were "a word clipped at a cut" where the take
  was continuous. `video_review.py` now sends the edit's cut list (`cut/timeline_<tag>.json`, tag from the file name
  or `--tag`) and marks any cut note with no real cut within 1.5 s `NO CUT HERE`. Same export with the list: 4 notes,
  every cut note at a real join, and the one true catch kept (the speaker said "70%" while the screen showed "75%").
- Its best catch in testing: a blur that left private terminal text readable for 3 s in a published video.

## Thumbnail concepts

- `thumbnails.py <ws> "<brief>"`: the brief and a face frame (or `--face <photo>`) to every model in
  `openrouter.images` at once, through `/api/v1/images`. Models that take image input get the face as a reference.
- Exact wording in quotes in the brief. Models add taglines nobody asked for; read every concept at full size, and
  look at `grid_phone.png`, which is how most viewers first see it.
- Cost: `usage.cost` per image, printed under each concept (3 cents to about 20 cents each).

## Fixing a word

- `fix_word.py <ws> <clip> <start> <end> "<corrected words for the span>"`. The span snaps to the quietest moment
  within 0.3 s of each edge, so it is bounded by pauses; give the corrected text for the WHOLE span.
- `fish-audio/s2.1-pro` by default. `bytedance-seed/seed-audio-1-0` also clones well (slower, ~10x the cost);
  `heygen/heygen-voice-1` sounded wrong on a real voice and returns raw 44.1 kHz PCM only.
- **Reference length decides whether it sounds like the speaker.** 8 s (the line alone, at the end of a take) came out
  "not quite me"; ~26 s (the line plus clean speech from the neighbouring take, one joined clip with its transcript)
  sounded right in every take. Fish accepts ONE reference clip ("no endpoints supporting multiple audio references").
- **Never slow the new line down.** Stretching it to fill the span made the voice sound slow and odd. It plays at
  natural speed (sped up at most 8% if long); a shorter take leaves room tone. Level-matched, crossfaded 40 ms.
- `--candidates 3` writes a listening file per take and applies nothing; the speaker picks by ear, `--use` applies.
  In the first real run 1 of 3 takes dropped a word ("as") and the check caught it; the other two read back exactly.
- Applied only if the span reads back as the corrected words (removed words gone, new words heard). It writes
  `clips_fixed/<same name>` and repoints config.json; the source is untouched.
- Trap: trimming the generated audio with `silenceremove` `stop_periods` cut it at the first gap between words;
  trim both ends only (`areverse` around a start trim).
- Cost: under a cent a line. Text to speech returns audio only; the cost comes from the generation lookup.

## Costs

`openrouter.py <ws> costs` totals `costs.jsonl` by step and model. A call whose cost was not reported counts as 0
and is flagged.

Measured on a 16-minute video (Fable 5.2 guide, 28 takes):
- One clean pass with the defaults (transcription, cut checks, one review): about $0.45; transcription alone $0.23.
- A real edit with three rebuilt versions, four reviews, eight thumbnail concepts and a voice fix: $2.58
  (transcription $1.24 over 2,368 calls, because the cut-point and validate checks run again after every fix;
  reviews $0.84; thumbnails $0.50; voice under a cent).
- Three Shorts cut from it, with two fix rounds and ten reviews: $0.13.

The video review is a lead, not a verdict. On that edit it caught the real problems (a number said wrong against the
screen, recorder dropouts in the camera audio, a clipped diagram and a wrong last frame in a Short) and also reported
many that were not there (transition sounds "too loud" that sat in pauses, a misread number under the mouse pointer,
a "path leak" that was a menu). Check every note against the frames and the audio before acting on it.
