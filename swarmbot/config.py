from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMConfig:
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "dummy"
    model: str = "local-model"
    timeout: float = 120.0


@dataclass
class SwarmConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    max_agents: int = 4
    max_turns: int = 16


DEFAULT_CONFIG = SwarmConfig()

