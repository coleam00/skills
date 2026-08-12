# The validation harness scaffold

Component 5. The longest part of the build, and the only one that decides whether the
other four produced anything worth keeping.

## It is not Python-only, and it is not web-only

The **step ladder** is the same in every factory. Every **command** it runs lives in
`harness.config.json`, and how it reaches your software is one of three drivers:

| driver | what it is | `APP_STARTED` means |
|---|---|---|
| `http` | a server, started on a dynamic port and polled until healthy | it answered |
| `cli` | a command, invoked with args; stdout/stderr/exit code asserted | the smoke invocation worked |
| `library` | no process at all; the E2E imports and calls it | it imports |

Verified end to end on three shapes:

```
Python HTTP service   STATIC_OK · UNIT_PASSED tests=8 · APP_STARTED port=… · E2E_PASSED steps=6 · HOLDOUT_PASSED · MUTATIONS_OK · GATE_OK
Node CLI              STATIC_OK · UNIT_PASSED tests=5 · APP_STARTED driver=cli · E2E_PASSED steps=4
Python library        STATIC_OK · UNIT_PASSED tests=4 · APP_STARTED driver=library · E2E_PASSED steps=4
```

The Node run changed **five values** in `harness.config.json` - `static`, `unit`,
`unit_count_pattern`, `driver`, `cli.invoke` - and nothing else. `harness.config.json`
carries worked examples for Node, Go, Rust, Ruby and .NET.

### A frontend app: `http` plus a browser, and the browser is not free

That used to be the whole of what this file said about visual apps, and it is true about
the easy half. Someone built one to check: `driver: "http"` needed **no code changes** -
five values in `harness.config.json` - and the resulting gate caught a **CSS-only** defect
(a meter width pinned to a constant) that `STATIC_OK` and all eight unit tests sailed past.
That is the claim working.

The other half is yours to write, and three things bite:

1. **Never `capture_output=True` on a browser CLI.** Playwright's driver server,
   chromedriver and `agent-browser` all spawn a **persistent daemon** that inherits the
   stdout pipe, so `communicate()` blocks on EOF long after the CLI itself exited. The
   observed result was `APP_STARTED` followed by silence, forever. Redirect to a real file
   handle instead. `ci.py` now puts a **watchdog** on this rung (`e2e_timeout_s`, default
   300) because it was the one rung with no timeout - but a killed gate is still a failed
   lap, so avoid the deadlock rather than relying on the deadline.
2. **Tear the browser down yourself.** `appproc.py` kills the *server*; it has never heard
   of a browser daemon. Close the session in a `finally`, and key the session name to
   `app.port` so two laps cannot share one browser. Skipping this left 37 orphaned Chrome
   processes on the machine that tested it.
3. **A missing browser is a FAILURE, not zero assertions.** Raise, print, exit non-zero. A
   `shutil.which` that returns `None` must never read as a clean run - that is
   empty-is-not-pass wearing a different hat.

**Assert what only a browser knows** - computed colour, rendered geometry, which of two
elements is actually on screen. `200 OK` and "the div is in the HTML" are both true of a
page with `display:none` on the wrong element.

**Install it deliberately, and on the runner too:** `npm i -g agent-browser && agent-browser
install`, or `pip install playwright && playwright install chromium`. It is a few hundred
megabytes and nothing else in this scaffold will tell you it is missing until gate time.

**Where the browser wrapper lives is a real decision.** The holdout's rule 2 is *duplicate,
do not import*, with a carve-out for `appproc.py` because starting a process is not an
assertion. A browser wrapper is exactly that kind of driver code, but the natural place to
put it is `harness/e2e.py` - the **builder's** side of the wall. Put it in its own module
next to `appproc.py` and import it from both sides under the same carve-out. Leaving it in
`e2e.py` and importing that from the holdout hands the builder edit rights over the thing
that judges it.

**`references/validation-harness.md` describes a rung 5, "visual / screenshot judging",
that this scaffold does not implement.** Screenshots you capture are artifacts nobody
reads unless you write something that reads them. Treat rung 5 as a thing to build, not a
thing you have.

**Borrowing somebody else's defect set does not silently pass.** Pointed at the wrong
repo, the mutation runner reports `NOT_INJECTED` per defect and fails the gate rather
than scoring a perfect run against anchors it never found.

**These files do not all go to the same place, and the paths are the point.**

```bash
cp -r templates/harness            <repo>/harness          # the checks the builder MAY read
cp -r templates/harness/holdout    <repo>/.factory/holdout # the ones it MAY NOT
cp    templates/harness/locks/floor.json <repo>/.factory/locks/floor.json
rm -rf <repo>/harness/holdout <repo>/harness/locks         # they have moved
```

Resulting layout:

```
harness/
  ci.py              the entrypoint. FACTORY_VALIDATE_CMD points here
  appproc.py         start the app on a dynamic port, wait for health, tear down
  e2e.py             ONE user journey. Your assertions go here
  mutations/
    run.py           break the software on purpose, require the gate to notice
    defects.json     the defect set. PROTECTED
.factory/
  holdout/run.py     assertions the builder cannot read. PROTECTED
  locks/floor.json   the ratchet. PROTECTED
```

`harness/` is readable by the builder; `.factory/holdout/` is blocked by
`--disallowedTools` on every node and by `guard.py` as a protected path. **Putting a
holdout scenario in `harness/` silently deletes the independence property** - it still
runs, it still passes, and it stops being evidence.

---

## It runs before you edit it

```bash
python harness/ci.py            # the whole gate
python harness/ci.py --quick    # the subset an implementing node runs on itself
python harness/mutations/run.py # prove the gate can fail
```

Out of the box, against a small HTTP service, that produces `STATIC_OK`,
`UNIT_PASSED tests=N`, `APP_STARTED`, `E2E_PASSED steps=5`, `HOLDOUT_PASSED`,
`MUTATIONS_CAUGHT`, `GATE_OK`. **Every assertion in it is a worked example and all of
them should be deleted.**

## What to write, in order

**1. `e2e.py` - one journey, the most valuable one.** The answer to interview R1.1.
Assert what a *user would notice*, not a status code: `200 OK` is not evidence the page
said the right thing. Count the assertions; the gate compares that count to a floor.

**2. `.factory/holdout/run.py` - the same product, composed.** Written *before* the work,
never shown to the builder, duplicating rather than importing so a refactor cannot
re-couple it. The dominant real failure is not cheating - it is **feature isolation**,
components individually correct that never work together. Unit tests test features in
isolation by definition, so what they measure is precisely the thing that is not broken.

**3. `harness/mutations/defects.json` - six or seven deliberate defects.** The only thing
in the gate that measures your *harness* rather than your code. Until you run it you have
no evidence any of your checks can fail at all.

**4. `.factory/locks/floor.json` - the numbers, raised by hand.** Watch the slack: the gap
between observed and floor is exactly how many assertions can be deleted with the gate
still green, and it *grows* as the harness improves, because raising the floor is a
protected edit the factory cannot make.

## The two rungs that are not optional

`ci.py` runs without a holdout or a mutation set - and says so, loudly:

```
HOLDOUT_ABSENT   nothing above the independence line ran
MUTATIONS_ABSENT this gate has never been shown to fail
```

That is a legitimate state on day one and an indefensible one at level 3. Everything
below the independence line sits inside the agent's optimisation loop; given enough
attempts it will satisfy those checks rather than the thing you meant. **The step change
is independence, not volume** - more tests below the line is not the fix.

Add `HOLDOUT_PASSED` to `FACTORY_REQUIRED_MARKERS` the day you write one, and the gate
enforces it from then on. `factory_doctor` blocks level 3 until you do.
