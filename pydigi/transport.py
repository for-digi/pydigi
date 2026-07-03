"""The transport layer: move bytes to and from the scale.

A :class:`Transport` knows nothing about DIGI frames — only how to open a link,
push bytes, and pull bytes back. That separation is what lets the whole library
be tested without hardware: :class:`LoopbackTransport` replays canned responses,
while :class:`SerialTransport` talks to a real RS-232 port through pyserial.

To support a new link type (a TCP<->serial bridge, USB HID, ...) implement this
interface; nothing above the transport needs to change.
"""

from abc import ABC, abstractmethod

from .config import SerialConfig
from .exceptions import TransportError, ScaleTimeout


class Transport(ABC):
    """Abstract byte pipe to a scale.

    Implementations are used as context managers::

        with SerialTransport(config) as link:
            link.write(b"\\x05")
            data = link.read(37)
    """

    @abstractmethod
    def open(self):
        """Open the link. Idempotent implementations are encouraged."""

    @abstractmethod
    def close(self):
        """Close the link and release the underlying resource."""

    @property
    @abstractmethod
    def is_open(self):
        """True while the link is usable."""

    @abstractmethod
    def write(self, data):
        """Send ``data`` (bytes) to the scale."""

    @abstractmethod
    def read(self, size):
        """Read up to ``size`` bytes; may return fewer on timeout."""

    @abstractmethod
    def reset_input(self):
        """Discard any bytes already buffered on the input side.

        Called before each poll so a stale/partial frame can't be mistaken for
        the reply to the ENQ we are about to send.
        """

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc_info):
        self.close()


class SerialTransport(Transport):
    """RS-232 transport backed by pyserial.

    pyserial is imported lazily so that importing pydigi (and running the
    hardware-free tests) does not require pyserial to be installed.
    """

    def __init__(self, config):
        if not isinstance(config, SerialConfig):
            raise TypeError("SerialTransport requires a SerialConfig")
        self._config = config
        self._serial = None

    def open(self):
        if self._serial is not None and self._serial.is_open:
            return
        try:
            import serial  # lazy: only needed for real hardware
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise TransportError(
                "pyserial is required for SerialTransport. Install it with "
                "'pip install pyserial'."
            ) from exc

        cfg = self._config
        try:
            self._serial = serial.Serial(
                port=cfg.port,
                baudrate=cfg.baudrate,
                bytesize=cfg.bytesize,
                parity=cfg.parity,
                stopbits=cfg.stopbits,
                timeout=cfg.timeout,
                rtscts=cfg.rtscts,
            )
        except Exception as exc:  # serial.SerialException and friends
            raise TransportError("Failed to open serial port %s: %s" % (cfg.port, exc)) from exc

    def close(self):
        if self._serial is not None and self._serial.is_open:
            self._serial.close()

    @property
    def is_open(self):
        return self._serial is not None and self._serial.is_open

    def _require_open(self):
        if not self.is_open:
            raise TransportError("Serial port is not open; call open() first")

    def write(self, data):
        self._require_open()
        try:
            self._serial.write(data)
        except Exception as exc:
            raise TransportError("Serial write failed: %s" % exc) from exc

    def read(self, size):
        self._require_open()
        try:
            return self._serial.read(size)
        except Exception as exc:
            raise TransportError("Serial read failed: %s" % exc) from exc

    def reset_input(self):
        self._require_open()
        try:
            self._serial.reset_input_buffer()
        except Exception as exc:
            raise TransportError("Failed to reset input buffer: %s" % exc) from exc


class LoopbackTransport(Transport):
    """In-memory transport for tests, demos, and offline development.

    Give it the bytes the scale *would* return. Each poll consumes the next
    scripted response; when responses run out it behaves like a silent scale
    (returns no bytes -> the protocol raises :class:`ScaleTimeout`).

    ``responses`` may be:
      * a single ``bytes`` object (returned once), or
      * an iterable of ``bytes`` (one per poll), or
      * a callable ``() -> bytes`` invoked on each read (for dynamic data).
    """

    def __init__(self, responses=b""):
        self._opened = False
        self._sent = bytearray()          # everything the client wrote
        self._buffer = bytearray()        # bytes waiting to be read
        self._callable = None
        self._queue = None

        if callable(responses):
            self._callable = responses
        elif isinstance(responses, (bytes, bytearray)):
            self._queue = [bytes(responses)]
        else:
            self._queue = [bytes(chunk) for chunk in responses]

    # -- introspection helpers for tests ----------------------------------
    @property
    def written(self):
        """All bytes the client has written so far (for assertions)."""
        return bytes(self._sent)

    def open(self):
        self._opened = True

    def close(self):
        self._opened = False

    @property
    def is_open(self):
        return self._opened

    def _require_open(self):
        if not self._opened:
            raise TransportError("Loopback transport is not open; call open() first")

    def write(self, data):
        self._require_open()
        self._sent.extend(data)
        # A write triggers the scale's reply: stage the next scripted response.
        if self._callable is not None:
            self._buffer.extend(self._callable())
        elif self._queue:
            self._buffer.extend(self._queue.pop(0))

    def read(self, size):
        self._require_open()
        chunk = bytes(self._buffer[:size])
        del self._buffer[:size]
        return chunk

    def reset_input(self):
        self._require_open()
        # Model a real UART: only already-arrived bytes are flushed. In the
        # loopback we stage replies on write(), so there is nothing buffered
        # here yet and this is a no-op, which matches hardware behaviour.
        del self._buffer[:]
