from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx
from litellm import completion as litellm_completion, acompletion as litellm_acompletion

from .config import LLMConfig
from .config_manager import ProviderConfig, load_config


class OpenAICompatibleClient:
    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or LLMConfig()

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
        # Delegate to litellm for robust handling of base_url and providers
        params = {
            "model": self.config.model,
            "messages": messages,
            "stream": stream,
            "api_key": self.config.api_key,
            "base_url": self.config.base_url,
        }
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if tools is not None:
            params["tools"] = tools
            params["tool_choice"] = "auto"
            
        # litellm handles the call
        return await litellm_acompletion(**params)

    def completion(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        params = {
            "model": self.config.model,
            "messages": messages,
            "stream": stream,
            "api_key": self.config.api_key,
            "base_url": self.config.base_url,
        }
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if tools is not None:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        # Implement exponential backoff for rate limits
        import time
        import random
        from litellm import RateLimitError
        
        max_retries = 7
        base_delay = 2.0
        
        for attempt in range(max_retries):
            try:
                return litellm_completion(**params)
            except RateLimitError as e:
                if attempt == max_retries - 1:
                    raise e
                
                # Calculate delay with jitter: base * 2^attempt + jitter
                delay = (base_delay * (2 ** attempt)) + (random.random() * 0.5)
                print(f"[LLMClient] Rate limit hit. Retrying in {delay:.2f}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(delay)
            except Exception as e:
                # Also catch Quota Exceeded as it might be transient if concurrency related
                if "quota" in str(e).lower() or "429" in str(e):
                    if attempt == max_retries - 1:
                        raise e
                    delay = (base_delay * (2 ** attempt)) + 1.0
                    print(f"[LLMClient] Quota/429 error. Retrying in {delay:.2f}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(delay)
                else:
                    raise e
