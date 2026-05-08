from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv


class LLMClient:
    def __init__(
        self,
        provider_name: str,
        provider_type: str,
        host: str,
        model: str,
        api_key: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 8000,
        timeout_seconds: int = 180,
    ) -> None:
        self.provider_name = provider_name
        self.provider_type = provider_type
        self.host = host.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "LLMClient":
        load_dotenv()

        active_provider_env = config.get("active_provider_env", "API")
        active_provider = os.getenv(active_provider_env, "deepseek").strip().lower()

        providers = config.get("providers", {})
        if active_provider not in providers:
            raise RuntimeError(
                f"未知模型提供方：{active_provider}。可选项：{list(providers.keys())}"
            )

        provider_config = providers[active_provider]
        defaults = config.get("defaults", {})

        provider_type = provider_config["type"]

        host_env = provider_config["host_env"]
        model_env = provider_config["model_env"]

        host = os.getenv(host_env)
        model = os.getenv(model_env)

        if not host:
            raise RuntimeError(f"未找到环境变量：{host_env}")

        if not model:
            raise RuntimeError(f"未找到环境变量：{model_env}")

        api_key = None
        api_key_env = provider_config.get("api_key_env")
        if api_key_env:
            api_key = os.getenv(api_key_env)
            if not api_key:
                raise RuntimeError(f"未找到环境变量：{api_key_env}")

        return cls(
            provider_name=active_provider,
            provider_type=provider_type,
            host=host,
            model=model,
            api_key=api_key,
            temperature=float(defaults.get("temperature", 0.2)),
            max_tokens=int(defaults.get("max_tokens", 8000)),
            timeout_seconds=int(defaults.get("timeout_seconds", 180)),
        )

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        if self.provider_type == "openai_compatible":
            return self._chat_openai_compatible(system_prompt, user_prompt)

        if self.provider_type == "ollama_chat":
            return self._chat_ollama(system_prompt, user_prompt)

        raise RuntimeError(f"不支持的 provider_type：{self.provider_type}")

    def _chat_openai_compatible(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        }

        headers = {
            "Content-Type": "application/json",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.post(
            self.host,
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )

        if response.status_code >= 400:
            raise RuntimeError(
                f"{self.provider_name} 请求失败："
                f"status={response.status_code}, body={response.text[:1500]}"
            )

        data = response.json()

        try:
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise RuntimeError(f"无法解析 {self.provider_name} 返回结果：{data}") from exc

    def _chat_ollama(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "options": {
                "temperature": self.temperature,
            },
        }

        response = requests.post(
            self.host,
            json=payload,
            timeout=self.timeout_seconds,
        )

        if response.status_code >= 400:
            raise RuntimeError(
                f"Ollama 请求失败：status={response.status_code}, body={response.text[:1500]}"
            )

        data = response.json()

        try:
            return data["message"]["content"]
        except Exception as exc:
            raise RuntimeError(f"无法解析 Ollama 返回结果：{data}") from exc