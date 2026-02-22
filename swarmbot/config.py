from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMConfig:
    # Default values are intentionally blank or placeholder to force config loading
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout: float = 120.0


@dataclass
class SwarmConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    max_agents: int = 8
    max_turns: int = 32


DEFAULT_CONFIG = SwarmConfig()

