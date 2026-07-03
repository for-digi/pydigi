"""pydigi — read weight, price and status from DIGI scales over RS-232.

Typical use::

    from pydigi import DigiDS781

    with DigiDS781.open("/dev/ttyUSB0") as scale:
        print(scale.read().weight_net_kg)

See ``DESIGN.md`` for the architecture and ``examples/`` for runnable scripts.
"""

from .version import __version__
from .exceptions import (
    PyDigiError,
    TransportError,
    ScaleTimeout,
    FrameError,
    ShortFrameError,
    HeaderError,
    FieldParseError,
    ParityError,
)
from .reading import (
    ScaleReading,
    StatusFlag,
    WeightConditionFlag,
    PriceBase,
)
from .config import SerialConfig
from .transport import Transport, SerialTransport, LoopbackTransport
from .protocol import Protocol, TypeBProtocol
from .scale import Scale, PollPolicy
from .watch import ChangeFilter, Field
from .models import ScaleModel, DigiDS781, get_model, available_models, register

__all__ = [
    "__version__",
    # errors
    "PyDigiError",
    "TransportError",
    "ScaleTimeout",
    "FrameError",
    "ShortFrameError",
    "HeaderError",
    "FieldParseError",
    "ParityError",
    # data model
    "ScaleReading",
    "StatusFlag",
    "WeightConditionFlag",
    "PriceBase",
    # config / transport / protocol
    "SerialConfig",
    "Transport",
    "SerialTransport",
    "LoopbackTransport",
    "Protocol",
    "TypeBProtocol",
    # client
    "Scale",
    "PollPolicy",
    "ChangeFilter",
    "Field",
    # models
    "ScaleModel",
    "DigiDS781",
    "get_model",
    "available_models",
    "register",
]
