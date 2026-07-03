#!/usr/bin/env python3
"""Record HIL frame dumps by walking the operator through timed instructions.

Reads the case matrix in tests/hil/cases.yaml, and for each selected case prints
each instruction with a countdown, captures the scale's real frames during the
``record`` windows, checks them against the case's expectations for immediate
pass/fail, and writes a dump to tests/hil/dumps/<case-id>.json.

Those dumps are then replayed, hardware-free, by tests/hil/test_replay_dumps.py.

Examples:
    # list the matrix
    python scripts/hil_record.py --list

    # rehearse the prompts with no scale connected (no capture, no dump)
    python scripts/hil_record.py --all --dry-run

    # record everything against a real scale
    python scripts/hil_record.py --port /dev/cu.usbserial-111420 --all

    # record specific cases
    python scripts/hil_record.py --port /dev/ttyUSB0 --case P02-ref-small --case P05-tare-container

Requires PyYAML:  pip install '.[hil]'
"""

import argparse
import logging
import os
import sys
import time

# Make pydigi and the HIL toolkit importable when run from a source checkout.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests", "hil"))

import hilkit  # noqa: E402
from pydigi import DigiDS781  # noqa: E402
from pydigi.exceptions import PyDigiError  # noqa: E402


def _record_window(scale, seconds, hz):
    """Poll the scale for `seconds`, capturing every frame (good or garbled)."""
    frames = []
    interval = 1.0 / hz
    start = time.time()
    while time.time() - start < seconds:
        stamp = round(time.time() - start, 3)
        try:
            reading = scale.read()
            frames.append({"t": stamp, "raw_hex": reading.raw_hex, "parsed": reading.as_dict()})
        except PyDigiError as error:
            frames.append({"t": stamp, "error": str(error)})
        sys.stdout.write("\r     recording ... %3d frames " % len(frames))
        sys.stdout.flush()
        time.sleep(interval)
    print()
    return frames


def _plan_line(step, index):
    if "record" in step:
        return "%d. RECORD (%ss): %s" % (index, step["record"], step["say"])
    return "%d. %s" % (index, step["say"])


def _run_case(case, scale, dry_run, dumps_dir, port):
    # -- intro: show WHAT is coming before anything happens (points 3, 4, 5) --
    print("\n" + "=" * 70)
    print("%s  —  %s  [%s]" % (case.id, case.title, case.polarity))
    prerequisites = case.all_prerequisites()
    if prerequisites:
        print("Prerequisites:")
        for item in prerequisites:
            print("  - " + item)
    print("Plan (%d steps):" % len(case.steps))
    for index, step in enumerate(case.steps, 1):
        print("  " + _plan_line(step, index))
    print("Dump -> %s" % os.path.join(dumps_dir, case.id + ".json"))
    print("=" * 70)

    # -- execute: instruction first, then wait for Enter (point 2) ----------
    hz = case.setting("record_hz") or 10
    total = len(case.steps)
    frames = []
    for index, step in enumerate(case.steps, 1):
        say = step["say"]
        if "record" in step:
            input("  Step %d/%d — RECORD (%ss): %s\n     [Enter] to START recording > "
                  % (index, total, step["record"], say))
            if dry_run:
                print("     (dry-run: no capture)")
            else:
                frames.extend(_record_window(scale, step["record"], hz))
        else:
            input("  Step %d/%d: %s\n     [Enter] when done > " % (index, total, say))

    if dry_run:
        print("  (dry-run: nothing captured, no dump written)")
        return

    path = hilkit.write_dump(case, frames, port=port, dumps_dir=dumps_dir)
    readings = hilkit.readings_from_frames(frames)
    print("  captured %d frames (%d parseable) -> %s"
          % (len(frames), len(readings), os.path.relpath(path, REPO_ROOT)))

    skip = hilkit.precondition_skip(case, readings)
    if skip:
        print("  RESULT: SKIP (%s)" % skip)
        return
    failures = hilkit.check(case, readings)
    if failures:
        print("  RESULT: FAIL")
        for failure in failures:
            print("    - " + failure)
    else:
        print("  RESULT: PASS")


def _select(catalog, args):
    if args.case:
        return [catalog.get(cid) for cid in args.case]
    cases = [c for c in catalog.cases if not c.synthetic]
    if args.tag:
        cases = [c for c in cases if args.tag in c.tags]
    return cases


def _print_run_intro(cases, port, dumps_dir):
    """Everything the operator needs to know before recording starts."""
    print("\nRecording %d case(s) from %s" % (len(cases), port))
    print("Dumps will be written to:\n  %s" % dumps_dir)

    gather, seen = [], set()
    for case in cases:
        for item in case.all_prerequisites():
            if item not in seen:
                seen.add(item)
                gather.append(item)
    if gather:
        print("\nBefore you begin, gather:")
        for item in gather:
            print("  - " + item)

    print("\nCases to record, in order:")
    for index, case in enumerate(cases, 1):
        flag = " [optional]" if case.optional else ""
        print("  %2d. %s — %s%s" % (index, case.id, case.title, flag))
    print("\nEach case shows its full plan first, then you confirm every step "
          "with Enter.\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", help="serial device of the scale")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--case", action="append", help="case id (repeatable)")
    parser.add_argument("--tag", help="only cases carrying this tag")
    parser.add_argument("--all", action="store_true", help="run all non-synthetic cases")
    parser.add_argument("--out", default=None,
                        help="directory for dumps (default: tests/hil/dumps/<model>)")
    parser.add_argument("--dry-run", action="store_true",
                        help="walk the prompts without a scale; capture nothing")
    parser.add_argument("--list", action="store_true", help="print the case matrix and exit")
    args = parser.parse_args(argv)

    # Keep pydigi's routine warnings (timeouts, negative-net) out of the
    # operator's console; the dump records them anyway.
    logging.getLogger("pydigi").setLevel(logging.ERROR)

    catalog = hilkit.load_catalog()
    dumps_dir = os.path.abspath(args.out) if args.out else hilkit.model_dumps_dir(catalog)

    if args.list:
        print("Reference weights: %s" % ", ".join(
            "%s=%.3fkg" % (k, v) for k, v in sorted(catalog.weights.items())))
        for case in catalog.cases:
            flags = []
            if case.optional:
                flags.append("optional")
            if case.requires_plu:
                flags.append("needs-plu")
            if case.synthetic:
                flags.append("synthetic")
            print("  %-20s %-8s %s%s"
                  % (case.id, case.polarity, case.title,
                     (" [%s]" % ",".join(flags)) if flags else ""))
        return 0

    if not (args.case or args.all or args.tag):
        parser.error("choose cases: --all, --case ID, or --tag TAG (or --list)")

    cases = _select(catalog, args)
    if not cases:
        print("No matching cases.")
        return 1

    if args.dry_run:
        _print_run_intro(cases, port="(dry-run, no scale)", dumps_dir=dumps_dir)
        for case in cases:
            _run_case(case, scale=None, dry_run=True, dumps_dir=dumps_dir, port="(dry-run)")
        return 0

    if not args.port:
        parser.error("--port is required unless --dry-run or --list")

    _print_run_intro(cases, port=args.port, dumps_dir=dumps_dir)
    with DigiDS781.open(args.port, baudrate=args.baud) as scale:
        for case in cases:
            choice = input("[Enter] record %s   [s] skip   [q] quit : " % case.id).strip().lower()
            if choice == "q":
                break
            if choice == "s":
                print("  skipped")
                continue
            _run_case(case, scale, dry_run=False, dumps_dir=dumps_dir, port=args.port)
    print("\nDone. Dumps are in %s\nReplay them with:" % dumps_dir)
    print("  .virtualenv/bin/python -m pytest tests/hil/test_replay_dumps.py -v")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
