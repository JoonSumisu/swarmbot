from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx
from litellm import completion as litellm_completion, acompletion as litellm_acompletion

from .config import LLMConfig
from .config_manager import ProviderConfig, load_config

# Disable LiteLLM logging noise
litellm_completion.__globals__["litellm"].suppress_debug_info = True
litellm_completion.__globals__["litellm"].drop_params = True



class OpenAICompatibleClient:
    def __init__(self, configs: List[LLMConfig] = None, config: Optional[LLMConfig] = None) -> None:
        self.configs = configs or []
        if config:
            self.configs.insert(0, config)
        if not self.configs:
            self.configs = [LLMConfig()]

    @property
    def config(self) -> LLMConfig:
        return self.configs[0] if self.configs else LLMConfig()

    @classmethod
    def from_provider(cls, provider: Optional[ProviderConfig] = None, providers: Optional[List[ProviderConfig]] = None) -> "OpenAICompatibleClient":
        if provider is None and providers is None:
            cfg = load_config()
            # Prefer providers list if available
            if hasattr(cfg, "providers") and cfg.providers:
                providers = cfg.providers
            elif hasattr(cfg, "provider"):
                provider = cfg.provider
        
        llm_configs = []
        if providers:
            for p in providers:
                llm_configs.append(LLMConfig(
                    base_url=p.base_url,
                    api_key=p.api_key,
                    model=p.model,
                    timeout=300.0,  # Increased timeout from 120.0 to 300.0 for complex tasks
                    max_tokens=p.max_tokens,
                    temperature=p.temperature,
                ))
        
        if provider:
            llm_configs.insert(0, LLMConfig(
                base_url=provider.base_url,
                api_key=provider.api_key,
                model=provider.model,
                timeout=300.0,  # Increased timeout from 120.0 to 300.0
                max_tokens=provider.max_tokens,
                temperature=provider.temperature,
            ))
            
        return cls(configs=llm_configs)

    async def acompletion(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        messages = self._normalize_messages(messages)

        last_exception = None
        
        # Iterate through providers for failover
        for idx, config in enumerate(self.configs):
            try:
                # Delegate to litellm for robust handling of base_url and providers
                model_name = config.model
                if config.base_url and not any(model_name.startswith(p + "/") for p in ["openai", "anthropic", "azure", "gemini", "vertex_ai", "bedrock", "ollama", "huggingface", "replicate", "openrouter"]):
                    model_name = f"openai/{model_name}"

                params = {
                    "model": model_name,
                    "messages": messages,
                    "stream": stream,
                    "api_key": config.api_key,
                    "base_url": config.base_url,
                    "timeout": config.timeout,
                }
                if temperature is not None:
                    params["temperature"] = temperature
                elif hasattr(config, "temperature") and config.temperature is not None:
                    params["temperature"] = config.temperature

                if max_tokens is not None:
                    params["max_tokens"] = max_tokens
                elif hasattr(config, "max_tokens") and config.max_tokens is not None:
                    params["max_tokens"] = config.max_tokens

                if tools:
                    params["tools"] = tools
                    params["tool_choice"] = "auto"
                    
                # litellm handles the call
                # Note: Qwen models might be strict about tool definitions.
                # If tools provided, ensure no None values in tool_choice or tools list
                
                return await litellm_acompletion(**params)
            except Exception as e:
                # Catch specific BadRequestError which often indicates Prompt/Tool schema issues
                err_msg = str(e)
                if "BadRequestError" in err_msg and "OpenAIException" in err_msg:
                    print(f"[LLM] Critical Schema Error with {config.model}: {e}")
                    
                    # DEBUG: Print the failing payload to help user debug
                    import json
                    try:
                        print(f"[LLM DEBUG] Failing Messages Sample (Last 2): {json.dumps(messages[-2:], default=str)}")
                        if "tools" in params:
                            print(f"[LLM DEBUG] Failing Tools Sample (First 1): {json.dumps(params['tools'][:1], default=str)}")
                    except:
                        pass

                    # Attempt fallback: Try without tools if it was a tool call
                    if "tools" in params:
                         print(f"[LLM] Retrying {config.model} WITHOUT tools due to schema error...")
                         params.pop("tools", None)
                         params.pop("tool_choice", None)
                         try:
                             return await litellm_acompletion(**params)
                         except Exception as retry_e:
                             print(f"[LLM] Retry failed: {retry_e}")
                             last_exception = retry_e
                    else:
                        last_exception = e
                else:
                    print(f"[LLM] Provider {idx+1} ({config.model}) failed: {e}")
                    last_exception = e
        
        if last_exception:
            raise last_exception
        return None

    def _sanitize_recursive(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return obj.encode("utf-8", "replace").decode("utf-8")
        elif isinstance(obj, list):
            return [self._sanitize_recursive(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self._sanitize_recursive(v) for k, v in obj.items()}
        else:
            return obj

    def _normalize_messages(self, messages: List[Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for m in self._sanitize_recursive(messages):
            if isinstance(m, dict):
                item = dict(m)
            elif hasattr(m, "model_dump"):
                item = m.model_dump()
            elif hasattr(m, "dict"):
                item = m.dict()
            elif hasattr(m, "__dict__"):
                item = dict(m.__dict__)
            else:
                continue
            role = item.get("role")
            if not role:
                continue
            content = item.get("content")
            if content is None:
                item["content"] = ""
            elif not isinstance(content, str):
                item["content"] = str(content)
            if item.get("content") or item.get("tool_calls") or role == "tool":
                normalized.append(item)
        return normalized

    def completion(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        filtered_messages = self._normalize_messages(messages)
        
        # --- Local Model Optimization ---
        # If base_url is set, we assume it's an OpenAI-compatible endpoint unless it's a known provider.
        model_name = self.config.model
        custom_llm_provider = None
        
        known_providers = ["openai", "anthropic", "azure", "gemini", "vertex_ai", "bedrock", "ollama", "huggingface", "replicate", "openrouter"]
        
        if self.config.base_url:
            # Check if model name starts with a known provider
            is_known = any(model_name.startswith(p + "/") for p in known_providers)
            
            if not is_known:
                # Treat unknown model prefixes as OpenAI compatible custom models
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
            "timeout": self.config.timeout,
        }
        
        if custom_llm_provider:
            params["custom_llm_provider"] = custom_llm_provider
            
        if temperature is not None:
            params["temperature"] = temperature
        elif getattr(self.config, "temperature", None) is not None:
            params["temperature"] = self.config.temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        elif getattr(self.config, "max_tokens", None) is not None:
            params["max_tokens"] = self.config.max_tokens
        if tools:
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
                delay = (base_delay * (2 ** attempt)) + (random.random() * 0.5)
                print(f"[LLMClient] Rate limit hit. Retrying in {delay:.2f}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(delay)
            except Exception as e:
                msg = str(e)
                if "failed to process regex" in msg.lower():
                    try:
                        import re as _re
                        def _clean(obj: Any) -> Any:
                            if isinstance(obj, str):
                                return _re.sub(r"[()\\`]", "", obj)
                            if isinstance(obj, list):
                                return [_clean(x) for x in obj]
                            if isinstance(obj, dict):
                                return {k: _clean(v) for k, v in obj.items()}
                            return obj
                        cleaned_messages = _clean(params.get("messages", []))
                        params["messages"] = cleaned_messages
                        return litellm_completion(**params)
                    except Exception as e2:
                        msg = str(e2)
                if "quota" in msg.lower() or "429" in msg:
                    if attempt == max_retries - 1:
                        raise e
                    delay = (base_delay * (2 ** attempt)) + 1.0
                    print(f"[LLMClient] Quota/429 error. Retrying in {delay:.2f}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(delay)
                elif "BadRequestError" in msg and "OpenAIException" in msg and "tools" in params:
                    try:
                        fallback_params = dict(params)
                        fallback_params.pop("tools", None)
                        fallback_params.pop("tool_choice", None)
                        return litellm_completion(**fallback_params)
                    except Exception:
                        pass
                    try:
                        import os
                        import json as _json
                        log_dir = os.path.expanduser("~/.swarmbot/logs")
                        os.makedirs(log_dir, exist_ok=True)
                        ts = int(time.time())
                        log_path = os.path.join(log_dir, f"llm_error_prompt_{ts}.json")
                        with open(log_path, "w", encoding="utf-8") as f:
                            _json.dump(
                                {"params": {k: v for k, v in params.items() if k != "api_key"}},
                                f,
                                ensure_ascii=False,
                                indent=2,
                            )
                        print(f"[LLMClient] Error during completion, prompt saved to {log_path}: {e}")
                    except Exception:
                        print(f"[LLMClient] Error during completion (logging failed): {e}")
                    raise e
                else:
                    try:
                        import os
                        import json as _json
                        log_dir = os.path.expanduser("~/.swarmbot/logs")
                        os.makedirs(log_dir, exist_ok=True)
                        ts = int(time.time())
                        log_path = os.path.join(log_dir, f"llm_error_prompt_{ts}.json")
                        with open(log_path, "w", encoding="utf-8") as f:
                            _json.dump(
                                {"params": {k: v for k, v in params.items() if k != "api_key"}},
                                f,
                                ensure_ascii=False,
                                indent=2,
                            )
                        print(f"[LLMClient] Error during completion, prompt saved to {log_path}: {e}")
                    except Exception:
                        print(f"[LLMClient] Error during completion (logging failed): {e}")
                    raise e
