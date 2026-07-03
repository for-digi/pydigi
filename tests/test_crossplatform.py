"""Cross-platform guarantees (roadmap #3).

pydigi must behave identically on Linux, macOS, and Windows. The parsing and
client layers touch no filesystem paths and no OS-specific APIs, so the real
risk areas are: port-name handling, byte/line-ending handling, and text
decoding. These tests pin that behaviour so a regression fails on any OS.
"""

import pytest

from pydigi import DigiDS781, LoopbackTransport, SerialConfig, TypeBProtocol

from framelib import type_b_frame


@pytest.mark.parametrize(
    "port",
    ["/dev/ttyUSB0", "/dev/cu.usbserial-1140", "COM1", "COM12"],
)
def test_port_names_are_opaque_strings(port):
    # We never parse or split the port name; any OS device string is accepted.
    cfg = SerialConfig(port=port)
    assert cfg.port == port


def test_parsing_is_independent_of_platform_newlines():
    # The frame uses explicit CR/LF bytes; parsing must not depend on the host's
    # os.linesep or any text-mode translation.
    protocol = TypeBProtocol()
    frame = type_b_frame(net="09.000")
    assert protocol.parse(frame).weight_net_kg == 9.0


def test_values_decoded_as_ascii_not_locale():
    # Numeric fields are ASCII; decoding must not depend on locale or a decimal
    # comma. "01.500" is always 1.5 regardless of LC_NUMERIC.
    protocol = TypeBProtocol()
    reading = protocol.parse(type_b_frame(unit="01.500"))
    assert reading.unit_price == 1.5


def test_reading_roundtrips_through_bytes_only():
    # End-to-end over the in-memory transport: no sockets, files, or devices,
    # so this exercises the same code path on every platform.
    with DigiDS781.bind(LoopbackTransport(type_b_frame(net="02.500"))) as scale:
        assert scale.read().weight_net_kg == 2.5
