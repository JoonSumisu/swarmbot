from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional

CONFIG_HOME = os.path.expanduser("~/.swarmbot")
CONFIG_PATH = os.path.join(CONFIG_HOME, "config.json")
WORKSPACE_PATH = os.path.join(CONFIG_HOME, "workspace")


@dataclass
class ProviderConfig:
    name: str = "custom"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.6


@dataclass
class SwarmSettings:
    agent_count: int = 4
    roles: List[str] = field(default_factory=lambda: ["planner", "coder", "critic", "summarizer"])
    architecture: str = "concurrent"
    max_turns: int = 16
    auto_builder: bool = False
    display_mode: str = "simple"  # simple or log


@dataclass
class OverthinkingConfig:
    enabled: bool = False
    interval_minutes: int = 30
    max_steps: int = 10


@dataclass
class SwarmbotConfig:
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    swarm: SwarmSettings = field(default_factory=SwarmSettings)
    overthinking: OverthinkingConfig = field(default_factory=OverthinkingConfig)


def ensure_dirs() -> None:
    os.makedirs(CONFIG_HOME, exist_ok=True)
    os.makedirs(WORKSPACE_PATH, exist_ok=True)


def load_config() -> SwarmbotConfig:
    ensure_dirs()
    if not os.path.exists(CONFIG_PATH):
        cfg = SwarmbotConfig()
        save_config(cfg)
        return cfg
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # robust load with defaults
    provider = data.get("provider", {})
    swarm = data.get("swarm", {})
    overthinking = data.get("overthinking", {})
    
    # Load defaults first, then override with file data if present
    # We strip sensitive defaults from code to ensure clean distribution
    return SwarmbotConfig(
        provider=ProviderConfig(
            name=provider.get("name", "custom"),
            base_url=provider.get("base_url", ""),
            api_key=provider.get("api_key", ""),
            model=provider.get("model", ""),
            max_tokens=provider.get("max_tokens", 4096),
            temperature=provider.get("temperature", 0.6),
        ),
        swarm=SwarmSettings(
            agent_count=swarm.get("agent_count", 4),
            roles=swarm.get("roles", ["planner", "coder", "critic", "summarizer"]),
            architecture=swarm.get("architecture", "concurrent"),
            max_turns=swarm.get("max_turns", 16),
            auto_builder=swarm.get("auto_builder", False),
            display_mode=swarm.get("display_mode", "log"),  # Force log mode default for visibility
        ),
        overthinking=OverthinkingConfig(
            enabled=overthinking.get("enabled", False),
            interval_minutes=overthinking.get("interval_minutes", 30),
            max_steps=overthinking.get("max_steps", 10),
        ),
    )


def save_config(cfg: SwarmbotConfig) -> None:
    ensure_dirs()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "provider": asdict(cfg.provider),
                "swarm": asdict(cfg.swarm),
                "overthinking": asdict(cfg.overthinking),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
