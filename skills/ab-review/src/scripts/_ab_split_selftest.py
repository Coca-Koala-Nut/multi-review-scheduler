#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end self-test for ab-review --split state machine.

Drives _ab_state.py through a full happy path:
  init(b) → claim(b)=act → handoff(b) → claim(a)=act → handoff(a) [round2]
  → claim(b)=act → finish(通过) → claim(b)=done → claim(a)=done
And an edge case: max_rounds exhaustion (max=1) → handoff(a) sets 遗留/done.
Verifies mutex: claiming the wrong role returns act=False.
Run from a scratch dir; cleans up .ab-review/ afterwards.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path.home() / ".claude/skills/ab-review/scripts/_ab_state.py"


def run(*args):
    # check=False: we inspect returncode manually so expected-failure cases
    # (e.g. handoff on wrong turn) don't raise CalledProcessError.
    r = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, check=False,
    )
    if r.returncode != 0:
        print(f"FAIL: {' '.join(args)}\n  rc={r.returncode}\n  stderr={r.stderr}")
        sys.exit(1)
    return r


def jout(r):
    return json.loads(r.stdout)


def assert_eq(actual, expected, msg):
    if actual != expected:
        print(f"FAIL {msg}: expected {expected!r}, got {actual!r}")
        sys.exit(1)
    print(f"  ok  {msg}: {actual!r}")


def main():
    if not SCRIPT.exists():
        print(f"FAIL: script not found at {SCRIPT}")
        sys.exit(1)

    tmp = Path(tempfile.mkdtemp(prefix="ab-split-test-"))
    print(f"scratch dir: {tmp}")
    orig = Path.cwd()
    import os
    os.chdir(tmp)
    try:
        run("init", "design-note.md", "--max-rounds", "3", "--object-type", "rtl")
        s = jout(run("show"))
        assert_eq(s["turn"], "b", "init turn")
        assert_eq(s["round"], 1, "init round")
        assert_eq(s["verdict"], None, "init verdict")
        assert_eq(s.get("object_type"), "rtl", "object_type persisted")

        # --- B round 1 ---
        c = jout(run("claim", "b"))
        assert_eq(c["act"], True, "B1 claim act")
        # A should NOT be able to claim
        c = jout(run("claim", "a"))
        assert_eq(c["act"], False, "A cannot claim during B1")
        run("handoff", "b")
        s = jout(run("show"))
        assert_eq(s["turn"], "a", "after B1 handoff turn")
        assert_eq(s["round"], 1, "round unchanged after B handoff")

        # --- A round 1 ---
        c = jout(run("claim", "a"))
        assert_eq(c["act"], True, "A1 claim act")
        run("handoff", "a")
        s = jout(run("show"))
        assert_eq(s["turn"], "b", "after A1 handoff turn")
        assert_eq(s["round"], 2, "round incremented after A handoff")

        # --- B round 2: 终审通过 ---
        c = jout(run("claim", "b"))
        assert_eq(c["act"], True, "B2 claim act")
        run("finish", "通过")
        s = jout(run("show"))
        assert_eq(s["turn"], "done", "after finish turn")
        assert_eq(s["verdict"], "通过", "after finish verdict")

        # --- both terminals see done ---
        c = jout(run("claim", "b"))
        assert_eq(c.get("done"), True, "B sees done")
        assert_eq(c.get("act"), False, "B done not act")
        c = jout(run("claim", "a"))
        assert_eq(c.get("done"), True, "A sees done")

        # handoff after done is a no-op (state already done)
        run("handoff", "b")  # should not error, state stays done
        s = jout(run("show"))
        assert_eq(s["turn"], "done", "handoff after done is no-op")

        # --- edge: max_rounds exhaustion ---
        run("reset")
        run("init", "design-note.md", "--max-rounds", "1")
        run("handoff", "b")              # B1 → turn=a
        c = jout(run("claim", "a"))
        assert_eq(c["act"], True, "A1 claim (max=1)")
        run("handoff", "a")              # round would be 2 > max(1) → 遗留
        s = jout(run("show"))
        assert_eq(s["turn"], "done", "max-rounds exhaustion turn")
        assert_eq(s["verdict"], "遗留", "max-rounds exhaustion verdict")

        # --- init idempotency: existing state not clobbered ---
        r = run("init", "other.md", "--max-rounds", "9")
        out = jout(r)
        assert_eq(out["created"], False, "init does not clobber existing")
        s = jout(run("show"))
        assert_eq(s["target"], "design-note.md", "target preserved on re-init")

        # --- set-type: correct a misjudged object_type (B-0 -> A fix) ---
        # (state here was rebuilt by the max-rounds init without --object-type, so
        # object_type is None — set-type must still be able to set it.)
        run("set-type", "doc")
        s = jout(run("show"))
        assert_eq(s.get("object_type"), "doc", "set-type corrected to doc")
        run("set-type", "rtl")
        s = jout(run("show"))
        assert_eq(s.get("object_type"), "rtl", "set-type corrected to rtl")

        run("reset")
        print("\nALL PASS — state machine verified: b→a→b→done, max-rounds, idempotent init, mutex, object_type, set-type")
    finally:
        os.chdir(orig)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()