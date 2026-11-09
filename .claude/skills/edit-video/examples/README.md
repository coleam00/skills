# Example workspace files

JSON has no comments, so every key is explained here. All three files live in the edit workspace (`<ws>/`, the
`_edit` folder `init_workspace.py` creates), never in the skill folder.

## brand.json (optional)

Overrides the default look of captions and B-roll. Any key can be left out; missing keys keep the default.

| Key | Used for |
|---|---|
| `bg`, `surface` | page background; card and panel surfaces |
| `ink`, `ink2` | main text; secondary text |
| `accent`, `accent_light`, `accent_deep` | the one accent colour, its light tint for text on dark, its deep tint for the background gradient. Every built-in blue in the scene kit is re-tinted to these when the page is written |
| `marker` | the highlighter sweep behind a key word (any CSS colour, usually the accent at ~55% alpha) |
| `bad` | struck-out or rejected things only |
| `font`, `mono` | statement/list font and technical font. Inter and JetBrains Mono resolve automatically in HyperFrames; others need an `@font-face` in the schedule's extra CSS |
| `caption_ink`, `caption_active` | caption text and the currently spoken word |

Lock the caption keys once a style is approved for a channel.

## config.json (written by init_workspace.py)

`init_workspace.py` writes `source`, `mode`, `w`, `h`, `fps`, `orientation` and `clips`, and keeps every other key on
a re-run. Add the rest by hand.

| Key | Meaning |
|---|---|
| `source` | the input file or folder; exports go to `<source>/final` by default |
| `mode` | `clips` (a folder, one segment per clip) or `single` (one file, split at pauses) |
| `w`, `h`, `fps`, `orientation` | the output format, from the first clip |
| `clips` | `key` (`c01`...; `m01`... for inserts), `path`, `dur`, `audio` |
| `language` | Whisper language code, default `en` |
| `captions` | `burn` (default, burned into the B-roll page) or `srt` (nothing burned; upload the .srt) |
| `bubble` | `[cx, cy, r]` of a face-cam bubble baked into a screen recording, in pixels. Masks it from scene detection, overlays it across wipes, and is what the bubble checks crop |
| `bubble_layout` | B-roll PIP bubble placement override: `r`, `cx`, `cy` on the canvas, `src_r`, `src_cx`, `src_cy` in the face frame |
| `bubble_shape` | `circle` for a round PIP bubble instead of the default portrait panel |
| `panel_layout` | panel size override: `w`, `h`, `src_h` |
| `type_scale` | scales B-roll type in the wide 16:9 boxes (FULL, PIP); ~1.45 for a 16:9 talking head |
| `split` | SPLIT window around the face: vertical `headroom` (default 0.5) and `below` (0.75), in face heights; 16:9 `width` (0.44 of the frame). A large face (a vertical reframe of a landscape camera) leaves the graphic a sliver at the defaults: `{"headroom": 0.2, "below": 0.5}`. The build report prints `SMALL SPLIT PAGE` when it is needed |
| `inserts` | written by `insert_segment.py`; do not edit by hand |
| `screen_cuts`, `screen_lags` | written by `assemble.py --screen` |

## overrides.json (your edit decisions)

Read by `cutpoints.py` (drop, in, out, splice) and `assemble.py` (video_out). Keys are segment ids as printed
(`c03_s01`); times are seconds in the SOURCE clip. Re-running `cutpoints.py` keeps them and applies them last.

| Key | Use |
|---|---|
| `drop` | segments to remove: retakes, false starts, asides |
| `in` / `out` | hard head and tail times when the detector is wrong. Place them with `align.py`, never from Whisper's word times |
| `video_out` | the picture ends here (split edit) while the audio plays to `out`; the next segment's picture starts early by the same amount |
| `splice` | ranges removed from inside a segment (`pauses.py --apply` writes these; slips are added by hand after the proof in `references/cutting.md`). The segment becomes `<key>`, `<key>b`, ... |

## Other workspace files you may write

`caption_fixes.json`: ASR spelling fixes for captions, matched case- and punctuation-insensitively; `_keep` holds a
phrase together in one caption.

```json
{"Cloud Code": "Claude Code", "11am": "11 AM", "_keep": ["Save My Seat"]}
```

`transitions.json` (written by `transitions.py detect`, then edited by hand): `joins` (incoming segment keys that get a
wipe), optional `bubble` per-join timing overrides, optional `bubble_at_cut`, optional lower-third `card`.

```json
{"joins": ["c04_s01", "c09_s01"],
 "bubble": {"c09_s01": {"out_keep": -0.33}},
 "card": {"before": "c09_s01", "text": "Up next: the full architecture", "secs": 6}}
```
