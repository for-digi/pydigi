"""Helpers for building synthetic DIGI Type B frames in tests.

Keeping frame construction in one place means the byte-offset knowledge lives
next to the parser's knowledge, and a datasheet change touches one file.
"""

CR = 0x0D
LF = 0x0A

HEADER_NET = 0x30    # '0'
HEADER_TARE = 0x34   # '4'
HEADER_UNIT = 0x55   # 'U'
HEADER_TOTAL = 0x54  # 'T'

# Value fields as they appear on the wire (fixed widths, space-padded).
OVERFLOW_6 = "OF    "
UNDERFLOW_6 = "UF    "
BLANK_6 = "      "
BLANK_7 = "       "


def _field(value, length):
    data = value.encode("ascii")
    if len(data) != length:
        raise ValueError("field %r must be exactly %d bytes, got %d" % (value, length, len(data)))
    return data


def type_b_frame(
    net="03.456",
    tare="01.200",
    unit="01.500",
    total="005.184",
    status=0x42,
    condition=0x42,
    parity=None,
):
    """Build a Type B frame. Value args are exact-width wire strings.

    ``status`` bit 0 controls whether a parity byte belongs; pass ``parity`` to
    append one (and set the bit yourself if you want a well-formed frame).
    """
    frame = (
        bytes([status, condition, CR, HEADER_NET]) + _field(net, 6)
        + bytes([CR, HEADER_TARE]) + _field(tare, 6)
        + bytes([CR, HEADER_UNIT]) + _field(unit, 6)
        + bytes([CR, HEADER_TOTAL]) + _field(total, 7)
        + bytes([CR, LF])
    )
    if parity is not None:
        frame += bytes([parity])
    return frame
