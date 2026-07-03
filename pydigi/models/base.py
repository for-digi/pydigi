"""Base class for concrete scale models.

A *model* binds a protocol variant to a device's serial defaults and a registry
name. Everything a model does (build a config, bind a transport, open a port) is
implemented here from a handful of class attributes, so **adding a model is data,
not code**::

    @register
    class DigiDS782(ScaleModel):
        name = "ds782"
        protocol_class = TypeBProtocol
        default_baudrate = 9600
        max_weight_kg = 15.0

No factory methods to re-implement, nothing to copy — that is the point.
"""

from ..config import SerialConfig
from ..scale import Scale
from ..transport import SerialTransport


class ScaleModel(object):
    """Metadata + factory methods shared by every concrete model."""

    #: Registry name, e.g. ``"ds781"``. Subclasses must set this.
    name = None
    #: The :class:`~pydigi.protocol.Protocol` subclass this model speaks.
    protocol_class = None
    #: Default serial baud rate for this device.
    default_baudrate = 9600
    #: Rated capacity in kg (drives a sanity warning), or ``None`` if unknown.
    max_weight_kg = None

    def __init__(self, *_args, **_kwargs):
        # Models are used through their classmethods; there is no instance state.
        raise TypeError(
            "%s is a model factory — use its classmethods (open/bind/config), "
            "not instances" % type(self).__name__
        )

    @classmethod
    def _require_defined(cls):
        if not cls.name or cls.protocol_class is None:
            raise NotImplementedError(
                "%s must set both 'name' and 'protocol_class'" % cls.__name__
            )

    @classmethod
    def config(cls, port, baudrate=None, **serial_kwargs):
        """Build a :class:`SerialConfig` with this model's defaults filled in."""
        return SerialConfig(
            port=port,
            baudrate=baudrate or cls.default_baudrate,
            **serial_kwargs
        )

    @classmethod
    def bind(cls, transport, policy=None):
        """Wrap an already-built transport in a configured :class:`Scale`.

        Use this with a :class:`~pydigi.transport.LoopbackTransport` in tests, or
        any custom transport. The returned scale is *not* opened.
        """
        cls._require_defined()
        return Scale(
            transport,
            cls.protocol_class(),
            policy=policy,
            max_weight_kg=cls.max_weight_kg,
        )

    @classmethod
    def open(cls, port, baudrate=None, policy=None, **serial_kwargs):
        """Open this model on a real serial ``port`` and return the ready scale.

        Works both as ``scale = Model.open(port)`` and as a context manager
        ``with Model.open(port) as scale:`` (re-opening is a no-op). Extra
        keyword args (parity, stopbits, timeout, rtscts) pass through to
        :class:`SerialConfig`.
        """
        config = cls.config(port, baudrate=baudrate, **serial_kwargs)
        scale = cls.bind(SerialTransport(config), policy=policy)
        return scale.open()
