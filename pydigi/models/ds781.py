"""DIGI DS-781 — the first concrete model.

Type B protocol, 9600 8N1, ~30 kg capacity. All behaviour is inherited from
:class:`ScaleModel`; this class is pure metadata. Use it as the template for the
next model.
"""

from ..protocol import TypeBProtocol
from .base import ScaleModel
from .registry import register


@register
class DigiDS781(ScaleModel):
    """DIGI DS-781: Type B (Standard command) protocol, 9600 8N1, ~30 kg."""

    name = "ds781"
    protocol_class = TypeBProtocol
    default_baudrate = 9600
    max_weight_kg = 30.0
