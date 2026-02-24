from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

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
class ChannelConfig:
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    encrypt_key: str = ""
    verification_token: str = ""
    token: str = ""  # For Telegram/Discord/Slack
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DaemonConfig:
    manage_gateway: bool = False
    manage_overthinking: bool = False
    backup_interval_seconds: int = 60
    health_check_interval_seconds: int = 3600
    gateway_restart_delay_seconds: int = 10
    overthinking_restart_delay_seconds: int = 10

@dataclass
class SwarmbotConfig:
    providers: List[ProviderConfig] = field(default_factory=list)
    provider: ProviderConfig = field(default_factory=ProviderConfig) # Deprecated, kept for backward compat
    swarm: SwarmSettings = field(default_factory=SwarmSettings)
    overthinking: OverthinkingConfig = field(default_factory=OverthinkingConfig)
    tools: ToolConfig = field(default_factory=ToolConfig)
    channels: Dict[str, ChannelConfig] = field(default_factory=dict)
    daemon: DaemonConfig = field(default_factory=DaemonConfig)
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
        # Create default config
        cfg = SwarmbotConfig()
        # Initialize default empty tools/channels structure
        cfg.tools = ToolConfig()
        cfg.channels = {}
        # Default provider
        cfg.providers = [ProviderConfig()]
        save_config(cfg)
        return cfg
    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # Migration: If "provider" is in data but "providers" is not, move it
        if "provider" in data and "providers" not in data:
            # Create a list with the single provider
            # We need to construct ProviderConfig from the dict
            p_data = data["provider"]
            # Filter keys that match ProviderConfig fields
            p_fields = {k: v for k, v in p_data.items() if k in ProviderConfig.__annotations__}
            # Note: We can't easily reconstruct the object here without more logic if we just pass dict to dataclass
            # So we will let the normal loading happen, then fix it up after instantiation if possible,
            # OR we modify data before instantiation.
            data["providers"] = [p_data]
            
        # Re-construct with dacite or simple unpacking if structure matches
        # For simplicity in this environment without dacite:
        
        cfg = SwarmbotConfig()
        
        # Load providers
        if "providers" in data:
            cfg.providers = []
            for p_data in data["providers"]:
                p = ProviderConfig()
                for k, v in p_data.items():
                    if hasattr(p, k):
                        setattr(p, k, v)
                cfg.providers.append(p)
        elif "provider" in data:
             # Fallback if migration logic above didn't fully work or for safety
             p = ProviderConfig()
             for k, v in data["provider"].items():
                 if hasattr(p, k):
                     setattr(p, k, v)
             cfg.providers = [p]
             
        # Load other sections
        if "swarm" in data:
            for k, v in data["swarm"].items():
                if hasattr(cfg.swarm, k):
                    setattr(cfg.swarm, k, v)
                    
        if "overthinking" in data:
            for k, v in data["overthinking"].items():
                if hasattr(cfg.overthinking, k):
                    setattr(cfg.overthinking, k, v)

        if "tools" in data:
            # Tools logic...
            pass # (Simplified for brevity, assuming defaults or simple dicts)
            
        # Channels
        if "channels" in data:
            cfg.channels = {}
            for ch_name, ch_data in data["channels"].items():
                ch_cfg = ChannelConfig()
                for k, v in ch_data.items():
                    if hasattr(ch_cfg, k):
                        setattr(ch_cfg, k, v)
                cfg.channels[ch_name] = ch_cfg

        return cfg

    except Exception as e:
        print(f"Error loading config: {e}")
        # Corrupt config, return default
        return SwarmbotConfig(providers=[ProviderConfig()])

    # ... (Provider, Swarm, Overthinking parsing logic remains same)
    
    provider_data = data.get("provider", {})
    provider = ProviderConfig(
        name=provider_data.get("name", "custom"),
        base_url=provider_data.get("base_url", ""),
        api_key=provider_data.get("api_key", ""),
        model=provider_data.get("model", ""),
        max_tokens=provider_data.get("max_tokens", 4096),
        temperature=provider_data.get("temperature", 0.6),
    )
    
    # 2. Force Sync to Environment Variables Immediately upon load
    # This ensures any subsequent code (including imports) sees the correct config
    if provider.base_url:
        os.environ["OPENAI_API_BASE"] = provider.base_url
    if provider.api_key:
        os.environ["OPENAI_API_KEY"] = provider.api_key
    if provider.model:
        os.environ["LITELLM_MODEL"] = provider.model

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

    # Parse channels config
    channels_data = data.get("channels", {})
    channels = {}
    for name, c_data in channels_data.items():
        # Support both simple dict (legacy nanobot style) and structured config
        if isinstance(c_data, dict):
             channels[name] = ChannelConfig(
                 enabled=c_data.get("enabled", False),
                 app_id=c_data.get("app_id", ""),
                 app_secret=c_data.get("app_secret", ""),
                 encrypt_key=c_data.get("encrypt_key", ""),
                 verification_token=c_data.get("verification_token", ""),
                 token=c_data.get("token", ""),
                 config={k:v for k,v in c_data.items() if k not in ["enabled", "app_id", "app_secret", "encrypt_key", "verification_token", "token"]}
             )
    daemon_data = data.get("daemon", {})
    daemon = DaemonConfig(
        manage_gateway=daemon_data.get("manage_gateway", False),
        manage_overthinking=daemon_data.get("manage_overthinking", False),
        backup_interval_seconds=daemon_data.get("backup_interval_seconds", 60),
        health_check_interval_seconds=daemon_data.get("health_check_interval_seconds", 3600),
        gateway_restart_delay_seconds=daemon_data.get("gateway_restart_delay_seconds", 10),
        overthinking_restart_delay_seconds=daemon_data.get("overthinking_restart_delay_seconds", 10),
    )

    return SwarmbotConfig(
        provider=provider,
        swarm=swarm,
        overthinking=overthinking,
        tools=tools,
        channels=channels,
        daemon=daemon,
    )


def save_config(cfg: SwarmbotConfig) -> None:
    ensure_dirs()
    
    # Serialize channels back to dict structure
    channels_dict = {}
    for name, c_cfg in cfg.channels.items():
        channels_dict[name] = c_cfg.config.copy()
        channels_dict[name]["enabled"] = c_cfg.enabled

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "provider": asdict(cfg.provider),
                "swarm": asdict(cfg.swarm),
                "overthinking": asdict(cfg.overthinking),
                "tools": asdict(cfg.tools),
                "channels": channels_dict,
                "daemon": asdict(cfg.daemon),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
