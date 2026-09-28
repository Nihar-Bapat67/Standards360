"""Provider adapters for chat-completion APIs used by the orchestration layer."""

from typing import Optional, Protocol

import requests

TIMEOUT = 45


class LLMProvider(Protocol):
    """Small contract shared by hosted and future local chat providers."""

    def complete(self, system: str, user: str, temperature: float,
                 max_tokens: int) -> tuple[Optional[str], Optional[str]]: ...


class CompatibleChatProvider:
    """Sarvam and OpenAI-compatible chat endpoint adapter."""

    def __init__(self, name: str, api_key: Optional[str], model: str, base_url: str):
        self.name = name
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def complete(self, system: str, user: str, temperature: float,
                 max_tokens: int) -> tuple[Optional[str], Optional[str]]:
        if not self.api_key:
            return None, "no api key configured"

        suffix = "/v1/chat/completions" if self.name == "sarvam" else "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        styles = ["subscription", "bearer"] if self.name == "sarvam" else ["bearer"]
        last_error = None
        for style in styles:
            headers = ({"api-subscription-key": self.api_key} if style == "subscription"
                       else {"Authorization": f"Bearer {self.api_key}"})
            headers["Content-Type"] = "application/json"
            try:
                response = requests.post(f"{self.base_url}{suffix}", headers=headers,
                                         json=payload, timeout=TIMEOUT)
            except requests.RequestException as error:
                last_error = f"{type(error).__name__}: {error}"
                continue
            if not response.ok:
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                if self.name != "sarvam" or response.status_code not in (401, 403):
                    break
                continue
            try:
                message = response.json()["choices"][0]["message"]
            except (ValueError, KeyError, IndexError, TypeError) as error:
                return None, f"unexpected response shape: {type(error).__name__}"
            content = message.get("content") or message.get("reasoning_content") or ""
            if not content.strip():
                return None, "model returned an empty reply; raise max_tokens"
            return content, None
        return None, last_error or "provider request failed"