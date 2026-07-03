<!-- Thanks for contributing! Keep this lean - delete sections that don't apply. -->

## What and why

<!-- What does this change, and what problem does it solve? Link any issue: "Closes #123". -->

## How it was tested

- [ ] `pytest` passes (`make test`)
- [ ] `pyflakes pydigi tests scripts` is clean
- [ ] Tested on real hardware <!-- which scale / USB-serial adapter, or "n/a" -->

<!-- For protocol/parsing/timing changes, a recorded HIL dump (scripts/hil_record.py)
     or a short `-v` log excerpt showing before/after behavior is very helpful. -->

## Checklist

- [ ] Logging only (no `print` in the library), comprehensible names
- [ ] New behavior has a test (or I've explained why it can't be unit-tested)
- [ ] Docs updated if user-facing (README / `--help` / DESIGN.md / TESTING.md)
- [ ] A new model/protocol/transport extends by subclassing - no existing code rewritten
- [ ] Commit messages are clear (the release changelog is generated from them)
