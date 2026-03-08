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
    max_agents: int = 4 # Maximum number of agents in the swarm
    # Default roles list is just a suggestion or pool; if dynamic allocation is used, this might be ignored or extended
    # Empty list by default to emphasize dynamic nature
    roles: List[str] = field(default_factory=list)
    architecture: str = "auto" # Default to auto for dynamic behavior
    max_turns: int = 16
    auto_builder: bool = True # Enable dynamic role building by default
    display_mode: str = "simple"  # simple or log


@dataclass
class OverthinkingConfig:
    enabled: bool = True
    interval_minutes: int = 30
    max_steps: int = 20 # Default 0 means no autonomous exploration actions unless configured
    external_checks: Dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": False,
            "email": {"enabled": False, "interval_minutes": 30},
            "calendar": {"enabled": False, "interval_minutes": 60},
            "weather": {"enabled": False, "interval_minutes": 120},
            "project": {"enabled": False, "interval_minutes": 60},
            "urgent_keywords": ["紧急", "urgent", "asap", "ci failed", "deploy failed"],
        }
    )

@dataclass
class OveractionConfig:
    enabled: bool = True
    interval_minutes: int = 60
    check_interaction: bool = True
    check_tasks: bool = True
    check_system: bool = True
    interaction_timeout_hours: int = 4
    scheduled_tasks: List[Dict[str, Any]] = field(default_factory=list)
    self_diagnosis: Dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "log_retention_days": 7,
            "perf_window": 50,
        }
    )


@dataclass
class ToolConfig:
    fs: Dict[str, Any] = field(default_factory=lambda: {"allow_read": [], "allow_write": []})
    shell: Dict[str, Any] = field(default_factory=lambda: {"allow_commands": [], "deny_commands": []}) # Unrestricted by default
    exec: Dict[str, Any] = field(
        default_factory=lambda: {
            "approval_mode": "deny_dangerous",
            "deny_patterns": ["rm -rf /", "shutdown", "reboot", ":(){:|:&};:", "mkfs", "dd if="],
            "default_timeout_seconds": 30,
            "max_concurrent_processes": 8,
        }
    )

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
    manage_gateway: bool = True  # Enable by default
    manage_overthinking: bool = True  # Enable by default
    backup_interval_seconds: int = 60
    health_check_interval_seconds: int = 3600
    gateway_restart_delay_seconds: int = 10
    overthinking_restart_delay_seconds: int = 10

@dataclass
class SwarmbotConfig:
    providers: List[ProviderConfig] = field(default_factory=lambda: [
        ProviderConfig(name="primary"),
        ProviderConfig(name="backup")
    ])
    # Deprecated 'provider' field removed to avoid confusion/conflicts
    swarm: SwarmSettings = field(default_factory=SwarmSettings)
    overthinking: OverthinkingConfig = field(default_factory=OverthinkingConfig)
    overaction: OveractionConfig = field(default_factory=OveractionConfig)
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
        # Create default config with 2 providers (from default_factory)
        cfg = SwarmbotConfig()
        save_config(cfg)
        return cfg
    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        cfg = SwarmbotConfig()
        
        # 1. Load Providers (Priority: providers list > provider object)
        if "providers" in data and isinstance(data["providers"], list) and len(data["providers"]) > 0:
            cfg.providers = []
            for p_data in data["providers"]:
                p = ProviderConfig()
                for k, v in p_data.items():
                    if hasattr(p, k):
                        setattr(p, k, v)
                cfg.providers.append(p)
        elif "provider" in data:
            # Migration: Use existing provider as primary, add backup template
            p = ProviderConfig()
            for k, v in data["provider"].items():
                if hasattr(p, k):
                    setattr(p, k, v)
            p.name = "primary"
            # Keep old provider + add backup template
            cfg.providers = [p, ProviderConfig(name="backup")]
            # Clean up old key on next save implicitly by not loading it into a field
            
        # 2. Load Swarm Settings
        if "swarm" in data:
            for k, v in data["swarm"].items():
                if k == "agent_count": # Migration: agent_count -> max_agents
                    cfg.swarm.max_agents = v
                elif hasattr(cfg.swarm, k):
                    setattr(cfg.swarm, k, v)
                    
        # 3. Load Overthinking
        if "overthinking" in data:
            for k, v in data["overthinking"].items():
                if hasattr(cfg.overthinking, k):
                    setattr(cfg.overthinking, k, v)

        if "overaction" in data:
            for k, v in data["overaction"].items():
                if hasattr(cfg.overaction, k):
                    setattr(cfg.overaction, k, v)

        # 4. Load Tools
        if "tools" in data:
            t_data = data["tools"]
            if "fs" in t_data: cfg.tools.fs = t_data["fs"]
            if "shell" in t_data: cfg.tools.shell = t_data["shell"]
            
        # 5. Load Channels
        if "channels" in data:
            cfg.channels = {}
            for ch_name, ch_data in data["channels"].items():
                ch_cfg = ChannelConfig()
                # Handle simple dict or structured
                conf_dict = ch_data.get("config", {}) if "config" in ch_data else ch_data
                
                if "enabled" in ch_data: ch_cfg.enabled = ch_data["enabled"]
                if "app_id" in ch_data: ch_cfg.app_id = ch_data["app_id"]
                if "app_secret" in ch_data: ch_cfg.app_secret = ch_data["app_secret"]
                if "encrypt_key" in ch_data: ch_cfg.encrypt_key = ch_data["encrypt_key"]
                if "verification_token" in ch_data: ch_cfg.verification_token = ch_data["verification_token"]
                if "token" in ch_data: ch_cfg.token = ch_data["token"]
                
                # Copy other keys to config dict
                for k, v in ch_data.items():
                    if k not in ["enabled", "app_id", "app_secret", "encrypt_key", "verification_token", "token", "config"]:
                        ch_cfg.config[k] = v
                # Merge nested config if present
                if "config" in ch_data and isinstance(ch_data["config"], dict):
                    ch_cfg.config.update(ch_data["config"])
                    
                cfg.channels[ch_name] = ch_cfg

        # 6. Load Daemon
        if "daemon" in data:
            for k, v in data["daemon"].items():
                if hasattr(cfg.daemon, k):
                    setattr(cfg.daemon, k, v)

        # Sync environment variables from primary provider
        if cfg.providers:
            primary = cfg.providers[0]
            if primary.base_url: os.environ["OPENAI_API_BASE"] = primary.base_url
            if primary.api_key: os.environ["OPENAI_API_KEY"] = primary.api_key
            if primary.model: os.environ["LITELLM_MODEL"] = primary.model

        return cfg

    except Exception as e:
        print(f"Error loading config: {e}")
        # Return default with 2 providers if load fails
        return SwarmbotConfig()


def save_config(cfg: SwarmbotConfig) -> None:
    ensure_dirs()
    
    # Prepare channels dict
    channels_dict = {}
    for name, c_cfg in cfg.channels.items():
        # Flatten structure for JSON if desired, or keep nested. 
        # Using nested approach for clarity in JSON
        c_dict = {
            "enabled": c_cfg.enabled,
            "app_id": c_cfg.app_id,
            "app_secret": c_cfg.app_secret,
            "encrypt_key": c_cfg.encrypt_key,
            "verification_token": c_cfg.verification_token,
            "token": c_cfg.token,
            "config": c_cfg.config
        }
        channels_dict[name] = c_dict

    # Prepare providers list
    providers_list = [asdict(p) for p in cfg.providers]

    data = {
        "providers": providers_list,
        "swarm": asdict(cfg.swarm),
        "overthinking": asdict(cfg.overthinking),
        "overaction": asdict(cfg.overaction),
        "tools": asdict(cfg.tools),
        "channels": channels_dict,
        "daemon": asdict(cfg.daemon),
    }

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
