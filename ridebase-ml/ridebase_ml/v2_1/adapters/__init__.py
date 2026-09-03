"""Read-only source adapters for the V2.1 history pipeline."""

from .base import RideBaseSourceAdapter
from .synthetic import SyntheticRideBaseSourceAdapter

__all__ = ["RideBaseSourceAdapter", "SyntheticRideBaseSourceAdapter"]
