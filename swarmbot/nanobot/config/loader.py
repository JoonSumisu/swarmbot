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

    cfg = load_swarmbot_config()

    channels: dict[str, dict] = {}
    for name, c in (cfg.channels or {}).items():
        payload = dict(c.config or {})
        payload["enabled"] = bool(c.enabled)
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
        channels[name] = payload

    port_raw = os.environ.get("OPENCLAW_GATEWAY_PORT")
    port = int(port_raw) if port_raw and port_raw.isdigit() else None

    data: dict = {
        "agents": {
            "defaults": {
                "workspace": str(WORKSPACE_PATH),
                "model": cfg.provider.model,
                "max_tokens": cfg.provider.max_tokens,
                "temperature": cfg.provider.temperature,
            }
        },
        "providers": {
            "custom": {
                "api_key": cfg.provider.api_key,
                "api_base": cfg.provider.base_url or None,
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
    from swarmbot.config_manager import ChannelConfig, load_config as load_swarmbot_config, save_config as save_swarmbot_config

    cfg = load_swarmbot_config()

    cfg.provider.model = config.agents.defaults.model
    cfg.provider.max_tokens = config.agents.defaults.max_tokens
    cfg.provider.temperature = config.agents.defaults.temperature

    custom = config.providers.custom
    cfg.provider.api_key = custom.api_key or ""
    cfg.provider.base_url = custom.api_base or ""

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
