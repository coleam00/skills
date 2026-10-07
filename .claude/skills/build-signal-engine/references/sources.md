# Sources

Every source maps to the item shape in `templates/item_schema.md`. Build one source end to
end into the store before adding the next, and prove each with a real run: how many items
came back, and a second run that adds roughly zero.

## Choosing how each source is pulled

**If the user chose one data platform (R2.6), use it for every source it covers.** One
client, one credential, one bill, one item shape to map from. Keep the per-source notes
below for what to ask it for.

**What the user named is final.** A platform or a specific tool they named in the interview
is used as named. Do not run a second tool against it, do not compare prices, and do not
switch to something you found that looks better. If a named tool actually fails on a real
run, stop and tell them; do not quietly substitute.

**For a source they left open,** pick one tool on their platform: search for it (through the
platform's MCP server during the build, if it has one), take the most used one that returns
the fields the item shape needs, and prove it with one real run. Only try a second if the
first fails that run or is far too slow, and say so.

**If they asked you to pick,** choose per source from the notes below: a feed or API where
a good one exists, the page read as Markdown for changelogs, and a hosted scraper or actor
where neither works. Say which method each source got and why.

## By source type

### Changelogs and release notes (the most underrated source)

The first place a change in a tool shows up, and usually the one with the most direct
consequence (a deprecation, a new mode, a price change). Most have no feed.

- **Method:** a page-to-Markdown fetcher (Apify Web Fetch, Firecrawl, Jina Reader, or a
  plain HTTP fetch plus a readability library for static pages). Then split the page into
  entries yourself.
- **Splitting:** an entry starts at a heading that carries a date or a version
  ("September 30, 2026", "Sep 29", "2026-09-30", "v2.1.287"). Some sites put the date on
  the line under a post title instead; only fall back to that when the page has no dated
  headings at all, or the page header becomes an entry.
- **Ids:** hash of page URL + heading + the first ~200 characters of the entry body. The
  body is needed because several entries can share a heading (three "Sep 29" entries).
- **Age cap:** parse the date from the heading (a month and day with no year takes the
  current year, or last year if that would be in the future) and skip entries older than
  the cap (default 7 days). Without it, a page's first read floods the digest with last
  month's launches as if they were news.
- **Titles:** label + heading + the entry's first real sentence. Skip tag lines
  ("Feature · Model: x · API: y"), boilerplate ("Choose a tag to compare", "Subscribe") and
  fragments under five words. A tag line as the title is how a minor update gets reported
  as a launch.
- **Pick the right URL.** Many docs sites render navigation only, with the content loaded
  by JavaScript. Look for a Markdown or "llms" version of the page (some docs serve `.md`),
  the product's public changelog page rather than the docs one, or a raw `CHANGELOG.md`
  in the repo. Test each URL and check it splits before adding it.
- **GitHub releases:** use the GitHub releases API, not the releases page. It is free, and
  the page read as Markdown can come back as "There was an error while loading".
- **Consumer products** (chat apps, assistants) usually publish release notes on their help
  center. Those are often the most relevant source for someone who is not a developer.

### Communities (Reddit, forums, Hacker News)

Where people using the tools report what they found, often before anyone writes about it.

- **Hacker News:** the free Firebase or Algolia API. Filter by points in code.
- **Reddit:** the official API needs approval under Reddit's developer terms, and
  unauthenticated JSON is unreliable. The practical route is a hosted scraper (an Apify
  Actor, for example). Use listing URLs that encode the window
  (`/r/<sub>/top/?t=day` or `?t=week`), cap posts per subreddit, skip comments.
  Scrapers differ a lot in speed: in testing, `harshmaur/reddit-scraper` returned 299 posts
  in 30 seconds and another took 7 minutes for 27. If a run is that slow, that is when to
  try another one, unless the user named it.
- **Forums and Discourse:** most have RSS (`/latest.rss`) or a JSON API.
- **Discord, Slack, private groups:** only with a public archive or the owner's
  permission. Otherwise leave them out and say why.

### Video

- **A channel's uploads:** YouTube's per-channel RSS feed is free.
- **Search ("what are people making videos about this week"):** a provider or the YouTube
  Data API (search is quota-heavy). Filter by views in code. Transcripts are a separate,
  paid step; only fetch them for items that survive the decision pass.

### Papers, repos, news

- **arXiv:** the free API, by category, last N days.
- **GitHub trending:** the trending page or a provider. Check the input limits (some cap
  results per run).
- **News search:** a search API with a per-query cap. High duplication; dedupe by URL and
  by title.

## Store and dedupe

- One table of items keyed on the stable id, one of sources with a last-fetched time.
- Check ids before any paid call. A run done twice should cost once.
- Keep filtered items with the reason they were dropped. The shadow week needs them.

## Cost rules for paid sources

- **Cap every run** (max items and max spend, if the provider supports it).
- **Paid sources run on the daily schedule only,** never on a frequent scan. A source that
  quietly runs on an hourly job costs 24 times what was planned.
- **You pay for rows you drop.** An engagement floor in code does not refund the provider.
  Pull smarter instead: top-of-day or top-of-week listings, fewer posts per community, a
  longer window run less often.
- **Trim the download.** Some providers return far more than needed (whole comment trees
  on every post); ask only for the fields the item shape uses.

## Proof for Stages 1-2

A platform's run record can post charges several seconds after the run returns (Apify does,
and the per-result charge lands after the start charge). Settle costs once at the end of the
run by polling each run record until its total stops changing; a single read under-counts.

For each source, report in one line: how it is pulled, items returned, items stored, and the count on
an immediate second run (should be 0 or close to it). For a paid source, add the real cost
of that run from the provider's own run record.
