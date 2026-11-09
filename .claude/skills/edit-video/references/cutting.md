# Cutting

How `cutpoints.py` decides where every segment starts and ends, how to correct it, and how to judge the result.

## Contents
- The two ways a cut goes wrong
- Head (in point)
- Tail (out point)
- Forced alignment (align.py)
- Joins and pacing
- Segments, merges and retakes
- Pauses inside takes
- Slips: a word said twice
- Overrides
- Split edits and punch-ins
- Levels between clips
- Inserts (a finished segment)
- Failure table

## The two ways a cut goes wrong

1. **Dead air.** A pause the viewer hears as hesitation. The usual cause is not silence but a **breath**: an energy
   threshold set relative to speech counts an inhale as sound, so the tail runs on through it.
2. **A clipped word.** The final consonant or the decay of the last word is cut (`actions` -> `action`, a falling
   "eventually" losing its fade). It sounds like a stutter or "cuts too soon".

The fixes pull in opposite directions (tighter vs. longer), which is why the tail uses several separate signals.

## Head (in point)

- Onset = first 5 ms frame where the RMS envelope stays above threshold for 40 ms.
- `in = onset - PRE` (0.10 s), but never more than `HEAD_CAP` (0.25 s) before Whisper's first word. The cap drops the
  inhale before the line; unvoiced initials ("So", "Then") keep their consonant because they sit after the onset.
- A head trimmed off a false start ("Okay, cool. So I also...") must start before the complete intended word and
  after the preceding word's decay. Place it with `align.py <ws> <seg> head --word N`, never from Whisper's start time.

## Tail (out point)

1. **Voicing end.** Track the 100-900 Hz band (voiced speech), tolerating dips under 80 ms (stops inside a word).
   Breaths are broadband noise with little low-band energy, so they do not extend it.
2. **Attached fricative.** If 2.5-8 kHz energy continues right after voicing for at most `FRIC_MAX` (0.12 s), it is
   the word's final s/sh/f/th: keep it. Longer broadband sound is a breath.
3. **ASR probe.** Re-transcribe the last ~5 s ending at candidate cut points every 40 ms. The robust end is the
   earliest point from which the last word is transcribed exactly with beam 5 AND beam 1, there and at every later
   point. `--no-asr` skips it (fast first passes on long recordings).
4. **Word decay.** Keep the tail until the level reaches the room (speech level - 38 dB), up to `DECAY_MAX` (0.4 s),
   breaking if it rises again near the floor (a breath). Falling endings take 0.3-0.4 s to fade, and Whisper still
   recognises a word whose fade is cut off, so the ASR robust end sits mid-decay. Decay is sound, not pause.
5. **Natural silence.** Then give back room tone up to `SIL_PAD` (0.2 s), stopping the moment anything rises.

## Forced alignment (align.py)

Whisper word times are good enough to find words and useless for placing a cut between them: ends run 50-300 ms
early, starts drift, a leading fragment can vanish, and a word whose second half was cut still transcribes whole.
`align.py` aligns the known words to the audio with torchaudio's MMS_FA model, then reads the waveform:

```
uv run --project $S --extra align python $S/align.py <ws> c04_s01 head [--word 2] [--write]
uv run --project $S --extra align python $S/align.py <ws> c04_s01 tail [--write]
uv run --project $S --extra align python $S/align.py <ws> c04 --from 12.0 --to 18.5        # word table only
```

- **head:** walk back from the aligned start to where the level leaves the room (the first sound often precedes the
  aligned start), keep 30 ms, and never go inside the previous word's decay. A worked case: the aligner put "So" at
  1.41-1.49 s, the waveform showed its onset earlier, and the safe start was 1.367 s; a head at 1.45 s cut into
  "So" while Whisper still printed the whole word.
- **tail:** after the aligned end, then the decay to room tone, then any voiced burst within 0.3 s (that burst is
  the end of the word), and before the next word.
- It prints both timings side by side, so the size of Whisper's error is visible. `--write` puts the point in
  overrides.json; re-run cutpoints, assemble and validate.

Use it for every hand-set `in`/`out`, every splice edge, and every join validate flags.

## Joins and pacing

The pause a viewer hears at a join is the tail silence plus the next head's lead-in. `JOIN_MAX` (0.25 s of padding)
caps it by trimming the tail first, never into the decay.

| Join | Heard pause (validate_cut's measure) |
|---|---|
| Plain cut, mid-thought | 0.15-0.25 s |
| A sentence ends and the next clip opens a new thought | top of that range, ~0.25-0.3 s; never above ~0.3 s |
| Transition join (step 6) | 0.5-0.8 s, so the whoosh sits in silence |

- Under 0.1 s the speaker sounds rushed; over 0.3 s reads as dead air (0.34 s at a section end was too much).
- "Clipped" and "too long" are different fixes: a word that sounds cut needs its decay kept, never extra silence.
- A lead-in of 0.3 s+ before the first word reads as dead space. The first word should land within ~0.1 s of frame
  one of the video.

## Segments, merges and retakes

- **Folder of clips:** one segment per clip. `--split-clips` also splits clips at pauses.
- **Single file:** split wherever Whisper shows a gap over `--max-pause` (0.6 s). Walkthroughs where typing pauses are
  content: `--max-pause 3`.
- **Merge:** neighbours from one recording with under 0.15 s between the end of one and the onset of the next are one
  segment. Whisper invents pauses; cutting there would replay audio or punch in mid-sentence.
- **Retakes:** `RETAKE?` = a segment whose first 8 words match one of the next three. Nothing is dropped
  automatically. Read both, keep the clean one (usually the later), add the other to `drop`. In clips mode it only
  compares clip openings, so restarts inside a clip need the slip search below.
- Never drop a sentence for redundancy alone. Cutting the first sentence of a take makes it start mid-thought.

## Pauses inside takes

`pauses.py` measures every quiet stretch between two words on the audio (not Whisper's times) and lists those over
`--min`. `--apply` writes a splice for each, keeping `--keep` (0.25 s). A pause that waits for something on screen
(a page loading, data arriving) is still cut: the jump to the result reads better than a spinner. Only a deliberate
beat stays; delete its splice. Re-run cutpoints after applying.

## Slips: a word said twice

Check every clip three ways: low-energy stretches against the clip's own floor, a second transcription with a
disfluent prompt diffed against `words.json`, and repeated 2-4 word phrases (`pauses.py` prints `REPEAT` and
`RESTART`). Then prove each one before cutting:

1. Re-transcribe the RAW clip window with no prompt. If the repeat is not there, it does not exist.
2. Autocorrelate the audio: a real repeat scores over ~0.6.
3. Place both splice edges with `align.py`, add `"splice": {"c06_s01": [[18.04, 18.28]]}` (source seconds; the segment
   becomes `c06_s01` + `c06_s01b`), and transcribe the spliced cut across the join: every word on both sides whole.

Whisper invents doubles often: in one long recording a third of the confirmed-looking doubles were a single word
transcribed twice, and splicing one cut a real word in half. validate flags a splice join `ON SOUND` with its tail
`TAIL ON SOUND`; expected, it is mid-sentence by design.

## Overrides

`<ws>/overrides.json` (annotated in `examples/README.md`):

| Key | Use |
|---|---|
| `drop` | segments to remove (retakes, false starts, asides) |
| `in` / `out` | hard source times for a segment when the detector is wrong. Place with align.py, re-validate |
| `video_out` | picture ends early (split edit), audio continues. Set from the eye strips |
| `splice` | ranges removed from inside a segment (pauses, confirmed slips) |

Keys are segment ids as printed (`c03_s01`). Re-running cutpoints keeps overrides; they are applied last.

## Split edits and punch-ins

- **Split edit:** a speaker who glances at the script before the line ends looks evasive. Cut the picture to the next
  take at the last frame with eyes on the lens; the audio plays on (`video_out`).
- **Punch-in:** consecutive takes of a locked-off camera are jump cuts. `assemble.py` measures the face per clip
  (OpenCV Haar; `opencv-python-headless<5`, 5.x removed the cascades) and alternates framings whose face sizes
  differ by ~10%. Smaller steps read as a glitch; larger ones read as a zoom effect. `--no-punch` for screen
  recordings, where a punch-in would crop the content.
- Micro-fades (8 ms in, 15 ms out) at every audio edge kill sample-level clicks.

## Levels between clips

One segment far louder than the rest (a mastered insert at -14 LUFS among raw clips at -25) pushes the final
loudnorm out of linear mode, and its dynamic gain then steps the level of whole sections (everything after an insert
came out 3 dB quieter once). Clips from different sessions drift too. Measure per-segment LUFS on the clean cut; if
they spread more than ~1.5 dB, re-assemble with `--level` (gains every segment to the median first).

## Inserts (a finished segment)

```
uv run --project $S python $S/insert_segment.py <ws> <ad_read.mp4> --after c07_s01 [--key m01]
```

The file is transcribed and trimmed as one segment in its own sub-workspace, then copied in as clip `m01` right after
the named segment; `config.json` "inserts" keeps it in place across later cutpoints runs. Keys starting with `m` are
never punched in on and never searched for pauses. Then: assemble with `--level`, a transition or clean cut on both
joins, and after export `insert_segment.py <ws> --check <file> --tag <tag>`: it cross-correlates the export against
each source clip before, inside and after the insert. The export's own sync probe compares against the clean cut, so
it reads 0.0 ms even when everything after an insert is 17 ms early; this check is the only one that catches it. Fix
any lag by adding or trimming that much room tone in the pause after the insert. Place an insert where a section
ends and the next opens with its own setup line, never mid-argument.

## Failure table

| Symptom | Cause | Fix |
|---|---|---|
| Breathy pause at a join | tail ran into an inhale | voicing + breath stop handle it; if it recurs, lower `SIL_PAD` or set `out` with align.py |
| Last word sounds cut, word diff clean | decay clipped; Whisper still hears the word | `TAIL ON SOUND` prints the time to move `out` to; confirm with `align.py tail` |
| A voiced burst just after the word was treated as a new sound | it was the word's ending | never override `TAIL ON SOUND` on a Whisper read; cut after the burst decays |
| Hand-set `out` clips a final s ("this" -> "thi") | a word-final sibilant can run 0.2 s, past `FRIC_MAX` | spectral centroid over 4 kHz at speech level after the word is the consonant: keep it |
| `DEAD AIR` at one join, speech clearly over | noise-gated mic: digital silence fools the ASR probe into a late robust end | read the tail energy in 50 ms steps; `out` = last voiced frame + 0.12 s |
| First word missing from captions/diff | word stamped before the in point | words are matched by overlap, not start; check the head with align.py |
| A line said twice | retake inside one file | `RETAKE?` -> `drop`, or a splice after the slip proof |
| Face blinks or looks down at a cut | eye timing | `video_out` split edit |
| Jump cut looks like a glitch | punch-in disabled or faces mis-measured | check `faces.json`; delete it to re-measure |
