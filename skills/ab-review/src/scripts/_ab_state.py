#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ab-review --split mode: atomic state manager for two-terminal A/B ping-pong.

Single source of truth: .ab-review/state.json. Two terminals poll it via /loop.
`turn` (b|a|done) is the mutex — only the matching role acts per wake-up.

This script is the ONLY thing that should write state.json, so the atomicity
(flock + os.replace) lives in one place rather than being re-handled by the LLM
each wake-up. The skill calls this script via Bash; it never hand-writes state.

Subcommands:
  init   <target> [--range R] [--max-rounds N]   create state.json (turn=b,round=1)
  show                                      print current state (json, fail if absent)
  claim <role>                              atomic read; if turn==role and verdict is null
                                            print {"act": true, ...state} and exit 0;
                                            else print {"act": false, "turn":..., "round":...}
                                            and exit 0 (idle — caller fast-exits)
  handoff <role> [--round N] [--verdict V]  after finishing a step, hand off:
                                            role=b → set turn=a (round unchanged)
                                            role=a → set turn=b, round=round+1
                                            --verdict 通过|遗留 → turn=done
  finish <verdict>                          set turn=done, verdict=V (B终审通过)
  reset                                     delete state.json + lock (manual abort)

All writes are atomic: flock on state.json.lock → write tmp → os.replace.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# ---- cross-platform file locking ----
# fcntl.flock (Unix) and msvcrt.locking (Windows) provide equivalent
# exclusive-file-lock semantics. We expose a uniform pair of helpers
# that work on raw file descriptors so the rest of _with_lock stays clean.

if sys.platform == "win32":
    import msvcrt

    def _lock_fd(fd: int) -> None:
        """Acquire exclusive byte-range lock (blocking)."""
        # msvcrt.locking locks 1 byte at the current seek position;
        # the file must be open for both reading and writing.
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)

    def _unlock_fd(fd: int) -> None:
        """Release byte-range lock."""
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def _lock_fd(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock_fd(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)

STATE = Path(".ab-review/state.json")
LOCK = Path(".ab-review/state.json.lock")
VALID_VERDICTS = {"通过", "遗留"}


def _ensure_dir():
    STATE.parent.mkdir(parents=True, exist_ok=True)


def _read_locked():
    """Read state while holding the lock (caller already holds flock)."""
    if not STATE.exists():
        return None
    return json.loads(STATE.read_text(encoding="utf-8"))


def _write_locked(state: dict):
    """Atomic write while holding lock: tmp file → os.replace."""
    _ensure_dir()
    fd, tmp = tempfile.mkstemp(prefix=".state-", dir=str(STATE.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(STATE))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _with_lock(fn):
    """Hold exclusive lock on LOCK for the whole read-modify-write.

    Uses ``os.open`` (not ``open``) so the file descriptor is available in
    a mode that supports byte-range locking on Windows (``msvcrt.locking``)
    as well as advisory ``flock`` on Unix.
    """
    _ensure_dir()
    fd = os.open(str(LOCK), os.O_RDWR | os.O_CREAT)
    try:
        _lock_fd(fd)
        try:
            return fn()
        finally:
            _unlock_fd(fd)
    finally:
        os.close(fd)


# ---- subcommands ----

def _json_error(msg):
    """Uniform JSON error to stdout + exit 1. Keeps stdout always-valid JSON."""
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(1)


def cmd_init(args):
    if args.max_rounds < 1:
        _json_error(f"max-rounds must be >= 1 (got {args.max_rounds})")
    created = []

    def do():
        existing = _read_locked()
        if existing is not None:
            return existing, False  # already exists, don't clobber
        state = {
            "target": args.target,
            "mode": "split",
            "round": 1,
            "turn": "b",
            "verdict": None,
            "max_rounds": args.max_rounds,
            "range": args.range,
            "object_type": args.object_type,
            "updated_at": _now(),
        }
        _write_locked(state)
        return state, True

    state, did_create = _with_lock(do)
    print(json.dumps({"state": state, "created": did_create}, ensure_ascii=False))
    if not did_create:
        print("NOTE: state.json already existed, left unchanged.", file=sys.stderr)


def cmd_show(args):
    state = _with_lock(_read_locked)
    if state is None:
        print(json.dumps({"error": "no state — run init first"}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(state, ensure_ascii=False, indent=2))


def cmd_claim(args):
    """Role asks: is it my turn? Atomic check under lock. No state mutation."""
    def do():
        state = _read_locked()
        if state is None:
            return {"act": False, "error": "no state — run init first"}
        # stale_seconds: how long since last turn advance. >1800 (30min) with
        # turn unchanged suggests the peer terminal stalled. LLM checks this
        # field instead of hand-computing updated_at deltas.
        updated = state.get("updated_at")
        stale = (int(time.time()) - updated) if isinstance(updated, int) else None
        if state.get("verdict") is not None:
            return {"act": False, "done": True, "verdict": state["verdict"],
                    "turn": state["turn"], "round": state["round"],
                    "stale_seconds": stale}
        if state["turn"] == args.role:
            return {"act": True, "stale_seconds": stale, **state}
        return {"act": False, "waiting": True, "turn": state["turn"],
                "round": state["round"], "stale_seconds": stale}
    print(json.dumps(_with_lock(do), ensure_ascii=False))


def cmd_handoff(args):
    """After a role finishes its step, advance turn under lock."""
    if args.verdict is not None and args.verdict not in VALID_VERDICTS:
        _json_error(f"verdict must be one of {sorted(VALID_VERDICTS)}")

    def do():
        state = _read_locked()
        if state is None:
            _json_error("no state — run init first")
        if state.get("verdict") is not None:
            return state  # already done, nothing to do
        if state["turn"] != args.role:
            _json_error(
                f"not {args.role}'s turn (turn={state['turn']}) — "
                f"another terminal may have raced; re-check state"
            )
        if args.verdict is not None:
            state["verdict"] = args.verdict
            state["turn"] = "done"
        elif args.role == "b":
            state["turn"] = "a"  # round unchanged — A modifies this round
        elif args.role == "a":
            new_round = state["round"] + 1
            if new_round > state["max_rounds"]:
                state["verdict"] = "遗留"
                state["turn"] = "done"
            else:
                state["turn"] = "b"
                state["round"] = new_round
        state["updated_at"] = _now()
        _write_locked(state)
        return state
    print(json.dumps(_with_lock(do), ensure_ascii=False))


def cmd_finish(args):
    """B declares terminal verdict (通过). Sets turn=done under lock."""
    if args.verdict not in VALID_VERDICTS:
        _json_error(f"verdict must be one of {sorted(VALID_VERDICTS)}")

    def do():
        state = _read_locked()
        if state is None:
            _json_error("no state — run init first")
        state["verdict"] = args.verdict
        state["turn"] = "done"
        state["updated_at"] = _now()
        _write_locked(state)
        return state
    print(json.dumps(_with_lock(do), ensure_ascii=False))


def cmd_reset(_args):
    def do():
        for p in (STATE, LOCK):
            if p.exists():
                p.unlink()
        return {"reset": True}
    print(json.dumps(_with_lock(do), ensure_ascii=False))


VALID_OBJECT_TYPES = {"doc", "rtl"}


def cmd_set_type(args):
    """Correct a misjudged object_type (e.g. .sv file that's actually a testbench).
    A role that detects the mismatch raises it as B-0; A calls this to fix state."""
    if args.object_type not in VALID_OBJECT_TYPES:
        _json_error(f"object_type must be one of {sorted(VALID_OBJECT_TYPES)}")

    def do():
        state = _read_locked()
        if state is None:
            _json_error("no state — run init first")
        state["object_type"] = args.object_type
        state["updated_at"] = _now()
        _write_locked(state)
        return state
    print(json.dumps(_with_lock(do), ensure_ascii=False))


def _now() -> int:
    # NOTE: this runs at runtime (not inside a workflow script), so time is fine.
    return int(time.time())


def main():
    ap = argparse.ArgumentParser(prog="_ab_state.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="create state.json (turn=b, round=1)")
    p.add_argument("target")
    p.add_argument("--range", default=None)
    p.add_argument("--max-rounds", type=int, default=3)
    p.add_argument("--object-type", default=None, choices=sorted(VALID_OBJECT_TYPES),
                   help="doc|rtl — auto-inferred by SKILL.md side from target ext; "
                        "pass explicitly to override")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("show", help="print current state")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("claim", help="ask if it's my turn (atomic, no mutation)")
    p.add_argument("role", choices=["a", "b"])
    p.set_defaults(func=cmd_claim)

    p = sub.add_parser("handoff", help="advance turn after finishing a step")
    p.add_argument("role", choices=["a", "b"])
    p.add_argument("--verdict", default=None, help="通过|遗留 — set to terminate")
    p.set_defaults(func=cmd_handoff)

    p = sub.add_parser("finish", help="B declares terminal verdict")
    p.add_argument("verdict", choices=sorted(VALID_VERDICTS))
    p.set_defaults(func=cmd_finish)

    p = sub.add_parser("reset", help="delete state + lock (manual abort)")
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser("set-type", help="correct a misjudged object_type (B-0 -> A fix)")
    p.add_argument("object_type", choices=sorted(VALID_OBJECT_TYPES))
    p.set_defaults(func=cmd_set_type)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()