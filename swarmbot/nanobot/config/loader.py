"""Configuration loading utilities."""

import os
from pathlib import Path

from nanobot.config.schema import Config


def get_config_path() -> Path:
    from swarmbot.config_manager import CONFIG_PATH
    return Path(CONFIG_PATH)


def get_data_dir() -> Path:
    """Get the nanobot data directory."""
    from nanobot.utils.helpers import get_data_path
    return get_data_path()


def _swarmbot_to_nanobot_dict() -> dict:
    from swarmbot.config_manager import WORKSPACE_PATH, load_config as load_swarmbot_config
    import logging
    logger = logging.getLogger("nanobot.config")
    
    cfg = load_swarmbot_config()

    channels: dict[str, dict] = {}
    for name, c in (cfg.channels or {}).items():
        payload = dict(c.config or {})
        payload["enabled"] = bool(c.enabled)
        
        # Merge top-level fields from ChannelConfig
        if hasattr(c, "app_id") and c.app_id:
            payload["app_id"] = c.app_id
        if hasattr(c, "app_secret") and c.app_secret:
            payload["app_secret"] = c.app_secret
        if hasattr(c, "encrypt_key") and c.encrypt_key:
            payload["encrypt_key"] = c.encrypt_key
        if hasattr(c, "verification_token") and c.verification_token:
            payload["verification_token"] = c.verification_token
        if hasattr(c, "token") and c.token:
            payload["token"] = c.token

        if name == "feishu":
            if "appId" in payload and "app_id" not in payload:
                payload["app_id"] = payload.pop("appId")
            if "appSecret" in payload and "app_secret" not in payload:
                payload["app_secret"] = payload.pop("appSecret")
            if "encryptKey" in payload and "encrypt_key" not in payload:
                payload["encrypt_key"] = payload.pop("encryptKey")
            if "verificationToken" in payload and "verification_token" not in payload:
                payload["verification_token"] = payload.pop("verificationToken")
            if "allowFrom" in payload and "allow_from" not in payload:
                payload["allow_from"] = payload.pop("allowFrom")
            
            logger.info(f"Loaded Feishu config: enabled={payload.get('enabled')}, app_id={payload.get('app_id', '')[:5]}...")
        
        channels[name] = payload

    port_raw = os.environ.get("OPENCLAW_GATEWAY_PORT")
    port = int(port_raw) if port_raw and port_raw.isdigit() else None

    # Get primary provider details safely
    primary_provider = cfg.providers[0] if cfg.providers else None
    
    # Use safe defaults if no provider configured
    model = primary_provider.model if primary_provider else "gpt-4o"
    max_tokens = primary_provider.max_tokens if primary_provider else 4096
    temperature = primary_provider.temperature if primary_provider else 0.7
    api_key = primary_provider.api_key if primary_provider else ""
    api_base = primary_provider.base_url if primary_provider else None

    data: dict = {
        "agents": {
            "defaults": {
                "workspace": str(WORKSPACE_PATH),
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        },
        "providers": {
            "custom": {
                "api_key": api_key,
                "api_base": api_base,
            }
        },
        "channels": channels,
        "gateway": {},
    }
    if port is not None:
        data["gateway"]["port"] = port
    return data


def load_config(config_path: Path | None = None) -> Config:
    data = _swarmbot_to_nanobot_dict()
    data = _migrate_config(data)
    return Config.model_validate(data)


def save_config(config: Config, config_path: Path | None = None) -> None:
    from swarmbot.config_manager import ChannelConfig, ProviderConfig, load_config as load_swarmbot_config, save_config as save_swarmbot_config

    cfg = load_swarmbot_config()

    if not cfg.providers:
        cfg.providers = [ProviderConfig(name="primary")]

    # Update primary provider
    primary = cfg.providers[0]
    primary.model = config.agents.defaults.model
    primary.max_tokens = config.agents.defaults.max_tokens
    primary.temperature = config.agents.defaults.temperature

    custom = config.providers.custom
    primary.api_key = custom.api_key or ""
    primary.base_url = custom.api_base or ""

    channels: dict[str, ChannelConfig] = {}
    for name, c in config.channels.model_dump(by_alias=True).items():
        enabled = bool(c.get("enabled", False))
        conf = {k: v for k, v in c.items() if k != "enabled"}
        channels[name] = ChannelConfig(enabled=enabled, config=conf)
    cfg.channels = channels

    save_swarmbot_config(cfg)


def _migrate_config(data: dict) -> dict:
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    return data
