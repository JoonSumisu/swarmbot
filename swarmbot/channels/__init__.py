"""Chat channels module with plugin architecture."""

from swarmbot.channels.base import BaseChannel
from swarmbot.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
