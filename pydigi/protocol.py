"""The protocol layer: turn a transport's bytes into a :class:`ScaleReading`.

A :class:`Protocol` owns the wire format only. It knows how to ask the scale for
data (:meth:`poll_request`), how to pull exactly one frame off a transport
(:meth:`read_frame`), and how to decode that frame (:meth:`parse`). It has no
idea what a serial port is.

Only DIGI **Type B** is documented, so only :class:`TypeBProtocol` is
implemented. Type A / Type C would each be another subclass; nothing else in the
library would change.
"""

from abc import ABC, abstractmethod

from .exceptions import (
    ScaleTimeout,
    ShortFrameError,
    HeaderError,
    FieldParseError,
)
from .reading import (
    ScaleReading,
    StatusFlag,
    WeightConditionFlag,
    PriceBase,
)


def _read_exact(transport, count):
    """Read exactly ``count`` bytes, or fewer if the transport times out.

    Loops because a single ``read`` may return a partial buffer; stops early
    when a read yields nothing (the transport's timeout elapsed with no data).
    """
    buffer = bytearray()
    while len(buffer) < count:
        chunk = transport.read(count - len(buffer))
        if not chunk:
            break
        buffer.extend(chunk)
    return bytes(buffer)


class Protocol(ABC):
    """Wire-format contract shared by every DIGI protocol variant."""

    @abstractmethod
    def poll_request(self):
        """Bytes to send to trigger one response (e.g. ENQ)."""

    @abstractmethod
    def read_frame(self, transport):
        """Read exactly one raw frame from ``transport`` and return its bytes."""

    @abstractmethod
    def parse(self, raw):
        """Decode raw frame bytes into a :class:`ScaleReading`."""


# --- DIGI Type B (Standard command) ---------------------------------------

_ENQ = b"\x05"
_CR = 0x0D
_LF = 0x0A

# Frame layout (datasheet §20.4). Offsets are the start of each field.
_BODY_LEN = 37          # bytes 0..36; the optional parity byte is #37
_HEADER_NET = 0x30      # '0'
_HEADER_TARE = 0x34     # '4'
_HEADER_UNIT = 0x55     # 'U'
_HEADER_TOTAL = 0x54    # 'T'

_OVERFLOW = b"OF"
_UNDERFLOW = b"UF"


def _parse_weight_field(raw):
    """Parse a 6-byte weight field. ``OF``/``UF``/blank -> ``None``."""
    stripped = raw.strip()
    if stripped in (_OVERFLOW, _UNDERFLOW, b""):
        return None
    try:
        return float(stripped.decode("ascii"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise FieldParseError(
            "Cannot parse weight field %r: %s" % (raw, exc), raw=raw.hex()
        )


def _parse_price_field(raw):
    """Parse a price field. Blank (no PLU / overflow) -> ``None``."""
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return float(stripped.decode("ascii"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise FieldParseError(
            "Cannot parse price field %r: %s" % (raw, exc), raw=raw.hex()
        )


class TypeBProtocol(Protocol):
    """DIGI Type B: send ENQ, receive a 37/38-byte command-response frame."""

    def poll_request(self):
        return _ENQ

    def read_frame(self, transport):
        """Read one frame: the 37-byte body plus the parity byte if present.

        The frame length is data-dependent (status-flag bit 0 says whether a
        parity byte follows), so we read the body first, inspect that bit, and
        read exactly one more byte only when needed. No fixed over-read that
        could merge two frames, no under-read that could truncate one.
        """
        body = _read_exact(transport, _BODY_LEN)
        if not body:
            raise ScaleTimeout("No response from scale")
        if len(body) < _BODY_LEN:
            raise ShortFrameError(
                "Frame too short: got %d of %d body bytes" % (len(body), _BODY_LEN),
                raw=body.hex(),
            )
        if body[0] & StatusFlag.ADDITIONAL_PARITY:
            parity = _read_exact(transport, 1)
            if len(parity) < 1:
                raise ShortFrameError(
                    "Additional-parity byte announced but missing", raw=body.hex()
                )
            return body + parity
        return body

    def parse(self, raw):
        if len(raw) < _BODY_LEN:
            raise ShortFrameError(
                "Frame too short: %d bytes, need >= %d" % (len(raw), _BODY_LEN),
                raw=raw.hex(),
            )

        status_flag = StatusFlag(raw[0])
        weight_condition_flag = WeightConditionFlag(raw[1])

        # Validate the fixed structural bytes so a misframed read is caught
        # here (with a clear message) instead of producing garbage numbers.
        self._require(raw, 2, _CR, "CR after condition flag")
        self._require(raw, 3, _HEADER_NET, "net-weight header '0'")
        self._require(raw, 10, _CR, "CR after net weight")
        self._require(raw, 11, _HEADER_TARE, "tare-weight header '4'")
        self._require(raw, 18, _CR, "CR after tare weight")
        self._require(raw, 19, _HEADER_UNIT, "unit-price header 'U'")
        self._require(raw, 26, _CR, "CR after unit price")
        self._require(raw, 27, _HEADER_TOTAL, "total-price header 'T'")
        self._require(raw, 35, _CR, "CR after total price")
        self._require(raw, 36, _LF, "LF frame terminator")

        weight_net = _parse_weight_field(raw[4:10])
        weight_tare = _parse_weight_field(raw[12:18])
        unit_price = _parse_price_field(raw[20:26])
        total_price = _parse_price_field(raw[28:35])

        # Gross is derived by ScaleReading itself (net + tare), so we don't pass
        # it here — that keeps a single source of truth for the relationship.
        price_base_bits = (int(status_flag) >> 3) & 0b11

        return ScaleReading(
            status_flag=status_flag,
            weight_condition_flag=weight_condition_flag,
            weight_net_kg=weight_net,
            weight_tare_kg=weight_tare,
            unit_price=unit_price,
            total_price=total_price,
            price_base=PriceBase.from_bits(price_base_bits),
            raw_hex=raw.hex(),
        )

    @staticmethod
    def _require(raw, index, expected, what):
        if raw[index] != expected:
            raise HeaderError(
                "Expected %s (0x%02x) at byte %d, got 0x%02x"
                % (what, expected, index, raw[index]),
                raw=raw.hex(),
            )
