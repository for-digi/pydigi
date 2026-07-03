"""Scale client: retries, single read, continuous stream, change-watch."""

import pytest

from pydigi import DigiDS781, LoopbackTransport, PollPolicy, ChangeFilter
from pydigi.exceptions import ScaleTimeout, TransportError

from framelib import type_b_frame

# No sleeping in tests.
FAST = PollPolicy(retries=3, retry_delay=0.0, poll_delay=0.0)


def scale_over(responses, policy=FAST):
    return DigiDS781.bind(LoopbackTransport(responses), policy=policy)


def test_read_returns_reading():
    with scale_over(type_b_frame(net="05.000")) as scale:
        assert scale.read().weight_net_kg == 5.0


def test_read_sends_enq():
    link = LoopbackTransport(type_b_frame())
    with DigiDS781.bind(link, policy=FAST) as scale:
        scale.read()
    assert link.written == b"\x05"


def test_read_retries_after_timeout():
    frame = type_b_frame(net="05.000")
    with scale_over([b"", frame]) as scale:  # first poll silent, second good
        assert scale.read().weight_net_kg == 5.0


def test_read_gives_up_after_retries():
    with scale_over([b"", b"", b""]) as scale:
        with pytest.raises(ScaleTimeout):
            scale.read()


def test_read_before_open_raises():
    scale = scale_over(type_b_frame())
    with pytest.raises(TransportError):
        scale.read()  # never opened


def test_stream_count_limits_iterations():
    with scale_over(lambda: type_b_frame(net="05.000")) as scale:
        readings = list(scale.stream(interval=0, count=3))
    assert len(readings) == 3
    assert all(r.weight_net_kg == 5.0 for r in readings)


def test_watch_reports_only_changes():
    weights = iter(["01.000", "01.000", "02.000", "02.000", "03.000"])

    def responder():
        try:
            return type_b_frame(net=next(weights))
        except StopIteration:
            return type_b_frame(net="03.000")

    with scale_over(responder) as scale:
        reported = list(scale.watch(interval=0, count=3))
    assert [r.weight_net_kg for r in reported] == [1.0, 2.0, 3.0]


def test_watch_stable_only_skips_unstable():
    # unstable frame (condition bit1 clear) then a stable one at same weight
    frames = iter([
        type_b_frame(net="02.000", condition=0x40),  # unstable
        type_b_frame(net="02.000", condition=0x42),  # stable
    ])

    def responder():
        try:
            return next(frames)
        except StopIteration:
            return type_b_frame(net="02.000", condition=0x42)

    with scale_over(responder) as scale:
        reported = list(scale.watch(
            interval=0, change_filter=ChangeFilter.weight(stable_only=True), count=1
        ))
    assert len(reported) == 1
    assert reported[0].is_stable


def test_stream_ignore_errors_survives_timeouts():
    frame = type_b_frame(net="07.000")
    seq = iter([b"", frame, b"", frame])

    def responder():
        try:
            return next(seq)
        except StopIteration:
            return frame

    policy = PollPolicy(retries=1, retry_delay=0.0, poll_delay=0.0)
    errors = []
    with scale_over(responder, policy=policy) as scale:
        readings = list(
            scale.stream(interval=0, count=2, ignore_errors=True, on_error=errors.append)
        )
    assert len(readings) == 2
    assert len(errors) == 2  # two silent polls were reported, not raised
