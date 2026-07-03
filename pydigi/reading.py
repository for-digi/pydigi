"""The data model: a single decoded reading and the flags behind it.

Everything here is protocol-agnostic. A :class:`ScaleReading` is what any DIGI
protocol parser produces, so higher layers (streaming, change-watch, the CLI)
never care which wire format it came from.
"""

from dataclasses import dataclass, field
from enum import IntFlag, Enum
from typing import Optional


class StatusFlag(IntFlag):
    """Status Flag — byte 0 of a Type B frame (datasheet §20.4).

    Bits 3-4 encode the price base and are read via :class:`PriceBase`, not here.
    Bit 6 is fixed to 1; bits 5 and 7 are unused.
    """

    ADDITIONAL_PARITY = 0b00000001  # bit 0: an extra parity byte is appended
    NET = 0b00000010                # bit 1: tare subtraction is active
    TOTAL_PRICE_OVERFLOW = 0b00000100  # bit 2: total price overflowed
    PRICE_BASE_LOW = 0b00001000     # bit 3: price-base low bit
    PRICE_BASE_HIGH = 0b00010000    # bit 4: price-base high bit
    FIXED_ONE = 0b01000000          # bit 6: always 1


class WeightConditionFlag(IntFlag):
    """Weight Condition Flag — byte 1 of a Type B frame (datasheet §20.4)."""

    ZERO_SIGN = 0b00000001          # bit 0: zero sign set
    STABLE = 0b00000010             # bit 1: reading is stable and valid
    NEGATIVE_NET = 0b00000100       # bit 2: tare exceeds gross (net is negative)
    WEIGHT_OVERFLOW = 0b00001000    # bit 3: weight above maximum
    WEIGHT_UNDERFLOW = 0b00010000   # bit 4: weight below minimum
    FIXED_ONE = 0b01000000          # bit 6: always 1


class PriceBase(Enum):
    """Unit that the unit-price is quoted per (Status Flag bits 3-4)."""

    PER_KG = "$/kg"
    PER_100G = "$/100g"
    PER_LB = "$/lb"
    PER_QUARTER_LB = "$/(1/4)lb"

    def __str__(self):
        return self.value

    @classmethod
    def from_bits(cls, bits):
        """Map the 2-bit price-base code to a member; unknown codes -> PER_KG."""
        return {
            0b00: cls.PER_KG,
            0b01: cls.PER_100G,
            0b10: cls.PER_LB,
            0b11: cls.PER_QUARTER_LB,
        }.get(bits, cls.PER_KG)


@dataclass(frozen=True)
class ScaleReading:
    """One decoded measurement from a DIGI scale.

    Weights are in kilograms; prices are in the scale's configured currency.
    A value is ``None`` when the scale did not (or could not) transmit it —
    e.g. overflow, underflow, or no PLU programmed — so ``None`` never gets
    confused with a genuine ``0.0``.
    """

    # Raw flag bytes, kept for advanced callers and diagnostics.
    status_flag: StatusFlag
    weight_condition_flag: WeightConditionFlag

    # Weights (kg). None on overflow / underflow / blank field. Gross is
    # derived (see the property below), not stored, so it can never disagree
    # with net + tare.
    weight_net_kg: Optional[float]
    weight_tare_kg: Optional[float]

    # Prices. None when not transmitted or overflowed.
    unit_price: Optional[float]
    total_price: Optional[float]
    price_base: PriceBase

    # The full frame as hex, for logging / bug reports. Excluded from repr/eq.
    raw_hex: str = field(default="", repr=False, compare=False)

    # -- Derived values ----------------------------------------------------
    # Everything below is computed, not stored, so a reading cannot become
    # internally inconsistent (gross disagreeing with net+tare, or a boolean
    # disagreeing with its flag).

    @property
    def weight_gross_kg(self) -> Optional[float]:
        """Gross weight = net + tare. ``None`` if either operand is missing.

        The scale does not transmit gross directly; it is always derived here.
        """
        if self.weight_net_kg is None or self.weight_tare_kg is None:
            return None
        return round(self.weight_net_kg + self.weight_tare_kg, 3)

    @property
    def is_stable(self) -> bool:
        """True when the scale reports the reading as settled and valid."""
        return bool(self.weight_condition_flag & WeightConditionFlag.STABLE)

    @property
    def is_net(self) -> bool:
        """True when tare subtraction is active (weight_net_kg is post-tare)."""
        return bool(self.status_flag & StatusFlag.NET)

    @property
    def is_zero(self) -> bool:
        """True when the scale's zero sign is set."""
        return bool(self.weight_condition_flag & WeightConditionFlag.ZERO_SIGN)

    @property
    def is_negative(self) -> bool:
        """True when net weight is negative (tare exceeds gross)."""
        return bool(self.weight_condition_flag & WeightConditionFlag.NEGATIVE_NET)

    @property
    def weight_overflow(self) -> bool:
        return bool(self.weight_condition_flag & WeightConditionFlag.WEIGHT_OVERFLOW)

    @property
    def weight_underflow(self) -> bool:
        return bool(self.weight_condition_flag & WeightConditionFlag.WEIGHT_UNDERFLOW)

    @property
    def total_price_overflow(self) -> bool:
        return bool(self.status_flag & StatusFlag.TOTAL_PRICE_OVERFLOW)

    def as_dict(self):
        """A plain-dict view of the reading, ready for JSON or structured logs."""
        return {
            "weight_net_kg": self.weight_net_kg,
            "weight_tare_kg": self.weight_tare_kg,
            "weight_gross_kg": self.weight_gross_kg,
            "unit_price": self.unit_price,
            "total_price": self.total_price,
            "price_base": self.price_base.value,
            "is_stable": self.is_stable,
            "is_net": self.is_net,
            "is_zero": self.is_zero,
            "is_negative": self.is_negative,
            "weight_overflow": self.weight_overflow,
            "weight_underflow": self.weight_underflow,
            "total_price_overflow": self.total_price_overflow,
            "status_flag": int(self.status_flag),
            "weight_condition_flag": int(self.weight_condition_flag),
            "raw_hex": self.raw_hex,
        }

    def __str__(self):
        def fmt(value, unit=""):
            return "--" if value is None else ("%.3f%s" % (value, unit))

        return (
            "ScaleReading(net=%s tare=%s gross=%s unit_price=%s total=%s "
            "base=%s stable=%s net=%s zero=%s)"
            % (
                fmt(self.weight_net_kg, " kg"),
                fmt(self.weight_tare_kg, " kg"),
                fmt(self.weight_gross_kg, " kg"),
                fmt(self.unit_price),
                fmt(self.total_price),
                self.price_base,
                self.is_stable,
                self.is_net,
                self.is_zero,
            )
        )
