# Lessons

The reasons behind the rules, from real edits and their review rounds. Each is a rule and the failure that produced
it. When a case is not covered by a rule, reason from these.

## Contents
- How the agent sees
- Cutting audio
- Picture
- Transitions
- Captions and graphics
- Motion design
- Render and export
- Process

## How the agent sees

- **Never report a render as good without reading the frames.** The agent cannot watch; frame grids, a transcript of
  the output and numbers are its eyes. Exit codes say nothing about how a cut looks.
- **Re-transcribe the finished cut and diff the words.** It is the only practical proof that nothing was lost or
  doubled; on long recordings nothing else scales.
- **Crop the thing you care about.** A look-away in a 250 px face bubble is invisible on a contact sheet; three wipes
  in one video passed a sheet review and failed in the bubble crop.
- **Check the exported file, not the intermediate.** An inserted segment once left everything after it 17 ms early
  while the export's own sync probe, which compares against the clean cut, read 0.0 ms.
- **Thumbnails mislead.** A card read as "jumping" until full-size frames showed it moving an even 19 px per frame.
  Look at full size before calling something broken or fixed.
- **A check that has never failed proves nothing.** Run a new gate on a known-bad render first.

## Cutting audio

- **ASR timestamps place nothing.** Whisper word ends run 50-300 ms early and Whisper completes words from their first
  half, so a re-transcription still "hears" a clipped word. Place cuts with forced alignment and the waveform; use ASR
  only as a second check. A head moved by 0.1 s on Whisper's word start cut into "So" while the transcript stayed
  clean.
- **A voiced burst right after a word is the word.** A tail check said a word was still sounding; it was overridden
  because a shorter re-transcription still printed the word. The burst 0.15 s later was the word's ending, and the
  word shipped cut off.
- **Tails: voicing, then the attached consonant, then the decay, then natural silence.** A breath is broadband with
  little low-band energy; that is how the tail tells them apart. Falling endings take 0.3-0.4 s to fade; a fixed
  0.12 s tail cut three of them in one video ("cuts too soon").
- **A breath counts as sound to a naive threshold.** The worst cutting feedback ever came from tails running through
  inhales; the fix was tracking voicing, not level.
- **Whisper invents doubled words.** Confirm every "repeat" on the raw audio (no-prompt transcription, autocorrelation)
  before splicing; a splice on an invented repeat cut a real word in half.
- **Cut dead air inside takes, not just at the ends.** Mid-take pauses of 3-4 s reached a reviewer uncut, video after
  video, until a dedicated pass existed.
- **Pause targets are narrow.** Plain joins 0.15-0.25 s heard; 0.07 s reads rushed, 0.34 s at a section end read as
  too much. Joins where a sentence ends sit at the top of the range, not above it.
- **Level-match before loudnorm.** One hot insert pushed loudnorm into dynamic mode and every section after it came
  out 3 dB quieter.
- **Noise-gated mics fool the ASR probe.** Digital silence after the last word made the robust end land late; read the
  energy instead.

## Picture

- **Cut the picture on the last frame with eyes on the lens; let the audio play on** (split edit). A glance at the
  script before the line ends reads as evasive.
- **Punch-ins of ~10% face-size steps hide jump cuts.** Smaller reads as a glitch, larger as a deliberate zoom.
- **Never punch in on a finished insert.** Its own framing measured as a small face and got a 3.4x zoom.
- **Never flash a face for 2-10 frames at a layout change next to a picture cut.** The engine moves layout changes to
  cover the cut (the cut sweep); build scenes from the time it returns.
- **The panel follows the face.** A fixed crop put the face off centre whenever the speaker moved.
- **Speakers read decks.** About a third of one 21-minute talk was eyes down at the slides; full-frame face only when
  they look at the lens, a panel or graphic over the reading.

## Transitions

- **Only at a scene change that ends a thought.** Wiping every in-clip tab switch was "overdone"; a whoosh
  mid-sentence was rejected outright.
- **The detector proposes, the agent decides.** A panel opening scores the same pixel difference as a page change.
- **Both sides of a wipe pause look away.** Switching the bubble at the wipe midpoint still showed a look-away three
  times in one video; live, held, live (only the last ~0.3 s of the incoming pre-roll) fixed it.
- **Small steps on speed.** 0.40 s wipes read slow, 0.34 s is right, under ~0.30 s reads as a jump cut with a sound.
- **Subtle sound.** Six audition rounds converged on short, airy, mid-low noise about -30 dB in the pause. Audition
  side by side on the same picture, never swap blind.

## Captions and graphics

- **Captions are verbatim.** Fix spellings, never paraphrase; an approved caption style stays locked.
- **Graphics land on the spoken word, never before it.** Anything said later is not on screen yet, not even greyed.
- **Dwell long enough to read.** Half-second graphics were "barely shown": 1.5-3 s after the main visual lands.
- **No machine-made tells.** "fig. 1" labels, 01/02/03 numbering, stamps, badges, icon chips, cards in cards and one
  fade-up for everything were called out as obviously generated.
- **Specific beats generic.** With the sound off, a viewer should name the idea. A real terminal with the real
  output, the real folder of files, the actual object drawn, beat any metaphor. Rectangles standing in for a device
  read as lazy.
- **Approved copy is verbatim.** Report every wording difference; never fix one silently.
- **No fake specifics.** A ticket id or number not in the script is decoration and gets cut.
- **Never put a source line on the speaker's own numbers.** Sources are for external figures.

## Motion design

- **Variety, within one system.** One treatment for every graphic reads as a template; never the same treatment twice
  in a row, none for more than about a third of the graphics.
- **Not too flat, not too built, not too chunky.** Card-and-arrow kits read as PowerPoint; a full 3D world with
  floors and camera flights read as a toy render and flickered; solid 3D blocks read as childlike. Mostly flat cards
  with a little depth (soft shadow, slight tilt) read as professional.
- **No idle motion.** A scan line sweeping back and forth "moves a ton"; things appear once and hold. No sub-pixel
  creeps: text snaps to whole pixels and hops.
- **Deterministic drawing.** A drawing that pulls from a shared random sequence changes every frame when redrawn; seed
  each from its own position.
- **Numbers appear at their final value.** Count-ups read as decoration.
- **Pace.** 60 graphics in 7 minutes was too fast; about 30, each 7-12 s, was right. No graphic is empty for its
  first seconds.
- **Face time on long-form is mostly the side panel;** full face is a few moments (opening, section starts,
  opinions, sign-off), about 8-10% of runtime. 22% was too much.
- **Parts belong together.** A part is parented to what it belongs to, or it floats behind it in some frames.
- **Dark gradients band through every encode.** Float per-pixel background with ~±2 levels of triangular dither,
  and a deband + static grain pass at finalize; check by boosting contrast on a graphics-only frame.
- **Product cutouts keep their floor shadow** in a naive cutout: flood the background from the border through
  neutral grey, take the edge colour from the device, never un-multiply against white.

## Render and export

- **Render a sample or one section first.** Full renders are hours; a framing fix on a preview costs minutes.
- **Chunk long pages.** A single 75,000-frame job captured every frame and then stalled at the end.
- **Delete the old output before rendering.** A failed render that leaves the previous file in place looks like
  success; two full-length runs "succeeded" that way.
- **Pin the renderer version for a project.** A release mid-project can fail to install or render differently.
- **`alimiter` needs `latency=1`,** or the export drifts 5 ms out of sync; limit before AAC, measure after.
- **Never capture a website live for an edit; render it frame by frame** on a controlled page clock (live capture
  dropped every other frame and played page animations several times too fast).
- **ffmpeg crops clamp silently at the frame edge.** A bubble landed 4 px off with a ring of background around it.

## Process

- **Never overwrite a source or an export.** Every version gets a new number.
- **Gates before slow work, at zero.** A spacing or overlap audit must report 0 issues in every format before a full
  render; never raise a threshold to make it pass.
- **Calibrate a gate on a known-bad render** before trusting it.
- **Turn each piece of feedback into a rule and a check.** A rule alone gets skipped; a check that runs every time
  does not. Keep a short review log per project and fold it into the rules.
- **Say plainly what was verified and how,** and name what only a human can judge (motion feel, sound).
- **Shared tooling stays simple.** One Python environment for every edit; no per-workspace venvs.
- **One heavy GPU job at a time.** A busy display GPU once made a transcription five times slower while a second GPU
  sat idle; the scripts pick the least-busy GPU, and the agent checks before starting a render.
