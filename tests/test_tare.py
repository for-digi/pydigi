"""Tare handling and net-mode semantics.

Tare is where a subtle sign/offset bug would hide, so it gets its own module:
parsing the tare field, deriving gross = net + tare, the NET (tare-active) flag,
and the negative-net condition.
"""

import pytest

from pydigi import TypeBProtocol
from framelib import type_b_frame, BLANK_6


@pytest.fixture
def protocol():
    return TypeBProtocol()


def test_tare_value_parsed(protocol):
    assert protocol.parse(type_b_frame(tare="02.500")).weight_tare_kg == 2.5


def test_gross_is_net_plus_tare(protocol):
    reading = protocol.parse(type_b_frame(net="03.000", tare="01.250"))
    assert reading.weight_gross_kg == 4.25


def test_zero_tare_leaves_gross_equal_net(protocol):
    reading = protocol.parse(type_b_frame(net="03.000", tare="00.000"))
    assert reading.weight_tare_kg == 0.0
    assert reading.weight_gross_kg == 3.0


def test_net_mode_flag_set(protocol):
    # Status bit 1 (NET) set -> tare subtraction is active.
    reading = protocol.parse(type_b_frame(status=0x42))  # 0x40 fixed + 0x02 NET
    assert reading.is_net is True


def test_net_mode_flag_clear(protocol):
    reading = protocol.parse(type_b_frame(status=0x40))  # fixed only, no NET
    assert reading.is_net is False


def test_negative_net_flag_surfaced(protocol):
    # Condition bit 2 (NEGATIVE_NET): tare exceeds gross.
    reading = protocol.parse(type_b_frame(condition=0x46))  # fixed + negative + stable
    assert reading.is_negative is True


def test_negative_net_value_parsed(protocol):
    # If the scale signs the net field directly, we parse the negative value.
    reading = protocol.parse(type_b_frame(net="-0.500", condition=0x46))
    assert reading.weight_net_kg == -0.5


def test_blank_tare_is_none_and_blocks_gross(protocol):
    reading = protocol.parse(type_b_frame(tare=BLANK_6))
    assert reading.weight_tare_kg is None
    assert reading.weight_gross_kg is None  # can't derive gross without tare
