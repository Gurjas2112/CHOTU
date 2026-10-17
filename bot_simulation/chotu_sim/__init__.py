"""CHOTU digital-twin simulator (drives the real chotu_core autonomy stack)."""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from .engine import SimResult, Simulation  # noqa: E402
from .world import generate_room  # noqa: E402

__all__ = ["Simulation", "SimResult", "generate_room"]
