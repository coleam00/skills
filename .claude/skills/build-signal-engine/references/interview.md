# The interview

**Three questions decide the engine. Five more only the user can answer. Everything else
is a default they confirm.**

The interview exists because a signal engine is only as good as its filter, and nobody can
write their filter on demand. Ask "what are your interests?" and you get a list of topics,
which is the vague input that makes every item look relevant. Ask what they missed last
month, and where it first showed up, and you get a source and a rule.

**Ask about things that already happened. Never ask the user to design an artifact.** They
do not write the decision question, the source list or the filters. They tell you about
last week, and you turn that into all three, then play it back.

## Rules for every question

**Every question goes through the question tool** (`AskUserQuestion`, or the equivalent).
It always carries an "Other" free-text answer, so an open question loses nothing, and a
user who would have typed "you pick" corrects the closest of three drafts instead.

- Two to four options, one marked `(Recommended)` and first, its reason in one line.
- Draft options from what they already told you, and say where each came from. Before
  Round 1 you only have their opening message; use it.
- `header` is 12 characters or fewer.
- Round 1 questions go one at a time, in order. Later questions can share a call (up to
  four).
- A question that wants a list is a multi-select of drafted candidates plus Other. What
  they deselect is as useful as what they keep.
- Offer **"Explain this first"** where a term is not obvious (decision model, stable id,
  shadow week). One breath, in the words below, then ask again.
- Reflect each answer back as the concrete thing it became: "so the first source is the
  Claude Code changelog, read every morning". Then move on.

**Say where the finish line is.** After Round 1: "Five more about your last few weeks, then
one message of defaults, then I start building."

---

## Round 1 - the three that decide the engine

### R1.1 - "What do you need to keep up with, and what would you do differently if you knew about it the day it happened?"

**What it becomes:** the focus line in `PROFILE.md` and the first draft of the decision
question. The second half is the important part. "I'd update my agent before it breaks"
gives a question ("does this change how a tool I use behaves?"); "I'd know what's going on"
gives nothing to filter on.

**Draft options from their opening message.** For someone who said "keep up with AI":
- "New releases and changes in the AI tools I use, so I can try or update them that week (Recommended)"
- "What's actually new in AI research, so I can learn it before it's everywhere"
- "What people building with AI are finding, so I can steal what works"

**Push back on:** a topic list with no action ("LLMs, agents, RAG"). Ask once: "If an item
about agents showed up tomorrow, what would make you open it versus skip it?" That answer
is the filter.

### R1.2 - "Tell me about something you found out about late, or missed entirely. Where did it first show up?"

**What it becomes:** the first source, and proof that the engine would have caught the
miss. This is the single best predictor of which sources matter, because it is evidence
instead of a guess.

**Draft options:** a changelog or release notes page ("a model being deprecated, found out
when it broke"), a community thread ("someone on a subreddit found the fix first"), a
creator's video. Recommend the changelog option when they named a tool, because it is the
source almost nobody watches and the one with the most direct consequence.

**Push back on:** "on Twitter, I think." Ask where the original came from. Social posts
are usually the second place news appears; the first place is a changelog, a repo, a paper
or a forum, and the engine should read the first place.

### R1.3 - "When this arrives every morning, where do you read it, and what do you do with an item you care about?"

**What it becomes:** delivery and output format. "I read it in Obsidian and add the good
ones to a to-try list" means a markdown digest with a link and one line per item. "I make
videos about them" means the digest plus an ideas section, which is an extension, not the
core.

**Draft options:** "A markdown note in my notes app (Recommended)", "an email", "a chat
message (Slack, Discord, Telegram)". Add "my notes app, plus content ideas" if they create
content.

---

## Round 2 - what only they can answer

Ask these together where they fit in one call.

### R2.1 - "Which tools or products do you use most days?" (multi-select)

**What it becomes:** the changelog and release-notes sources. Draft from R1.1 and R1.2,
for example their coding agent, their model provider's API, their editor, their framework.
For each pick, find the official changelog, release notes or releases feed yourself; do not
ask them for URLs.

### R2.2 - "Where do people using those tools actually talk?" (multi-select)

**What it becomes:** community sources. Draft the obvious subreddits, forums, Discords
with public archives, Hacker News, and video (YouTube search for what people are making
videos about this week) when the topic has creators. Four options is the limit, so merge
the subreddits into one option if you need the room. If they say "Discord", ask whether it
has a public archive; a private server is not a source the engine can read legitimately.

### R2.3 - "Pick three things from the last week or two you'd have wanted in your digest, and three you never want to see again."

**What it becomes:** the keep/drop examples in `PROFILE.md`, the test set for Stage 4, and
the wording of the decision question. This is the most valuable answer in the interview.
Ask for their own examples first: say in the question that they can type their own three and
three in the free-text answer ("Other"), which is the answer you want most. Do not make
"I'll type my own" an option; picking an option opens no text box. Offer two or three
plausible drafts from their earlier answers as multi-select options they can accept. Only if
they cannot name any from memory, offer to pull a sample of real items from their sources
after Stage 2 and have them sort it then; never mark that fallback as recommended, and note
it in `PROFILE.md`.

**Push back on:** examples that are all one kind. If every "keep" is a model release, ask
for one that is not, or the question will only ever keep model releases.

### R2.4 - "What's too old, too small or too far off to matter?"

**What it becomes:** code filters. Age ("older than a week is history"), engagement ("a
post with five upvotes is noise"), language, length. Turn every answer into a number in
code. If an answer is a judgment ("too basic"), it belongs in the decision question, not
in a filter.

### R2.5 - "Which would be worse: the digest missing something big, or the digest wasting your time?"

**What it becomes:** the routing thresholds. "Missing something big" means drop only when
sure, and send the uncertain middle to the LLM. "Wasting my time" means a tighter digest
cap and a stricter keep. Recommend "missing something big" as the default; a missed
deprecation costs more than one extra item.

### R2.6 - "Do you want your sources to come through one data platform, or should I pick per source?"

**What it becomes:** how every source is pulled. Options: one data platform for everything
(Recommended: one client, one credential, one bill and one spending cap, and the engine
maps one output shape), a platform they already use (name it), or "you pick per source".
If they name a platform, it is the answer for every source it covers. Do not talk them out
of it; ask whether it has an MCP server you can use while you build.

**They can also name the exact tool for a source** ("Reddit through harshmaur/reddit-scraper,
changelogs through Web Fetch"). A named tool is final: write it into `PROFILE.md` and use it.
Never test an alternative against it, and never swap it for a cheaper or faster one. Only
the sources they left open are yours to choose.

---

## Round 3 - the defaults, in one message

One message, every remaining setting with its default filled in, ask what to change:

| Setting | Default |
|---|---|
| Schedule | daily, early morning, local time |
| Stack | Python + uv, or whatever their repo already uses |
| Storage | SQLite file in the repo, gitignored |
| Per-source cap | 50-100 items per source per run, plus a spending cap on anything billed |
| Decision model | Jev via OpenRouter if they have a key, otherwise a small fast LLM with structured output |
| Reading model | a mid-tier LLM; the reading pass is one call per run |
| Digest | ten items, grouped, one or two sentences each, every link kept |
| Delivery | `digests/YYYY-MM-DD.md` in the repo, plus their R1.3 destination |
| Shadow week | on |

## Explanations, one breath each

- **Decision model:** a model that only answers typed questions (yes/no, pick one, a
  score) with probabilities, in milliseconds, for a fraction of a cent. It writes no text,
  so it makes the quick call on every item and the LLM does the reading.
- **Stable id:** the same item always gets the same id, so the engine knows it has seen it
  and a re-run adds nothing new. Without it, every run is a full re-read.
- **Shadow week:** the engine runs for a week while they read the digest and mark misses
  and noise. Nothing is trusted until that week says so.

## Closing the interview

Write `PROFILE.md`, read it back as a proposal in one short message, and ask one question:
"Build it like this?" with options to build, change something, or explain a part. Then
Stage 1.
