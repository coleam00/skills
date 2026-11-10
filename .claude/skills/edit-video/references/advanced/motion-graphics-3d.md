# Premium motion graphics with depth

For the rare edit that asks for premium, keynote-style animation or "3D". Most videos do not; they use the
HyperFrames scene kit (`references/captions-and-broll.md`) or no graphics at all. This file describes an approach and
its audit discipline. No kit ships with the skill: build one per project from these rules, and expect several review
rounds.

## Contents
- The look that works
- The approach
- Hard rules
- Picking a graphic
- Gates, in order
- Traps

## The look that works

**Mostly 2D, with a little depth.** Product UI in a keynote, not toys and not slides: a few flat cards (crisp shapes,
clean line icons, documents, tables and charts that look like real software) set slightly apart in depth, soft
shadows, a still background, at most a very slow drift. Real product photos where they exist.

It goes wrong in three directions:
- **Too flat:** card, arrow and text templates read as a slightly animated slide deck.
- **Too built:** a rendered 3D world with floors, reflections, bloom and camera flights reads as a toy render, and it
  flickers.
- **Too chunky:** solid 3D objects (blocks, cube stacks, capsule people, toy props) read as childlike.

And one more: **one treatment everywhere reads as a template.** Mix a few treatments that share colours and type
(product photo with callouts, a blueprint line drawing that draws itself on, a realistic UI screen, the odd flat
card); never the same treatment twice in a row, none for more than about a third of the graphics. Isometric and
extruded depth read as "too 3D".

## The approach

- **A plate, rendered separately.** Graphics render in headless Chrome on the GPU (three.js for the depth, cards drawn
  on 2D canvases as textures) into a video plate the size of the frame, at the final fps. Two passes from one page: a
  plate with the words and a clean plate without them, so a clean master exists for re-captioning or translation.
- **Composite with the face.** The plate, the clean cut and the captions are composited (for example with a
  HyperFrames page) in three face states: full face, face panel + graphic, graphic only.
- **Beats declare intent, not coordinates.** Each beat states its time (from a phrase lookup in the captions file,
  never typed seconds), whether it sits beside the face or fills the frame, and the world size it must fit; the
  camera is worked out from those. Each graphic builds in its own local coordinates and never depends on where another
  one sits.
- **Words on cards are drawn on the card,** so they tilt with it and the clean pass can drop them.

## Hard rules

**Professional, not childlike.** No solid volumes. A person is a round avatar with a line icon; a token is a small
flat tile; a machine is a card with an icon or the real product photo. Depth only from layering, soft shadows and a
gentle tilt.

**Simple.** No environment (floor, reflections, horizon, fog, bloom, dynamic shadows). One fixed camera per graphic.
If a problem needs tuning shaders or lights to fix, delete the feature.

**No flicker.** Supersample 2x; mipmapped textures; no pulses, blinking or additive sparkle. A change of light takes
0.3 s or more, once. Nothing fine and repeating moves fast (paper texture, stripes and grids crawl). Nothing bright
appears in one frame; fade or grow it in.

**Parts belong together.** A part is parented to what it belongs to and starts from a named point on it, or it
floats behind its owner in some frames.

**Pace.** At least 4 s per graphic, aim for 7-12 s, one idea each. If the words change every 2 s, keep the graphic and
change its title. About 30 graphics in 7 minutes is right; 60 was too fast. No graphic is empty for its first
seconds: show the cards at rest, animate their content on the words.

**Face time.** On long-form, most of the runtime is face panel + graphic; full face is a few moments (the opening,
section starts, opinions, the sign-off), about 8-10%. More than ~20% read as too much.

**Specific.** A viewer with the sound off can name the idea: a scan line passing over a page, a lock landing on each
chunk, a capacity bar the items overflow. Reuse a whole graphic at most twice. Numbers appear at their final value.
Product photos only where the product is named; elsewhere draw the idea, and draw real objects, not rectangles with
circles.

**Sources.** Every external figure has its source on screen; the speaker's own measurements never do.

## Picking a graphic

Write a table before any code: spoken span, face state, the cards, what changes on which word, and why it could only
mean this sentence.

| Sentence | Graphic |
|---|---|
| The cost is many times the question | a grid of small token tiles beside a receipt that keeps printing |
| Permissions live on the data, not the app | a stack of chunk strips, a lock badge landing on each; the app bar gets a cross |
| It all fits in memory | a capacity bar; the segments fill it with room to spare |
| It does not fit | the same bar, shorter; the last segments run past the end as a dashed outline |

## Gates, in order

Each gate runs on the plate (minutes), not on the finals (hours).

1. **Spacing audit, at zero, in every format.** Check every visible word against the graphic pixels under it (with
   padding), words against words, the face and caption zones, and the frame edge. Words meant to sit on a card are
   marked as such. Fix until it reports 0 issues; never raise a threshold to pass.
2. **Overlap audit.** Render each top-level graphic of a beat alone and list every pair whose pixels overlap, plus
   pairs closer than ~36 px ("smashed"). Mark deliberate layering explicitly; review the rest as stills.
3. **Stills of every graphic** at its middle and its end, in every format, in ascending time order (a renderer that
   does not rewind shows leftovers from out-of-order requests). The audits miss ugly-but-legal layouts.
4. **Flicker gate:** `uv run --project $S python $S/flicker_check.py <plate.mp4> --w 540` counts pixels that reverse
   brightness repeatedly across frames. Calibrate it on a known-flickering render first.
5. **Face-state transitions frame by frame** on a low-fps preview before the slow render.
6. **Sample windows** of the full composite (a few 10-20 s windows) before the whole video, especially when choosing
   between styles.
7. Then finals into a staging folder, verified like any export (`references/verification.md`). Say plainly that the
   frames and measurements were read; motion feel is the human's to judge.

Measure throughput on the first plate (frames per second for both passes) and plan renders from that number. Only one
GPU render at a time.

## Traps

- A face panel transition tweened as a clip-path string does not interpolate: the camera frame shrinks as a square
  and snaps into the panel. Tween each edge and the radius as numbers; check every transition frame by frame.
- Dark gradients band through the encode chain. Compute the background per pixel in float with about ±2 levels of
  triangular dither, keep it subtle, and finalize with `finalize.py --deband`. Check by boosting contrast.
- A glow or shadow texture must reach zero alpha inside its canvas, or the plane shows a box edge.
- Product shots on white keep a grey floor shadow in a naive cutout. Rendered shadows are neutral grey: flood the
  background from the border through near-white and neutral grey, smooth the outline, take the edge colour from the
  device, never un-multiply against white. Check every cutout on a dark and a saturated background, zoomed on its base.
- Product photos can be very wide; size them from the frame width or they run off a vertical frame.
- Lines that start at a badge's centre can sort in front of it; start them at the rim and draw badges above lines.
- A drawing helper that shares one random sequence changes every frame on a redrawn card: seed each drawing from its
  own position. Scrub a live card frame by frame before calling an idle-motion note fixed.
- No idle motion on icons; things appear once and hold.
- Labels at pane edges drift on a tilted beat: keep labelled beats straight-on. Line charts stay straight-on.
- A row of related items appears together; their labels arrive as each is named.
- In a graphic-only 16:9 beat the captions own the bottom band: keep cards and labels above it.
- Set start states at time 0, not 0.01: frame 0 renders first and shows one wrong frame.
- A plate is words plus picture: a layout change means re-rendering both passes.
- One global zoom for every graphic cuts off the wide ones: size each graphic and check each edge.
- On a case-insensitive file system, `FINAL` and `final` are the same folder.
- The last section is the close: give it a through-line (one object carried station to station) rather than three
  unrelated cards.
