"""RideBase Policy Module.

Contains deterministic maintenance assessment and severity calculations.
"""
from __future__ import annotations

from .urgency import calculate_maintenance_urgency

__all__ = ["calculate_maintenance_urgency"]
