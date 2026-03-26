"""Message bus module for decoupled channel-agent communication."""

from swarmbot.bus.events import InboundMessage, OutboundMessage
from swarmbot.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
