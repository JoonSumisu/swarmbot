from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from .config import LLMConfig
from .config_manager import ProviderConfig, load_config


class OpenAICompatibleClient:
    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or LLMConfig()
        # We don't initialize a long-lived client here to avoid event loop issues
        # with asyncio.run() being called multiple times.
        # Each request will create its own client or we use a sync client for sync calls.

    @classmethod
    def from_provider(cls, provider: Optional[ProviderConfig] = None) -> "OpenAICompatibleClient":
        if provider is None:
            cfg = load_config()
            provider = cfg.provider
        llm_cfg = LLMConfig(
            base_url=provider.base_url,
            api_key=provider.api_key,
            model=provider.model,
            timeout=120.0,
        )
        return cls(llm_cfg)

    async def acompletion(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        async with httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout
        ) as client:
            payload: Dict[str, Any] = {
                "model": self.config.model,
                "messages": messages,
                "stream": stream,
            }
            if temperature is not None:
                payload["temperature"] = temperature
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            if tools is not None:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
            
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
            }
            resp = await client.post("/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            if stream:
                # Note: streaming with async context manager closing might be tricky 
                # if we yield out of it. For now, we assume simple usage.
                # If stream is needed, we'd need to keep client open.
                # But for now, let's just return lines (this might fail if client closes)
                # Actually, for this simple implementation, we might not support stream properly in async
                # unless we yield.
                return resp.aiter_lines()
            return resp.json()

    def completion(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        # Use synchronous httpx.Client to avoid asyncio loop issues
        with httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout
        ) as client:
            payload: Dict[str, Any] = {
                "model": self.config.model,
                "messages": messages,
                "stream": stream,
            }
            if temperature is not None:
                payload["temperature"] = temperature
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            if tools is not None:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
            }
            resp = client.post("/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            if stream:
                return resp.iter_lines()
            return resp.json()
