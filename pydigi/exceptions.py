"""Exception hierarchy for pydigi.

Catch :class:`PyDigiError` to handle anything this library raises. The finer
grained classes let callers react specifically: retry on :class:`ScaleTimeout`,
or log-and-skip a garbled frame (:class:`FrameError`) inside a long-running
stream without tearing down the serial port.
"""


class PyDigiError(Exception):
    """Base class for every error raised by pydigi."""


class TransportError(PyDigiError):
    """The underlying transport (serial port, socket, ...) failed.

    Wraps lower-level errors such as :class:`serial.SerialException` so callers
    depend on pydigi's exceptions, not on pyserial's.
    """


class ScaleTimeout(TransportError):
    """The scale sent no (or too few) bytes before the timeout / retries ran out."""


class FrameError(PyDigiError):
    """A response arrived but could not be interpreted as a valid frame.

    Carries the offending bytes on ``raw`` (hex string) for diagnostics.
    """

    def __init__(self, message, raw=None):
        super(FrameError, self).__init__(message)
        self.raw = raw


class ShortFrameError(FrameError):
    """Fewer bytes were received than the frame layout requires."""


class HeaderError(FrameError):
    """A fixed header or terminator byte did not hold its expected value."""


class FieldParseError(FrameError):
    """A value field was not valid ASCII decimal and was not a known special value."""


class ParityError(FrameError):
    """The additional-parity byte did not match the computed value."""
