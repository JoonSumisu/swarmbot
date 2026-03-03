__version__ = "0.5.0"

__all__ = [
    "CoreAgent",
    "SwarmManager",
    "MemoryStore",
    "QMDMemoryStore",
]

import importlib
import sys

try:
    sys.modules["nanobot"] = importlib.import_module("swarmbot.nanobot")
except Exception:
    pass

from .core.agent import CoreAgent
from .swarm.manager import SwarmManager
from .memory.base import MemoryStore
from .memory.qmd import QMDMemoryStore
