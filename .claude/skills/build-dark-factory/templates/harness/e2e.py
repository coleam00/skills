"""The end-to-end path: ONE journey, the most valuable one, as the real user does it.

Not a suite. The answer to interview R1.1 - "the single most valuable thing a user does
with this app, as a sequence of actions ending in something you can see on a screen."

THIS IS WHERE THE ASSERTIONS LIVE, and they are the part of the harness nobody can write
for you. Everything else in `harness/` is plumbing that is the same in every factory;
these lines are the only place your product appears.

Three rules that decide whether any of it is worth anything:

  1. ASSERT WHAT A USER WOULD NOTICE, not a status code. `200 OK` is not evidence that
     the page said the right thing. A test that only checks the status passes on an app
     that returns an empty body forever.
  2. COUNT THE STEPS. `run_e2e` returns how many ASSERTIONS ran, and the gate compares
     that to a protected floor. A skipped assertion and a passed assertion are
     indistinguishable without a count.
  3. RETURN None ON FAILURE, having printed why. The caller turns that into a named
     GATE_FAILED so the log says which rung broke.
"""
from __future__ import annotations

import json

STEPS = 0


def check(name: str, ok: bool, detail: str = "") -> bool:
    global STEPS
    STEPS += 1
    if ok:
        print(f"  ok    {name}", flush=True)
        return True
    print(f"  FAIL  {name}  {detail}", flush=True)
    return False


def run_e2e(app) -> int | None:
    """Drive the app as a person does. Returns the assertion count, or None on failure."""
    global STEPS
    STEPS = 0

    # SCAFFOLD_EXAMPLE_DELETE_THIS_LINE_WHEN_YOU_WRITE_YOUR_OWN
    # ===================================================================
    # TODO: REPLACE EVERYTHING BELOW WITH YOUR OWN JOURNEY.
    # Delete the marker line above once these are YOUR assertions. factory_doctor
    # blocks on it, because a gate asserting things about somebody else's product
    # is worse than no gate: it is green.
    #
    # What is here is a worked example against the shape of a small HTTP service, kept
    # because the SHAPE is worth stealing: act, then assert something observable about
    # what came back. Delete it and write yours.
    # ===================================================================

    # --- the user arrives ------------------------------------------------
    status, body, _ = app.get("/")
    if not check("the landing page renders", status == 200 and "<" in body,
                 f"status={status}"):
        return None

    # --- the user does the main thing ------------------------------------
    target = "https://example.com/a/long/path?with=params&more=1"
    status, body, _ = app.post("/api/shorten", json.dumps({"url": target}))
    if not check("the primary action succeeds", status == 200, f"status={status}"):
        return None

    try:
        code = json.loads(body)["code"]
    except (ValueError, KeyError):
        return None if not check("the response is the documented shape", False,
                                 f"body={body[:120]!r}") else None

    # --- the user sees the result ----------------------------------------
    # The assertion that matters. Not "did it 302" - WHERE to, byte for byte. A redirect
    # that silently rewrites its destination passes every status-code check ever written.
    status, _, headers = app.get(f"/{code}")
    location = headers.get("Location", "")
    if not check("the result is byte-identical to what was asked for",
                 status == 302 and location == target,
                 f"status={status} location={location!r} wanted={target!r}"):
        return None

    # --- the unhappy path a user will actually hit ------------------------
    status, body, _ = app.get("/does-not-exist-000")
    if not check("an unknown input fails cleanly rather than crashing",
                 status == 404, f"status={status}"):
        return None

    # --- idempotence / the product's own promise --------------------------
    _, body2, _ = app.post("/api/shorten", json.dumps({"url": target}))
    try:
        again = json.loads(body2)["code"]
    except (ValueError, KeyError):
        again = None
    if not check("the documented guarantee holds on a second run", again == code,
                 f"first={code} second={again}"):
        return None

    # --- the operational readout reflects reality -------------------------
    # ADDED BECAUSE A MUTATION ESCAPED. `health-always-reports-zero` replaced the link
    # count with a literal 0 and every check above still passed: the endpoint answered,
    # the shape was right, and the number was a lie. Nothing asserted the count MOVED.
    #
    # This is the whole argument for mutation testing in one example. No amount of
    # reading these assertions would have found it; breaking the software on purpose
    # found it in one run.
    status, body, _ = app.get("/health")
    try:
        links = json.loads(body).get("links")
    except ValueError:
        links = None
    if not check("the health readout counts the links that exist",
                 isinstance(links, int) and links >= 1,
                 f"status={status} links={links!r} (at least one link was just created)"):
        return None

    return STEPS
