"""Transport-layer behaviour (loopback + serial construction guards)."""

import pytest

from pydigi import LoopbackTransport, SerialTransport, SerialConfig
from pydigi.exceptions import TransportError


def test_loopback_write_records_bytes():
    with LoopbackTransport(b"") as link:
        link.write(b"\x05")
        assert link.written == b"\x05"


def test_loopback_replies_per_write():
    link = LoopbackTransport([b"AAA", b"BBB"])
    link.open()
    link.write(b"\x05")
    assert link.read(3) == b"AAA"
    link.write(b"\x05")
    assert link.read(3) == b"BBB"
    # exhausted -> silent scale
    link.write(b"\x05")
    assert link.read(3) == b""


def test_loopback_callable_responses():
    counter = {"n": 0}

    def responder():
        counter["n"] += 1
        return ("%03d" % counter["n"]).encode("ascii")

    link = LoopbackTransport(responder)
    link.open()
    link.write(b"\x05")
    assert link.read(3) == b"001"
    link.write(b"\x05")
    assert link.read(3) == b"002"


def test_loopback_read_is_chunked():
    link = LoopbackTransport(b"HELLO")
    link.open()
    link.write(b"?")
    assert link.read(2) == b"HE"
    assert link.read(2) == b"LL"
    assert link.read(2) == b"O"


def test_loopback_operations_require_open():
    link = LoopbackTransport(b"x")
    with pytest.raises(TransportError):
        link.write(b"x")


def test_serial_transport_requires_serial_config():
    with pytest.raises(TypeError):
        SerialTransport("/dev/ttyUSB0")  # must be a SerialConfig, not a str


def test_serial_transport_read_before_open_raises():
    link = SerialTransport(SerialConfig(port="/dev/nonexistent"))
    assert not link.is_open
    with pytest.raises(TransportError):
        link.read(1)


def test_serial_transport_open_bad_port_raises_transport_error():
    # A device that cannot exist on any platform -> wrapped as TransportError,
    # never a raw serial.SerialException leaking to the caller.
    link = SerialTransport(SerialConfig(port="/nonexistent/pydigi-test-port"))
    with pytest.raises(TransportError):
        link.open()
