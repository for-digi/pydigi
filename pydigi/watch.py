"""Change detection for the "data change watch" use case.

A :class:`ChangeFilter` decides whether one reading counts as a *change* versus
the previous one. You tick the fields you care about — weight only, weight plus
tare, prices, anything — and the filter reports a change when any ticked field
moves. Weight fields compare with a tolerance; everything else compares exactly.

Kept free of I/O so the "did it change?" decision is unit-testable on its own.
:class:`~pydigi.scale.Scale` uses it to drive
:meth:`~pydigi.scale.Scale.watch`.
"""


class Field(object):
    """Names of the reading fields a :class:`ChangeFilter` can watch.

    The values are exactly the :class:`~pydigi.reading.ScaleReading` attribute
    names, so the filter reads them with ``getattr``. Use these constants
    (``Field.NET``) rather than raw strings to catch typos.
    """

    NET = "weight_net_kg"
    TARE = "weight_tare_kg"
    GROSS = "weight_gross_kg"
    UNIT_PRICE = "unit_price"
    TOTAL_PRICE = "total_price"
    PRICE_BASE = "price_base"
    STABLE = "is_stable"
    ZERO = "is_zero"
    NET_MODE = "is_net"          # tare subtraction active
    NEGATIVE = "is_negative"
    WEIGHT_OVERFLOW = "weight_overflow"
    WEIGHT_UNDERFLOW = "weight_underflow"
    TOTAL_PRICE_OVERFLOW = "total_price_overflow"


# Every field a filter may watch.
ALL_FIELDS = frozenset(
    value for name, value in vars(Field).items() if not name.startswith("_")
)

# Fields that compare with a kg tolerance rather than exact equality.
WEIGHT_FIELDS = frozenset({Field.NET, Field.TARE, Field.GROSS})


def _weight_changed(previous_kg, current_kg, min_delta_kg):
    """True when a weight field moved meaningfully.

    A transition to/from ``None`` (e.g. overflow) always counts. Otherwise the
    move must exceed ``min_delta_kg``.
    """
    if previous_kg is None and current_kg is None:
        return False
    if (previous_kg is None) != (current_kg is None):
        return True
    return abs(current_kg - previous_kg) > min_delta_kg


class ChangeFilter(object):
    """Select which reading fields count as a change for :meth:`Scale.watch`.

    Tick fields with the :class:`Field` constants::

        ChangeFilter([Field.NET])                     # weight only (the default)
        ChangeFilter([Field.NET, Field.TARE])         # weight and tare
        ChangeFilter([Field.UNIT_PRICE, Field.TOTAL_PRICE])   # pricing
        ChangeFilter.everything()                     # any field at all

    :param fields: iterable of :class:`Field` constants to watch.
    :param min_delta_kg: tolerance (kg) applied to weight fields; other fields
        always compare exactly. Raise it to debounce small quantisation steps.
    :param stable_only: when true, unstable readings never count as a change.
    """

    def __init__(self, fields=(Field.NET,), min_delta_kg=0.0, stable_only=False):
        selected = frozenset(fields)
        unknown = selected - ALL_FIELDS
        if unknown:
            raise ValueError(
                "Unknown change field(s): %s. Valid fields: %s"
                % (", ".join(sorted(unknown)), ", ".join(sorted(ALL_FIELDS)))
            )
        if not selected:
            raise ValueError("ChangeFilter needs at least one field to watch")
        self.fields = selected
        self.min_delta_kg = min_delta_kg
        self.stable_only = stable_only

    @classmethod
    def weight(cls, min_delta_kg=0.0, stable_only=False):
        """Trigger on net-weight moves only — the common "weigh, remove, weigh"."""
        return cls([Field.NET], min_delta_kg=min_delta_kg, stable_only=stable_only)

    @classmethod
    def everything(cls, min_delta_kg=0.0, stable_only=False):
        """Trigger on a change in any field (weights, prices, and all flags)."""
        return cls(ALL_FIELDS, min_delta_kg=min_delta_kg, stable_only=stable_only)

    def changed(self, previous, current):
        """True when ``current`` differs from ``previous`` in a watched field.

        ``previous`` is ``None`` for the first reading, which always counts.
        """
        if self.stable_only and not current.is_stable:
            return False
        if previous is None:
            return True
        for field in self.fields:
            previous_value = getattr(previous, field)
            current_value = getattr(current, field)
            if field in WEIGHT_FIELDS:
                if _weight_changed(previous_value, current_value, self.min_delta_kg):
                    return True
            elif previous_value != current_value:
                return True
        return False

    # A filter is callable: filter(previous, current) == filter.changed(...)
    __call__ = changed

    def __repr__(self):
        return "ChangeFilter(fields={%s}, min_delta_kg=%s, stable_only=%s)" % (
            ", ".join(sorted(self.fields)),
            self.min_delta_kg,
            self.stable_only,
        )
