# Open decisions

<!--
  THE POINT OF THIS FILE IS THAT A DECISION IS ASKED ONCE.

  Without it, one unmade product decision is re-discovered by every issue that touches it
  and reported as a fresh escalation each time. Measured: four issues against one game,
  four escalations, one decision. The human sees four interruptions and concludes the
  factory refuses too much work - when it actually refused one thing, four times.

  READ ORDER, for every node that is about to stop:
    1. Is the decision already ANSWERED below? Then it is not open. Use it, cite the ID.
    2. Is it OPEN below? Then do not re-ask it. Reference the ID and either plan around
       it or leave a follow-up.
    3. Neither? Only then is it new - and even then, most product values are decided and
       recorded in ASSUMPTIONS rather than escalated. See FACTORY_RULES.md §7.

  A human answers by moving an entry to Answered and writing the value. That single edit
  unblocks everything listed against it.
-->

## Open

<!-- One per decision. Blocks: list every issue waiting on it, so the cost is visible. -->

- **D1** — <the question, in one sentence, as a decision rather than a topic>
  - **Recommended:** <the factory's proposed answer, with the reasoning that produced it>
  - **Blocks:** <#4, #5, #7>
  - **Raised:** <YYYY-MM-DD> by <workflow/node>

## Answered

<!-- Never delete one. A decision with its date is why the code looks the way it does, and
     it is the first thing anybody re-litigating it needs to read. -->

- **D0** — example: what does a tier-3 reward multiply by?
  - **Answer:** 1.5
  - **Decided:** 2026-01-01 by <human>
  - **Why:** anything below 1.4 makes tier 3 net-negative and breaks MISSION invariant 3.
