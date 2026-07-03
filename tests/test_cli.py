"""CLI behaviour, driven through a loopback transport (no hardware)."""

import json

import pydigi.cli as cli
from pydigi import DigiDS781, LoopbackTransport, PollPolicy

from framelib import type_b_frame

FAST = PollPolicy(retries=1, retry_delay=0.0, poll_delay=0.0)


def patch_scale(monkeypatch, responses):
    """Make cli._open_scale return a loopback-backed scale regardless of args."""
    def fake_open(args):
        return DigiDS781.bind(LoopbackTransport(responses), policy=FAST)
    monkeypatch.setattr(cli, "_open_scale", fake_open)


def test_list_models(capsys):
    assert cli.main(["list-models"]) == 0
    assert "ds781" in capsys.readouterr().out


def test_no_command_is_usage_error(capsys):
    assert cli.main([]) == 2
    assert "No command" in capsys.readouterr().err


def test_read_requires_port(capsys):
    assert cli.main(["read"]) == 2
    assert "--port is required" in capsys.readouterr().err


def test_read_prints_reading(monkeypatch, capsys):
    patch_scale(monkeypatch, type_b_frame(net="04.000"))
    assert cli.main(["--port", "loopback", "read"]) == 0
    assert "4.000" in capsys.readouterr().out


def test_read_json(monkeypatch, capsys):
    patch_scale(monkeypatch, type_b_frame(net="04.000"))
    assert cli.main(["--port", "loopback", "--json", "read"]) == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["weight_net_kg"] == 4.0
    assert payload["price_base"] == "$/kg"


def test_stream_count(monkeypatch, capsys):
    patch_scale(monkeypatch, lambda: type_b_frame(net="04.000"))
    assert cli.main(["--port", "loopback", "stream", "--interval", "0", "--count", "3"]) == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 3


def test_watch_reports_changes(monkeypatch, capsys):
    weights = iter(["01.000", "01.000", "05.000"])

    def responder():
        try:
            return type_b_frame(net=next(weights))
        except StopIteration:
            return type_b_frame(net="05.000")

    patch_scale(monkeypatch, responder)
    rc = cli.main(["--port", "loopback", "watch", "--interval", "0", "--count", "2"])
    assert rc == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 2  # 1.0 then 5.0, the repeat is filtered


def test_watch_all_fields_reports_flag_flip(monkeypatch, capsys):
    # Same weight throughout; only the zero-sign flag flips. --all-fields sees it.
    conds = iter([0x42, 0x43, 0x42, 0x43])

    def responder():
        try:
            cond = next(conds)
        except StopIteration:
            cond = 0x42
        return type_b_frame(net="00.000", condition=cond)

    patch_scale(monkeypatch, responder)
    rc = cli.main(["--port", "loopback", "watch", "--all-fields",
                   "--interval", "0", "--count", "2"])
    assert rc == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 2


def test_watch_field_tare(monkeypatch, capsys):
    # Net weight is constant; only tare changes. --field tare tracks it.
    tares = iter(["00.000", "00.000", "00.500"])

    def responder():
        try:
            tare = next(tares)
        except StopIteration:
            tare = "00.500"
        return type_b_frame(net="01.000", tare=tare)

    patch_scale(monkeypatch, responder)
    rc = cli.main(["--port", "loopback", "watch", "--field", "tare",
                   "--interval", "0", "--count", "2"])
    assert rc == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 2  # first reading + the tare change


def test_error_exit_code(monkeypatch, capsys):
    patch_scale(monkeypatch, b"")  # silent scale -> ScaleTimeout
    rc = cli.main(["--port", "loopback", "read"])
    assert rc == 1
    assert "Error:" in capsys.readouterr().err


def test_unknown_model_is_a_clean_error(capsys):
    # No monkeypatch: exercises the real registry lookup -> friendly exit, not a
    # traceback.
    rc = cli.main(["--model", "bogus", "--port", "loopback", "read"])
    assert rc == 2
    assert "Unknown scale model" in capsys.readouterr().err


def test_forever_survives_outage_and_reconnects(monkeypatch, capsys):
    # Two silent polls (device down), then two good frames (device back).
    frame_a = type_b_frame(net="01.000")
    frame_b = type_b_frame(net="02.000")
    seq = iter([b"", b"", frame_a, frame_b])

    def responder():
        try:
            return next(seq)
        except StopIteration:
            return frame_b

    patch_scale(monkeypatch, responder)
    rc = cli.main(["--port", "loopback", "watch", "--forever",
                   "--interval", "0", "--count", "2"])
    assert rc == 0
    out = capsys.readouterr()
    readings = [ln for ln in out.out.splitlines() if ln.strip()]
    assert len(readings) == 2                       # kept going, emitted both
    assert out.err.lower().count("unresponsive") == 1   # noted once, not per poll
    assert "reconnected" in out.err.lower()


def test_outage_notifier_is_edge_triggered(capsys):
    notifier = cli._OutageNotifier(retries=5)
    notifier.on_error(Exception("x"))
    notifier.on_error(Exception("x"))   # still down -> no second message
    notifier.saw_reading()              # back up -> one 'reconnected'
    notifier.saw_reading()              # already up -> no message
    err = capsys.readouterr().err
    assert err.count("unresponsive") == 1
    assert err.count("reconnected") == 1
