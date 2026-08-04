---
name: system-evolution-review
description: Performs a meta-level review of how well an implementation followed its plan, classifying divergences and recommending AI-Layer improvements. Use after an execution report exists to find bugs in the process, not the code.
argument-hint: "[plan-file] [execution-report-file]"
arguments: [plan, report]
---

# System Review

Perform a meta-level analysis of how well the implementation followed the plan and identify process improvements.

## Purpose

**System review is NOT code review.** You're not looking for bugs in the code - you're looking for bugs in the process.

**Your job:**

- Analyze plan adherence and divergence patterns
- Identify which divergences were justified vs problematic
- Surface process improvements that prevent future issues
- Suggest updates to AI-Layer assets (CLAUDE.md, plan templates, skills)

**Philosophy:**

- Good divergence reveals plan limitations → improve planning
- Bad divergence reveals unclear requirements → improve communication
- Repeated issues reveal missing automation → create skills

## Context & Inputs

You will analyze four key artifacts:

**Plan Skill:**
Read this to understand the planning process and what instructions guide plan creation.
`.claude/skills/piv-plan-implementation/SKILL.md`

**Generated Plan:**
Read this to understand what the agent was SUPPOSED to do.
Plan file: $plan

**Execute Skill:**
Read this to understand the execution process and what instructions guide implementation.
`.claude/skills/piv-implement/SKILL.md`

**Execution Report:**
Read this to understand what the agent ACTUALLY did and why.
Execution report: $report

## Analysis Workflow

### Step 1: Understand the Planned Approach

Read the generated plan ($plan) and extract:

- What features were planned?
- What architecture was specified?
- What validation steps were defined?
- What patterns were referenced?

### Step 2: Understand the Actual Implementation

Read the execution report ($report) and extract:

- What was implemented?
- What diverged from the plan?
- What challenges were encountered?
- What was skipped and why?

### Step 3: Classify Each Divergence

For each divergence identified in the execution report, classify as:

**Good Divergence ✅** (Justified):

- Plan assumed something that didn't exist in the codebase
- Better pattern discovered during implementation
- Performance optimization needed
- Security issue discovered that required different approach

**Bad Divergence ❌** (Problematic):

- Ignored explicit constraints in plan
- Created new architecture instead of following existing patterns
- Took shortcuts that introduce tech debt
- Misunderstood requirements

### Step 4: Trace Root Causes

For each problematic divergence, identify the root cause:

- Was the plan unclear, where, why?
- Was context missing, where, why?
- Was validation missing, where, why?
- Was manual step repeated, where, why?

### Step 5: Generate Process Improvements

Based on patterns across divergences, suggest:

- **CLAUDE.md updates:** Universal patterns or anti-patterns to document
- **Plan skill updates:** Instructions that need clarification or missing steps
- **New skills:** Manual processes that should be automated
- **Validation additions:** Checks that would catch issues earlier

## Output Format

Save your analysis to: `.claude/system-reviews/[feature-name]-review.md`

### Report Structure:

#### Meta Information

- Plan reviewed: [path to $plan]
- Execution report: [path to $report]
- Date: [current date]

#### Overall Alignment Score: \_\_/10

Scoring guide:

- 10: Perfect adherence, all divergences justified
- 7-9: Minor justified divergences
- 4-6: Mix of justified and problematic divergences
- 1-3: Major problematic divergences

#### Divergence Analysis

For each divergence from the execution report:

```yaml
divergence: [what changed]
planned: [what plan specified]
actual: [what was implemented]
reason: [agent's stated reason from report]
classification: good ✅ | bad ❌
justified: yes/no
root_cause: [unclear plan | missing context | etc]
```

#### Pattern Compliance

Assess adherence to documented patterns:

- [ ] Followed codebase architecture
- [ ] Used documented patterns (from CLAUDE.md)
- [ ] Applied testing patterns correctly
- [ ] Met validation requirements

#### System Improvement Actions

Based on analysis, recommend specific actions:

**Update CLAUDE.md:**

- [ ] Document [pattern X] discovered during implementation
- [ ] Add anti-pattern warning for [Y]
- [ ] Clarify [technology constraint Z]

**Update Plan Skill ($plan):**

- [ ] Add instruction for [missing step]
- [ ] Clarify [ambiguous instruction]
- [ ] Add validation requirement for [X]

**Create New Skill:**

- [ ] A new skill for [manual process repeated 3+ times]

**Update Execute Skill:**

- [ ] Add [validation step] to execution checklist

#### Key Learnings

**What worked well:**

- [specific things that went smoothly]

**What needs improvement:**

- [specific process gaps identified]

**For next implementation:**

- [concrete improvements to try]

## Important

- **Be specific:** Don't say "plan was unclear" - say "plan didn't specify which auth pattern to use"
- **Focus on patterns:** One-off issues aren't actionable. Look for repeated problems.
- **Action-oriented:** Every finding should have a concrete asset update suggestion
- **Suggest improvements:** Don't just analyze - actually suggest the text to add to CLAUDE.md or skills
