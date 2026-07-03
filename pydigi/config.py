"""Serial-link configuration.

The defaults are the DIGI DS-781 factory settings (9600 8N1, no flow control).
Values are the literal constants pyserial accepts, so importing this module does
not require pyserial to be installed.
"""

from dataclasses import dataclass


# pyserial constant values, inlined so config stays import-light:
#   parity 'N' = none, bytesize 8, stopbits 1
PARITY_NONE = "N"
PARITY_EVEN = "E"
PARITY_ODD = "O"
EIGHT_BITS = 8
SEVEN_BITS = 7
STOP_BITS_ONE = 1
STOP_BITS_TWO = 2


@dataclass
class SerialConfig:
    """Everything needed to open an RS-232 link to a scale.

    :param port: OS device name, e.g. ``/dev/ttyUSB0`` or ``COM3``.
    :param baudrate: DS-781 supports 1200/2400/4800/9600/19200/38400.
    :param timeout: per-read timeout in seconds.
    """

    port: str
    baudrate: int = 9600
    bytesize: int = EIGHT_BITS
    parity: str = PARITY_NONE
    stopbits: float = STOP_BITS_ONE
    timeout: float = 1.0
    rtscts: bool = False  # RTS/CTS only when SPEC3.3 = 0; default is 3-wire
