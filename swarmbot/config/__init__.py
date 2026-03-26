"""Configuration module for nanobot."""

from swarmbot.config.loader import load_config, get_config_path
from swarmbot.config.schema import Config

__all__ = ["Config", "load_config", "get_config_path"]
