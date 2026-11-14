# Shorts from a long-form recording

Vertical Shorts (1080x1920) cut out of a finished 16:9 long-form edit that was recorded as separate camera and
screen files per take (the "Separate face and screen files" row in SKILL.md). The long-form's validated cut is the
source, so its joins, splices, voice fixes and audio repairs carry over; each Short is then its own small edit in the
stacked layout: the screen or animations in the band on top, the camera band at the bottom, captions on the seam.

Built and proven on the Fable 5.2 guide (11/13): three Shorts of 35-48 s from a 16-minute v3, one of them mostly
animation, all passing validate, sync, loudness and the empty-band check.

## Steps

1. **Pick the moments** from the long-form transcript (`cut/words_<tag>.json`) and timeline (`cut/timeline_<tag>.json`):
   30-60 s each, a hook in the first two seconds (a claim, a number, a surprising result), one clear point, a clean
   ending (a payoff line, not "and then"). Prefer spans that start and end on the cut's own segment boundaries; a span
   can join two parts (a setup from one take, the payoff from another). Check the screen content of each span for
   anything private before going further.
2. **Cut the sources:**
   ```
   uv run --project $S python $S/long_to_shorts.py <ws> --tag v3 --short s1=14.25-48.75 --short s2=328.3-335.9,358.2-404.9
   ```
   Per Short: the camera as a 1080x760 band cropped at native pixels (never upscaled), the full-resolution screen
   track carrying the same audio, and `layout.json` (stacked, face at the bottom). READ `check_<name>.png`: the face
   must sit on the red centre line; if not, re-run with `--nudge <px>`.
3. **Per Short, a workspace** (one per Short, never shared):
   ```
   uv run --project $S python $S/init_workspace.py <ws>/shorts/src/s1/faces --out <ws>/shorts/s1   # "layout stacked"
   uv run --project $S python $S/transcribe.py <ws>/shorts/s1          # full mode: through OpenRouter like the long-form
   uv run --project $S python $S/cutpoints.py <ws>/shorts/s1
   uv run --project $S python $S/assemble.py <ws>/shorts/s1 --no-punch --screen <ws>/shorts/src/s1/screens --screen-native
   uv run --project $S python $S/validate_cut.py <ws>/shorts/s1
   ```
   - Copied caption fixes that do not occur in a Short are summarised on one line; that is expected.
   - `transcribe.py` reuses an existing `words.json`. In full mode check the Short's `costs.jsonl` shows the
     transcription call (one Short logged $0 because it had copied the local transcript).
   - `pauses.py` normally finds nothing: the long-form removed them. Its REPEAT / RESTART lines are often the
     speaker's real phrasing ("better and better"), not slips.
   - `--screen-native` keeps the screen track at 1920x1080. Without it the screen is conformed to the 1080x760 face
     band and the top band has to zoom into a blurry track.
   - A single-segment Short whose `validate_cut.py` shows `sync lag 0` is exact; the screen slice and the face band
     come from the same long-form timeline.
4. **Captions:** copy the long-form's `caption_fixes.json` (names, "Claude Code", numbers written as on screen:
   "5.2", "/model") and run `captions.py`. Captions sit just above the seam, never on the face.
5. **The graphics band** (B-roll page, stacked layout, `captions-and-broll.md`):
   - Screen-led beats: `hf/screenband.py` plays the Short's screen track in a rounded window and eases a camera onto
     the region being talked about, on the word. Pick the rects off a gridded frame of `cut/screen_<tag>.mp4`.
     Product UI with small text needs `max_zoom=1.8`-`2.0` and a tight rect on the one line being talked about; the
     default 1.4x left a database UI unreadable at phone size (MongoDB, 11/14).
   - Animated beats: the scene library (title cards, checklists, statement lines, code slips) like any B-roll page.
     A "mostly animations" Short is a sequence of these timed to the words, with the screen used only where it proves
     the point.
   - **The band is never empty.** A gap of a second between two scenes reads as broken; land the next title as the
     previous scene leaves (`EMPTY BAND` / the band check must report 0). A scene that is "up" but has not drawn its
     first element yet is empty too, and only `empty_card.py` on the rendered draft sees it: run it on every draft.
   - Put `tk.key` where the scene's main visual lands, not at its last word, or every beat reads SHORT DWELL.
   - **No text on screen twice.** While a kinetic text card spells out the sentence being spoken, hide the captions
     (fade them out as the card enters, back in as it leaves); the reviewer does not always catch this.
   - Long titles: keep model names whole on one line ("Opus 5.5"), shorten the title rather than let it wrap into
     the line below.
6. **Render and export** one Short at a time (one heavy GPU job): draft, read the review sheets, then high and
   `finalize.py`. Each Short ends with the skill's 1 s hold.
7. **Review each Short** (`video_review.py`, full mode): about a cent each. The cut list is found by matching the
   export's length when its version number differs from the cut's tag. On the Fable Shorts it caught a diagram
   clipped at the band's edges and a screen that flipped to the next slide during the final fade; fix and re-export
   as a new version.

## What it costs (full mode, Fable 11/13)

Three Shorts, including two fix rounds and ten reviews: $0.13 of OpenRouter (transcription $0.03, reviews $0.12).
