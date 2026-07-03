"""Replay recorded HIL dumps through the parser — a hardware-free regression test.

Every dump under tests/hil/dumps/ is re-parsed with the *current* parser and
checked against its case's expectations in cases.yaml. This runs in the normal
suite (no scale needed): it turns one-off hardware recordings into a permanent
corpus, so a future change that breaks real-frame decoding fails here.

Cases without a recorded dump are simply not parametrized (nothing to replay
yet). Needs PyYAML; skipped if it is not installed.
"""

import os

import pytest

pytest.importorskip("yaml")  # HIL tooling dep; skip the module if absent

import hilkit  # noqa: E402  (tests/hil is on sys.path)

_CATALOG = hilkit.load_catalog()
_DUMPS_DIR = hilkit.model_dumps_dir(_CATALOG)
_CASES_WITH_DUMPS = [
    c for c in _CATALOG.cases if os.path.exists(hilkit.dump_path(c.id, _DUMPS_DIR))
]


@pytest.mark.skipif(
    not _CASES_WITH_DUMPS,
    reason="no recorded dumps yet — record some with scripts/hil_record.py",
)
@pytest.mark.parametrize("case", _CASES_WITH_DUMPS, ids=[c.id for c in _CASES_WITH_DUMPS])
def test_recorded_dump_matches_expectations(case):
    dump = hilkit.read_dump(hilkit.dump_path(case.id, _DUMPS_DIR))
    readings = hilkit.readings_from_dump(dump)

    skip = hilkit.precondition_skip(case, readings)
    if skip:
        pytest.skip(skip)

    failures = hilkit.check(case, readings)
    assert not failures, "%s expectations not met:\n  - %s" % (
        case.id, "\n  - ".join(failures)
    )
