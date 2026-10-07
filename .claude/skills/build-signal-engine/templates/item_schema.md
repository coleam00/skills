# The item shape

Every source maps to this before it is stored. Nothing downstream knows which source an
item came from except through these fields.

| Field | Type | Notes |
|---|---|---|
| `id` | string | **Stable.** The source's own id (`reddit:t3_abc`, `hn:4231`), or a hash of url + heading + the first ~200 body characters for changelog entries. Same item, same id, every run. |
| `source` | string | The source's name from `PROFILE.md` |
| `title` | string | What the item is, in one line. For changelog entries: label + heading + first real sentence |
| `url` | string | Where a human reads it |
| `body` | string | Text, capped (a few thousand characters). Never the whole comment tree |
| `published_at` | datetime or null | From the source, or parsed from a changelog heading |
| `engagement` | number or null | Upvotes, points, stars or views. Used only by code filters and ranking |
| `metadata` | object | Anything else worth keeping (community, author, comment count) |

Stored alongside, by the pipeline:

| Field | Set by |
|---|---|
| `filtered_by` | the code filter or decision route that dropped it, or null |
| `decision` | the decision pass answers (scores and route) |
| `in_digest` | the date of the digest it appeared in, or null |
