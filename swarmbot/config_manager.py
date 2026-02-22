from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional

CONFIG_HOME = os.path.expanduser("~/.swarmbot")
CONFIG_PATH = os.path.join(CONFIG_HOME, "config.json")
WORKSPACE_PATH = os.path.join(CONFIG_HOME, "workspace")
BOOT_CONFIG_PATH = os.path.join(CONFIG_HOME, "boot")


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
    max_steps: int = 0 # Default 0 means no autonomous exploration actions unless configured


@dataclass
class ToolConfig:
    fs: Dict[str, Any] = field(default_factory=lambda: {"allow_read": [], "allow_write": []})
    shell: Dict[str, Any] = field(default_factory=lambda: {"allow_commands": [], "deny_commands": []}) # Unrestricted by default

@dataclass
class SwarmbotConfig:
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    swarm: SwarmSettings = field(default_factory=SwarmSettings)
    overthinking: OverthinkingConfig = field(default_factory=OverthinkingConfig)
    tools: ToolConfig = field(default_factory=ToolConfig)
    # No more hardcoded paths here, rely on constants

def ensure_dirs() -> None:
    # Ensure config and workspace exist
    os.makedirs(CONFIG_HOME, exist_ok=True)
    os.makedirs(WORKSPACE_PATH, exist_ok=True)
    # Ensure boot config dir exists
    os.makedirs(BOOT_CONFIG_PATH, exist_ok=True)

def load_config() -> SwarmbotConfig:
    ensure_dirs()
    if not os.path.exists(CONFIG_PATH):
        cfg = SwarmbotConfig()
        save_config(cfg)
        return cfg
    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        # Corrupt config, return default
        return SwarmbotConfig()

    provider_data = data.get("provider", {})
    provider = ProviderConfig(
        name=provider_data.get("name", "custom"),
        base_url=provider_data.get("base_url", ""),
        api_key=provider_data.get("api_key", ""),
        model=provider_data.get("model", ""),
        max_tokens=provider_data.get("max_tokens", 4096),
        temperature=provider_data.get("temperature", 0.6),
    )

    swarm_data = data.get("swarm", {})
    swarm = SwarmSettings(
        agent_count=swarm_data.get("agent_count", 4),
        roles=swarm_data.get("roles", ["planner", "coder", "critic", "summarizer"]),
        architecture=swarm_data.get("architecture", "concurrent"),
        max_turns=swarm_data.get("max_turns", 16),
        auto_builder=swarm_data.get("auto_builder", False),
        display_mode=swarm_data.get("display_mode", "log"),
    )

    overthinking_data = data.get("overthinking", {})
    overthinking = OverthinkingConfig(
        enabled=overthinking_data.get("enabled", False),
        interval_minutes=overthinking_data.get("interval_minutes", 30),
        max_steps=overthinking_data.get("max_steps", 0), # Default 0 safe
    )
    
    tools_data = data.get("tools", {})
    tools = ToolConfig(
        fs=tools_data.get("fs", {}),
        shell=tools_data.get("shell", {})
    )

    return SwarmbotConfig(
        provider=provider,
        swarm=swarm,
        overthinking=overthinking,
        tools=tools
    )


def save_config(cfg: SwarmbotConfig) -> None:
    ensure_dirs()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "provider": asdict(cfg.provider),
                "swarm": asdict(cfg.swarm),
                "overthinking": asdict(cfg.overthinking),
                "tools": asdict(cfg.tools),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
