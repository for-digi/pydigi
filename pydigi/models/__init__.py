"""Concrete scale models.

A *model* ties a protocol variant to a device's serial defaults and gives it a
registry name the CLI can look up. Import a model here to register it.
"""

from .registry import register, get_model, available_models
from .base import ScaleModel
from .ds781 import DigiDS781

__all__ = ["register", "get_model", "available_models", "ScaleModel", "DigiDS781"]
