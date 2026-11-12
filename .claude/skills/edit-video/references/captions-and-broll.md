# Captions and B-roll

Burned-in captions and motion-graphics B-roll, both built as one HyperFrames page (HTML + a paused GSAP timeline,
rendered frame by frame by headless Chrome) over the clean cut. Every rule here came from a review of a real render;
the reason is given so the cases it does not cover can be judged.

## Contents
- Captions
- Brand and look
- What makes graphics read as machine-made
- Layouts
- Timing
- Writing the on-screen words
- Planning the beats
- Scene catalogue
- Schedule mechanics
- HyperFrames and GSAP traps
- Render facts

## Captions

- Verbatim: what was said, never the script the speaker paraphrased. Fix ASR spellings in `<ws>/caption_fixes.json`:
  `{"Cloud Code": "Claude Code", "11am": "11 AM", "_keep": ["Save My Seat"]}`. Fixes match words as `captions.py`
  prints them (case and punctuation ignored) and may add punctuation; `_keep` holds a name or label together.
  Because case and hyphens are ignored, `"work-flow": "workflow"` also rewrites a correctly capitalised product name
  "Workflow" elsewhere: when the word appears twice, anchor the fix with its neighbour (`"our work-flow"`).
- Vertical: 2-4 words per phrase (22-26 characters). 16:9: 34-42 characters. Split at punctuation, pauses over
  0.25 s and segment joins; nothing on screen under 0.5 s.
- Style: heavy sans, white, the active word in the accent, soft dark shadow, no box. Once a caption style is approved
  for a channel, lock it in brand.json and do not restyle it to match a new graphic look.
- Long-form YouTube usually uploads an .srt instead: config.json `"captions": "srt"` keeps them out of the picture;
  `finalize.py` writes the .srt either way (run `captions.py` for the tag first).
- Read every printed phrase: no split names, no take that came back lower-case and unpunctuated (fix it with
  punctuation in caption_fixes).

## Brand and look

Defaults live in `scripts/hf/style.py` (TOKENS); `<ws>/brand.json` overrides any of them (`examples/brand.json`).
`style.page()` re-tints every built-in accent and background colour in the finished page to the brand's, so one file
changes the whole look.

- A still dark background with a soft gradient; subtle grain. No aurora blobs, no grids.
- One accent; a lighter tint of it for text on dark. Red only for struck-out or rejected things.
- A heavy weight for statements, a bold weight for list text, a mono face for anything technical. Inter and
  JetBrains Mono resolve automatically in HyperFrames; any other font needs an `@font-face`.
- Emphasis is a marker sweep behind the key word or a hand-drawn mark (circle, underline, check, strike) drawn on
  over 0.3-0.5 s. Marks are seeded `rough.py` paths: imperfect but deterministic.

## What makes graphics read as machine-made

These were called out on a first motion draft as obviously generated, and are banned in `scenes.py`:

- "fig. 1" labels, zero-padded 01 02 03 numbering, letter-spaced uppercase overlines on every scene
- rubber stamps, slanted badges, sticky notes, slapped-on chips
- icon + label chips where a generic icon stands in for meaning
- cards inside cards, uniform rounded borders everywhere, glows behind everything
- every element entering with the same fade-up
- lower-case list items (every label and item starts with a capital)
- boxes and circles standing in for a real object; draw the object or a real UI instead

If a scene needs a label to explain itself, the scene is wrong.

## Layouts

`engine.Track` derives every box from the measured face; never hard-code positions.

| Mode | Vertical (9:16) | 16:9 |
|---|---|---|
| FACE | full frame, captions on the shirt below the chin | full frame, captions in the lower band |
| SPLIT | face slides UP into a full-width band (headroom kept), graphic below in `page_box` | avoid: it reads zoomed in on the face with a hard seam down the middle |
| FULL | graphic covers the frame, wipes up; captions stay | same, content in a centred column (`full_box`); keep short |
| PIP | not used | the face shrinks into a portrait **panel** on the right, the graphic on a card to its left (`pip_box`); the panel grows back to full face in place. `"bubble_shape": "circle"` for a round bubble |
| SCREEN | not used | the recorded screen track (`assemble.py --screen`) full frame, face in the panel |

- Never put the face in a box, frame or "photo print". Never push it so high the head is cut, never cover more than
  the chest; it needs room above the head.
- **Long-form 16:9 with the panel:** FACE and PIP; no FULL between card spans (a 2-3 s full-screen opener between
  two card spans reads as jumping back and forth). FULL is for videos with no PIP.
- Pick layouts from where the speaker looks: someone reading a deck looks down, which reads badly full frame. Keep
  FACE for stretches at the lens; put PIP over the reading. Check every FACE beat on a frame sheet.
- `face_track.py <ws> --tag <tag>` after assemble makes the panel follow the face; without it the panel crops one
  median spot and punch-ins put the face off centre.

## Timing

- Enter a layout so the panel has landed by the first word it illustrates (SPLIT ~0.5 s before, FULL ~0.4 s).
  Each element appears ON its spoken word; anything said later is not on screen yet, not even greyed out.
- **Dwell:** a graphic someone must look at stays up 1.5-3 s after its main visual has landed (short form); mark
  the landing with `tk.key(scene, t)` and fix every `SHORT DWELL` by starting the next scene later or landing this one
  sooner. Premium long-form graphics hold 7-12 s each, one idea per graphic.
- Leave on the phrase that closes the idea, plus ~0.3 s. A payoff link stays on screen after the return to the face.
- Shorts: 55-70% of runtime in B-roll, about a third of it FULL; never more than ~12 s without the face; never a face
  gap under ~1.5 s between two B-roll segments (merge them). Long-form: 50-65% graphics counting PIP and SCREEN.
- **Stacked layout (face in its own band): the graphics band is never empty.** Beats run back to back from 0.0
  (`tk.band(t, sid)`), and a stretch with nothing new to show holds a topic card (`S.title_card`) rather than going
  back to the face. The report's `EMPTY BAND` lines (over 2 s) must be gone before rendering; the B-roll share
  target above does not apply. `references/formats.md`, Stacked layout.
- **Face beats under 3.5 s between graphics are dropped by the engine** (`MIN_FACE`): the card crosses straight to the
  next graphic. Face pops scheduled in a dropped beat must be deleted.
- **Cut sweep:** near a picture cut, entering B-roll starts early enough to cover the cut and returning to the face
  lands exactly on it; otherwise the next take's face flashes for 2-10 frames. Build every scene from the time
  `split()` / `full()` / `pip()` RETURN, since they can move.
- No empty card: start a card scene ~0.5 s before its first element. `empty_card.py <preview.mp4>` lists blanks of
  1 s+.
- Do not end a short by snapping back to the full camera on the last word: hold the last graphic or the link.
- After an inserted segment, return straight to the face; a graphic on its first frame flashes the old slide.

## Writing the on-screen words

- Short. One idea per scene, at most ~6 labels. Lists of five read better one per line.
- The speaker's words (or the approved script's), never a paraphrase that contradicts them. Numbers exactly as said
  ("100,000"), appearing at their final value; a count rolling up reads as decoration.
- No made-up specifics: a fake ticket id or pass number not in the script gets cut.
- Specific beats generic: a viewer with the sound off should be able to name the idea. Draw the actual thing (a real
  terminal with the real output, the real folder of files) rather than an icon standing in for it.
- Metaphors must read in a second; two labelled arrows beat an abstract diagram.
- A statement that only repeats the line being said adds nothing; drop it.

## Planning the beats

Write the plan as a table before any code, one row per beat, using the speaker's own words from the transcript:

| Phrase (from the transcript) | Layout | Scene | Shows |
|---|---|---|---|
| "the one thing I want you to leave with" | PIP | quote | the thesis, key phrase swept |
| "first, second, third" | PIP | steps | the framework, one item per word |
| "watch what it runs" | PIP | terminal | the real command and output, typed on their words |
| "my take" | FACE | none | an opinion: the face carries it |

A slide is not a scene: turn each slide into the one idea it carries. Change layout when the idea changes, not on a
timer. Variety: never the same treatment twice in a row. A recurring picture (a framework map built once, each
section flying into its node) beats a new one per section. The first graphic lands within ~10 s; a FACE stretch over
~4 s can take one `face_pop` on its key phrase (verbatim, 1.2 s minimum, clear of layout changes).

## Scene catalogue

`scripts/hf/scenes.py` (import as `S`) and `scripts/hf/motion.py` (import as `M`). Each takes `(tk, sid, box, ..., t0)`
and returns HTML; times are output seconds from `tk.at`. Type scales with the box, so one scene works in every layout.

| Scene | Shows |
|---|---|
| `S.statement` | 1-4 stacked lines; strike the wrong idea, underline or circle the right one |
| `S.points`, `S.checklist` | plain lines with a key word marked; hand-drawn boxes ticked on their words |
| `S.ledger`, `S.columns`, `S.stats` | a two-column table; 2-4 titled columns; one to three big figures |
| `S.meters`, `S.ring`, `S.hub`, `S.lanes` | level rows; a lifecycle loop; centre + spokes; labelled arrows then stages |
| `S.card`, `S.log`, `S.terminal` | key/value card; typed mono lines; a terminal with prompt, commands and output |
| `S.file_tree` | a file explorer, files lighting on their words, optional open note |
| `S.quote`, `S.bignum` | one big statement with its key phrase swept; numbered items |
| `S.title_card` | a held topic card (kicker, title, rule, optional line on its word): fills the stacked band between beats |
| `S.image_cta`, `S.link_pill` | a screenshot on a card with a typed URL; a persistent URL above the captions |
| `S.shot` | a real capture of the product in a window: push-ins, rings, spotlight and state swaps on the words (`screen-inserts.md`) |
| `M.system_map` | a four-part framework round a centre; `focus=i` flies into one node (section openers) |
| `M.load_context`, `M.flow_hub`, `M.converge` | files flying into a context window; packets into a hub; chips merging |
| `M.gate`, `M.test_runner`, `M.pulse` | pass/block at a gate; rows flipping to PASS; a pulse line dropping labels |
| `M.kinetic` | the speaker's own words popping in on their spoken times |
| `M.window_grid`, `M.chat`, `M.palette` | mini app windows; message bubbles; a command bar typing |
| `M.steps`, `M.stack_tower`, `M.foundation`, `M.bars`, `M.declutter`, `M.model_slot` | process and structure scenes |
| `M.counter`, `M.tiles` | count-ups; avoid for figures (numbers land at their final value) |
| `M.face_pop`, `M.face_shake` | FACE only: big words beside the face, returned as overlay HTML |

A scene goes in the library when it will be reused; a one-off goes in the schedule as raw HTML plus `tk.add()` tweens,
following the same rules: real pixel boxes, appear on the word, marks drawn on.

## Schedule mechanics

```python
s = tk.split(at("not a tool") - 0.1); tk.pscene(s, "hook")          # vertical: enter SPLIT, show scene "hook"
P.append(S.statement(tk, "hook", tk.page_box, [...], s))           # build it from the RETURNED time
s2 = tk.full(at("and on Monday") - 0.15, "when")                    # FULL
F.append(S.card(tk, "when", tk.full_box, "Live session", [...], s2))
s3 = tk.pip(at("the first step") - 0.4, "ctx")                       # 16:9: PIP scenes go in F, in pip_box
F.append(S.quote(tk, "ctx", tk.pip_box, "...", "key", s3))
tk.face(at("in front of you", end=True) + 0.3)                      # back to the face
```

`tk.at(phrase, after=t, end=True)` finds a phrase's first occurrence after `t`; use `after` for repeated phrases.
`tk.report()` prints coverage, every segment, every cut-sweep move and every `SHORT DWELL`: read it each build. Set
`"type_scale"` in config.json (about 1.45 for a 16:9 talking head) if wide scenes read half-empty.

## HyperFrames and GSAP traps

| Trap | What happens | Do instead |
|---|---|---|
| `className` tweens | GSAP 3 removed them; silently nothing | tween properties |
| CSS `transform` on an element GSAP also moves | lint error; GSAP overwrites it | a wrapper, or `fromTo` with explicit start values |
| `left`/`top` tweens | lint rejects layout-property animation | `x`/`y` |
| `tl.to` on a property set elsewhere | starts from whatever the last seek left | `fromTo(..., {immediateRender:false})` |
| start states at t=0.01 | frame 0 renders before them: one wrong first frame | set start states at 0 |
| `stroke-dashoffset` in CSS | CSS wins over the attribute tween; marks never draw | set it as an attribute; tween `attr` |
| a stretched SVG `viewBox` | wobble and stroke width distort | size the viewBox in real pixels |
| `clip-path` reveal on text | descenders cut off | negative bottom inset (`reveal()` does) |
| clip shapes tweened as `inset(... round r)` strings | they do not interpolate: the shape snaps | tween each edge and the radius as numbers |
| sub-pixel slow push-ins | text sits still, then hops 1 px every few seconds | no idle drift; motion comes from entrances |
| GSAP `force3D:auto` | text re-rasterises a pixel off when a tween ends | `gsap.config({force3D:true})` (the page sets it) |
| a shared random sequence in a redrawn drawing | the drawing changes every frame (jitter) | seed each drawing from its own position |
| hard-coded seconds | every re-cut shifts all of them | `tk.at("phrase")`, always |
| intentional overflow or overlap | inspect warns | `data-layout-allow-overflow` / `data-layout-allow-occlusion` |

## Render facts

- `render.py` runs `npx hyperframes lint`, `inspect` and `render`. Pin the renderer for a project in progress with
  `HYPERFRAMES_VERSION=<version>`: a release published mid-project can fail to install or render differently.
- Draft renders run roughly 2.5-3.5x real time at 1080p60 on a fast desktop; measure your own on the first render.
  `--fps 6` gives a review preview of a long page at a tenth of the frames.
- Pages longer than `--chunk-secs` (240) render in chunks; one huge job can stall near the end. `--only 0,2`
  re-renders chosen chunks after a fix.
- Render one section (2-3 minutes) of a long page first, review it, fix the patterns, then render the rest.
- The rendered audio is the clean cut's; `finalize.py` re-normalises it (HyperFrames lands ~1 dB low) and limits peaks.
- AAC raises true peak ~1 dB: limit before encoding, measure after.
