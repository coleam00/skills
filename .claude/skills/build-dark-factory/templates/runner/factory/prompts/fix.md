<!--
  THIS PROMPT IS THE INTERVIEW'S OUTPUT, not machinery. It is the one file in the runner
  you are MEANT to rewrite.

  The factory's whole claim is that it runs YOUR process with the approvals removed. So
  these seven prompts should be recognisably your planning step, your implementation
  step, your review step - loading the skills, rules files and MCP servers you already
  load at each one. What is here is a worked example from a real factory, kept because
  the shape is worth stealing; the words are not.

  Every <ANGLE-BRACKET> below is a decision from the interview. factory_doctor reports a
  prompt that still contains one.
-->

# fix-pr

Run the `piv-fix-review-findings` skill against the validator's findings:

- **the verdict** — `{{findings}}`
- **the raw validation output** — `{{gatelog}}`

Read the verdict first. Read the log when a finding names a check, because the log says
what the check actually printed and the verdict says what the judge made of it.

## What you get, and what you do not

You get **the findings and the issue**. You do not get the plan or the implementation
report, deliberately: a fix that re-reads the plan tends to re-argue the plan rather than
address the finding, and the finding is the only thing that failed.

## Fix the finding, not the symptom

Take the findings one at a time, highest severity first. For each, fix the cause in the
source.

**The prohibition that matters most here** (`FACTORY_RULES.md` §2.1, §6.4): when a check
is red, the cheapest repair is always to make the check quieter. Deleting the assertion,
loosening the tolerance, shrinking the sample, adding a special case for the test input,
catching and swallowing - all of these turn the light off rather than fix the wiring, and
all of them are an auto-reject.

The paths that would let you do it are denied to this node, so the attempt will fail
rather than succeed quietly. Read that as the design working, not as an obstacle: if
fixing the finding genuinely requires changing a check, then the finding is not a code bug
and the correct move is to say so and stop. That is a `needs-human` escalation and it is a
perfectly good outcome.

## Attempt cap

You are attempt {{attempts}} of 2. On the second failure this escalates and stops. If you
do not believe the finding is fixable within scope, say so **now** rather than spending the
last attempt on a guess - an escalation with a clear reason is worth more than a second
failed cycle.

## Then

run **exactly this command, verbatim** - it is the only one on your allowlist:

```
{{quick}}
```

Do not substitute another way of running the tests. `python -m unittest`, `pytest`, or
anything you would normally reach for is denied to this node, and a denied command is a
fix that never got checked. Observed on the first real fix run: the node named the
config *variable* instead of the command, tried `echo $FACTORY_VALIDATE_QUICK`, was
refused, fell back to `python -m unittest discover`, was refused again, and committed a
fix it had never executed. The fix happened to be right. That is luck, not a process.

Then hand back to the independent validator. A fix is never self-certified: the node that
made the change does not get to decide the change worked.
