from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class MemoryStore(ABC):
    @abstractmethod
    def add_event(self, agent_id: str, content: str, meta: Dict[str, Any] | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_context(self, agent_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        raise NotImplementedError

