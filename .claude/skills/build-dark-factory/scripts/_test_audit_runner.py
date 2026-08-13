r"""Does each audit in `_audit_runner.py` actually FIRE?

    python scripts/_test_audit_runner.py

Break one thing at a time in a COPY of the skill and require the audit to notice. Same
principle as `_test_runner.py --mutate` and `_test_factory_doctor.py`: an audit that has
never gone red is an audit nobody has tested, and a checker is exactly the kind of code
whose failure mode is silence.

It earned itself on the first run. The "does this script have an ERR trap" check used the
regex `^\s*trap\s+.*ERR`, which matches `trap - ERR` -- the line that DISARMS the
trap, and the first line of every handler. So deleting the trap INSTALLATION while leaving
the handler behind, which is what a careless edit does, read as fully protected. The most
important check in the audit had a false negative, and nothing but this file would have
found it.

The skill's own copy is never modified: every case runs against a temp clone.
"""
import io, re, shutil, subprocess, sys, tempfile, pathlib

SK = pathlib.Path(r"C:\Users\colem\OpenSource\skills\.claude\skills\build-dark-factory")

CASES = [
    # (label, relative path under the COPY, find, replace, substring the audit must print)

    # --- the three user-facing rules. Each came from Cole using the skill and finding it
    # --- unusable in a specific way, and none can be caught by a behaviour test, because
    # --- they are properties of what the agent SAYS.
    ("a duration estimate in SKILL.md", "SKILL.md",
     "## Output discipline", "This takes about three days.\n\n## Output discipline",
     "estimates how long something takes"),
    ("a question marked [PROSE] again", "references/interview.md",
     "### R1.1 -", "### [PROSE] R1.1 -",
     "[PROSE]"),
    ("jargon back in a question the user reads", "references/interview.md",
     "### R2.2 - \"What would make you stop",
     "### R2.2 - \"What invariant must hold, and what would make you stop",
     "no reason to know"),
    ("the output-discipline rule deleted", "SKILL.md",
     "## Output discipline - read this before you write a single word to the user",
     "## Some other heading entirely",
     "no output-discipline rule"),

    ("config knob not exported", "templates/runner/factory/config.sh",
     "       FACTORY_SIZE_CAP \\", "",
     "FACTORY_SIZE_CAP"),
    ("a state nothing can act on", "templates/runner/factory/state.py",
     '"failed": {"open", "rejected", "needs-human"},',
     '"failed": {"open", "rejected", "needs-human"},\n    "orphaned": {"open"},',
     "orphaned"),
    ("unsubstituted prompt placeholder", "templates/runner/factory/prompts/plan.md",
     "{{issue}}", "{{no_such_placeholder}}",
     "no_such_placeholder"),
    ("ERR trap removed from the runner", "templates/runner/factory/run-workflow.sh",
     "trap 'on_unguarded_error", "# trap 'on_unguarded_error",
     "no ERR trap"),
    ("a label no init-labels.sh creates", "templates/runner/factory/gh_backend.py",
     '"accepted": "factory:accepted",', '"accepted": "factory:never-created",',
     "factory:never-created"),
    ("a $ followed by a digit in SKILL.md", "SKILL.md",
     "## Phase 0. The input", "Costs $6 to run.\n\n## Phase 0a",
     "positional argument"),
    ("SKILL.md cites a question that does not exist", "SKILL.md",
     "## Phase 0. The input", "See R9.9 for details.\n\n## Phase 0a",
     "R9.9"),
    ("SKILL.md names a file that is not there", "SKILL.md",
     "## Phase 0. The input", "Read `references/nonexistent-guide.md`.\n\n## Phase 0a",
     "nonexistent-guide.md"),
]

tmp = pathlib.Path(tempfile.mkdtemp(prefix="audit-verify-"))
passed = failed = 0
try:
    for label, rel, find, repl, want in CASES:
        dest = tmp / re.sub(r"\W+", "-", label)
        shutil.copytree(SK, dest, ignore=shutil.ignore_patterns("__pycache__"))
        target = dest / rel
        s = io.open(target, encoding="utf-8").read()
        if find not in s:
            print(f"  SKIP  {label:<44} the text it breaks is gone; update this case")
            print(f"        looked for: {find[:70]}")
            failed += 1
            continue
        io.open(target, "w", encoding="utf-8", newline="\n").write(s.replace(find, repl, 1))

        p = subprocess.run([sys.executable, str(dest / "scripts" / "_audit_runner.py")],
                           capture_output=True, text=True, errors="replace", timeout=200)
        out = (p.stdout or "") + (p.stderr or "")
        fired = "FIND" in out and want in out
        if fired:
            passed += 1
            print(f"  FIRED {label}")
        else:
            failed += 1
            print(f"  MISSED {label}")
            print(f"         expected a finding mentioning {want!r}")
            print("         " + "\n         ".join(
                [l for l in out.splitlines() if "FIND" in l][:4] or ["(no findings at all)"]))
        shutil.rmtree(dest, ignore_errors=True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print(f"FIRED={passed}  MISSED={failed}  of {len(CASES)}")
sys.exit(1 if failed else 0)
