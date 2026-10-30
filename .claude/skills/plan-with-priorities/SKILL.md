---
name: plan-with-priorities
description: Plan a product or technical decision by eliciting the user's priorities before recommending options. Use when the user wants help deciding what to build or which approach to take, especially when the goals or tradeoffs are unclear. Supports small spikes when the user needs to try alternatives before choosing.
---

# Plan With Priorities

Use the supplied idea, decision, PRD or brief, plus any reference paths.

Adapted from Cole's interview-first `plan-create-prd` and `plan-architecture` workflow. This skill adds a deliberate separation between learning what matters to the user and recommending a way to achieve it. It can be used on its own; no other skill is required.

The conversation is the work. Do not produce a finished plan while consequential preferences are still guesses. Recommendations are useful, but the user should be able to see whose priorities they optimize.

## Read the situation

Read the supplied brief and relevant project context before asking about facts already available. Separate:

- Established facts and hard constraints, with their source.
- Priorities the user explicitly stated, keeping their meaning and noting where they came from.
- Your inferences and unanswered preferences. An existing design is evidence of an earlier choice, not proof the user wants it forever.

Keep the read proportional to the decision. Do not turn a small scope discussion into a codebase audit. If essential context is unavailable, name that gap.

## First, learn what matters

Before ranking solutions for a consequential decision, check whether the user has already supplied the relevant goal and tradeoff. If they have, use those answers and move on; do not make them repeat an interview.

If priorities are missing, ask one or two open questions about the user's experience, desired outcome or unacceptable cost. For example, ask what currently gets in their way or what would make the change worthwhile. Do not attach a recommended answer, preselect an option, suggest a preferred solution, or hide a ranking inside the question. Then stop and wait.

When the answer is vague, ask for a concrete recent situation. If examples would help, offer balanced, unranked examples and leave room for something else. The user can be unsure; do not demand invented numerical weights or a confident preference.

Briefly reflect the priorities you heard before recommending, distinguishing any inference that still matters. Ask about a missing tradeoff only if its answer could change the recommendation. A user may revise priorities after seeing options or trying a prototype.

If the user explicitly delegates a decision or asks you to proceed without an interview, respect that. State the assumptions behind your recommendation and mark the decision as delegated. Keep any priorities or constraints they did supply separate from those assumptions; delegation does not make known facts uncertain. Do not present an inferred preference as something the user said. Routine, cheap, reversible decisions do not need this entire process.

## Then, compare and recommend

Present two or three credible approaches at comparable detail, including keeping the current approach when it is viable. Explain the tradeoffs against the user's stated priorities, and distinguish technical evidence from value judgments. Do not manufacture an inferior alternative to make your favorite look inevitable.

Give a conditional recommendation: why this option fits the stated priorities, which tradeoff it accepts, and what missing fact or changed priority would make another option preferable. Keep the strongest honest case for that alternative visible. If new information changes your advice, say what changed instead of defending the earlier answer. A changed preference does not erase a verified constraint; explain when no option satisfies both.

Ask for the user's decision without a preselected response, then wait. For an important choice, invite them to state which tradeoff they are willing to accept in their own words. This is an opportunity to correct your interpretation, not a compulsory quiz or a requirement to disagree. An explicit yes or delegation is valid; do not attribute reasoning the user did not provide.

## Spike when an answer needs experience

If the user cannot judge a preference without seeing or using something, or if a technical unknown could change the decision, propose a small spike rather than another round of speculative questions.

Agree on the smallest useful comparison:

- The uncertainty to resolve, and whether it concerns preference or feasibility.
- One or more small, disposable versions, with the same task and inputs so the comparison is fair.
- A time or resource bound, and what to observe. For a preference question, the observation may be the user's experience rather than a numerical winner.
- What would change the decision, and what the spike will not establish about production readiness.

State the decision rule explicitly in the proposal: which observation would favor each approach, or which unresolved criterion the user needs to supply. Do not substitute a list of things to watch for a decision rule, and do not invent a threshold the user never agreed to.

A smaller, cheaper model can build a bounded spike if it can handle the task. Independent versions can be built in parallel when useful and authorized. Keep scope, acceptance checks and presentation quality comparable; do not confuse a model's implementation mistake with evidence that an approach is bad.

Proposing a spike is not permission to implement or launch agents. Carry out the work when authorized, in isolated disposable files or branches. Stay within the agreed resources and avoid production services or data unless the user specifically includes them. If the first comparison is inconclusive, report that rather than declaring a winner.

## Keep a short decision record

Once a decision is made, summarize the chosen approach, the user-stated priorities, the accepted tradeoff, the evidence or observations, and the condition that would justify revisiting it. Distinguish a user choice from an explicitly delegated choice. Preserve unresolved preferences instead of silently resolving them.

Keep it in the conversation unless the user asks for a file or an existing workflow already calls for one. If producing a PRD, keep product intent separate from engineering choices. If producing architecture notes, keep them at the approach level; implementation tasks come later.

This is a planning practice, not a validated method for eliminating bias. Asking questions, showing alternatives or getting approval does not by itself prove independent judgment.

## Background

- [Anthropic's study of agents and expert judgment](https://www.anthropic.com/research/agents-judgment-calls) motivates examining how recommendations influence defensible choices. It did not test this skill.
- [Matt Pocock's Grill Me guide](https://www.aihero.dev/skills-grill-me) already warns against passive agreement during planning interviews.
- [Research on cognitive forcing](https://arxiv.org/abs/2102.09692) supports testing deliberate reflection before relying on AI advice, while also finding usability costs. Its results are not a validation of this workflow.
