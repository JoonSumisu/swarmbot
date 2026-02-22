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

    def _sanitize_recursive(self, obj: Any) -> Any:
        if isinstance(obj, str):
            # Replace surrogate characters that are invalid in UTF-8
            return obj.encode('utf-8', 'replace').decode('utf-8')
        elif isinstance(obj, list):
            return [self._sanitize_recursive(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self._sanitize_recursive(v) for k, v in obj.items()}
        else:
            return obj

    def completion(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        # Sanitize messages to prevent surrogate errors in JSON encoding
        messages = self._sanitize_recursive(messages)
        
        # Filter out empty messages to prevent "Invalid request: message must not be empty" errors
        # Some local models/litellm are strict about this.
        filtered_messages = []
        for m in messages:
            content = m.get("content")
            # Keep if content is non-empty OR if it's a tool call (content can be null) OR tool output
            if content or m.get("tool_calls") or m.get("role") == "tool":
                filtered_messages.append(m)
        
        # --- Local Model Optimization ---
        # If base_url is set, we assume it's an OpenAI-compatible endpoint unless it's a known provider.
        model_name = self.config.model
        custom_llm_provider = None
        
        known_providers = ["openai", "anthropic", "azure", "gemini", "vertex_ai", "bedrock", "ollama", "huggingface", "replicate", "openrouter"]
        
        if self.config.base_url:
            # Check if model name starts with a known provider
            is_known = any(model_name.startswith(p + "/") for p in known_providers)
            
            if not is_known:
                # E.g. "openbmb/agentcpm-explore" -> Treat as OpenAI compatible
                custom_llm_provider = "openai"
            elif model_name.startswith("openai/"):
                # Already prefixed, standard behavior
                pass
            
        params = {
            "model": model_name,
            "messages": filtered_messages,
            "stream": stream,
            "api_key": self.config.api_key or "sk-dummy", # Local models often need a dummy key
            "base_url": self.config.base_url,
        }
        
        if custom_llm_provider:
            params["custom_llm_provider"] = custom_llm_provider
            
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
