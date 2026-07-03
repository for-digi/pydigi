"""Frame parsing and framing edge cases for TypeBProtocol."""

import pytest

from pydigi import TypeBProtocol, PriceBase, LoopbackTransport
from pydigi.exceptions import ShortFrameError, HeaderError, FieldParseError, ScaleTimeout

from framelib import type_b_frame, OVERFLOW_6, UNDERFLOW_6, BLANK_6, BLANK_7


@pytest.fixture
def protocol():
    return TypeBProtocol()


def test_poll_request_is_enq(protocol):
    assert protocol.poll_request() == b"\x05"


def test_parse_datasheet_example(protocol):
    reading = protocol.parse(type_b_frame())
    assert reading.weight_net_kg == 3.456
    assert reading.weight_tare_kg == 1.200
    assert reading.weight_gross_kg == 4.656
    assert reading.unit_price == 1.500
    assert reading.total_price == 5.184
    assert reading.price_base is PriceBase.PER_KG
    assert reading.is_stable
    assert reading.is_net
    assert not reading.is_zero


def test_gross_is_net_plus_tare(protocol):
    reading = protocol.parse(type_b_frame(net="10.000", tare="02.500"))
    assert reading.weight_gross_kg == 12.5


@pytest.mark.parametrize("special", [OVERFLOW_6, UNDERFLOW_6, BLANK_6])
def test_weight_special_values_become_none(protocol, special):
    reading = protocol.parse(type_b_frame(net=special))
    assert reading.weight_net_kg is None
    # gross cannot be derived when an operand is missing
    assert reading.weight_gross_kg is None


def test_blank_prices_become_none(protocol):
    reading = protocol.parse(type_b_frame(unit=BLANK_6, total=BLANK_7))
    assert reading.unit_price is None
    assert reading.total_price is None


def test_price_base_decoding(protocol):
    # bits 3-4 of status: 0b01 << 3 = 0x08 -> $/100g, keep fixed-1 bit (0x40)
    reading = protocol.parse(type_b_frame(status=0x48))
    assert reading.price_base is PriceBase.PER_100G
    reading = protocol.parse(type_b_frame(status=0x50))  # 0b10 << 3
    assert reading.price_base is PriceBase.PER_LB
    reading = protocol.parse(type_b_frame(status=0x58))  # 0b11 << 3
    assert reading.price_base is PriceBase.PER_QUARTER_LB


def test_condition_flags_surface_as_booleans(protocol):
    # zero sign (bit0) + stable (bit1) + fixed (bit6) = 0x43
    reading = protocol.parse(type_b_frame(condition=0x43))
    assert reading.is_zero and reading.is_stable
    # overflow bit3
    reading = protocol.parse(type_b_frame(condition=0x48))
    assert reading.weight_overflow


def test_short_frame_rejected(protocol):
    with pytest.raises(ShortFrameError):
        protocol.parse(type_b_frame()[:20])


def test_wrong_header_rejected(protocol):
    frame = bytearray(type_b_frame())
    frame[11] = 0x39  # corrupt the tare header ('4' -> '9')
    with pytest.raises(HeaderError):
        protocol.parse(bytes(frame))


def test_missing_terminator_rejected(protocol):
    frame = bytearray(type_b_frame())
    frame[36] = 0x00  # LF terminator clobbered
    with pytest.raises(HeaderError):
        protocol.parse(bytes(frame))


def test_garbage_weight_field_rejected(protocol):
    with pytest.raises(FieldParseError):
        protocol.parse(type_b_frame(net="12.3XY"))


# --- read_frame: length is data-dependent on the parity bit ---------------

def _read(protocol, frame):
    with LoopbackTransport(frame) as link:
        link.write(protocol.poll_request())
        return protocol.read_frame(link)


def test_read_frame_without_parity_is_37_bytes(protocol):
    frame = type_b_frame(status=0x42)  # bit0 clear -> no parity byte
    raw = _read(protocol, frame)
    assert len(raw) == 37


def test_read_frame_with_parity_is_38_bytes(protocol):
    frame = type_b_frame(status=0x43, parity=0x1D)  # bit0 set -> parity follows
    raw = _read(protocol, frame)
    assert len(raw) == 38
    assert raw[37] == 0x1D


def test_read_frame_does_not_merge_two_frames(protocol):
    # Two frames back-to-back: one read_frame must return exactly the first.
    two = type_b_frame(net="01.000") + type_b_frame(net="02.000")
    with LoopbackTransport(two) as link:
        link.write(protocol.poll_request())
        first = protocol.read_frame(link)
        assert len(first) == 37
        assert protocol.parse(first).weight_net_kg == 1.0
        second = protocol.read_frame(link)
        assert protocol.parse(second).weight_net_kg == 2.0


def test_read_frame_timeout_when_silent(protocol):
    with LoopbackTransport(b"") as link:
        link.write(protocol.poll_request())
        with pytest.raises(ScaleTimeout):
            protocol.read_frame(link)


def test_read_frame_short_body_raises(protocol):
    with LoopbackTransport(b"\x42\x42\x0d") as link:
        link.write(protocol.poll_request())
        with pytest.raises(ShortFrameError):
            protocol.read_frame(link)
