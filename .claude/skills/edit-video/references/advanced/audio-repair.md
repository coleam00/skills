# Audio repair

Two problems the cut cannot fix by trimming: dropouts baked in by an overloaded recorder, and a misspoken word that
cannot be re-recorded.

## Contents
- Recorder buffer skips
- A copy with the unrepaired audio
- A misspoken word (described, not shipped)

## Recorder buffer skips

When a screen recorder's audio thread is starved (CPU at 100% during a demo), it drops whole 1024-sample buffers.
Nothing goes silent: the waveform jumps at one sample and the speech lurches ahead, heard as a click, a cut or a
stutter. It happens upstream of the encoders, so the camera, screen and composite files all carry the same skips and
silence checks or cross-file comparisons find nothing. Check every recording made under load.

```
uv run --project $S python $S/fix_skips.py <ws> --report            # per clip: skips found, grid phase, spike share
uv run --project $S python $S/fix_skips.py <ws> --out <clips>_fixed # repaired copies; point config.json clips at them
```

- **Found** with an LPC residual (order 20): normal speech cancels, a skip is a residual spike. Skips sit on the
  take's buffer grid, so only grid boundaries are scored; natural spikes rarely land there (in one recording 52 of
  343 big spikes fell in one 3-sample grid window, where chance predicts one).
- **Repaired** by relaxing the step to zero over 3 ms. Timing never changes, so picture sync cannot drift, and no
  sample outside those 3 ms moves. The skipped audio is gone; the repair makes the join inaudible, it does not restore
  words.
- **Verify:** the cut's re-transcription should be identical word for word before and after the repair, and a
  waveform tile of each repaired skip should show no step. One 21-clip recording had 310 skips; the median step went
  from many times typical speech to about the level of speech.

## A copy with the unrepaired audio

Keep the originals. A speaker who prefers their own enhancement tool gets the same finished video with the original
audio:

```
uv run --project $S python $S/swap_audio.py <ws> <final.mp4> <tag> <cuts.json with the original paths> <out.mp4>
```

It rebuilds the audio exactly as assemble did for that tag, applies the same end hold and loudness, muxes it onto
the finished picture with the video stream copied, and prints the lag against the final's own audio (must be 0.0 ms).

## A misspoken word (described, not shipped)

A wrong product name or pronoun can be fixed without re-recording by generating the corrected words with a local voice
clone of the speaker. The skill does not ship this: it needs a multi-gigabyte model stack, and cloning a voice needs
the speaker's explicit consent for every use. What worked, for anyone building it:

1. **Consent and locality.** The speaker's own voice, with their permission, on a local model. Nothing leaves the
   machine. Always keep an untouched original-voice export alongside.
2. **Replace a span bounded by silence or a stop closure,** not the word alone. Swapping one word inside connected
   speech sounded choppy; a run of corrections in one phrase is ONE span from one continuous take.
3. **Reference the clone on the original sentence itself** (reference text = what was said, generated text = the
   corrected line), so pitch and pace match that line. A reference from elsewhere came out several semitones off.
4. **Lay the original room tone under the generated audio** and crossfade 40 ms at both edges. Keep tempo within
   0.9-1.1 so span length and lip timing do not move.
5. **Restore the top band.** A 24 kHz model has nothing above 12 kHz and reads duller than the mic on spans over
   ~1 s; an exciter scaled to the original span's level fixes it.
6. **Verify every take** by splicing and transcribing; keep the first that contains the new words and no trace of the
   old.
7. **Hide the mouth** when the face is visible: a gentle 1.2x zoom eased over 0.6 s, fixes under ~6 s apart sharing
   one zoom. Aimed close-ups on each fix looked random; a visible lip mismatch looked worse.
