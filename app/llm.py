"""Thin client for the language model, used only for phrasing and extraction.

Every fact in this product comes from the catalogue or the indexed clauses. The model is asked to
structure or phrase text, never to supply a standard number, and whatever it writes passes through
D1 before anyone sees it. When no key is configured, `available` is False and each caller falls back
to deterministic behaviour, so the whole system still runs offline.

    from app.llm import LLM
    LLM().complete("Return JSON only.", "Extract the product from: 500 MT of 43 grade OPC")
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

TIMEOUT = 45
JSON_BLOCK = re.compile(r"\{.*\}", re.S)


class LLM:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 base_url: Optional[str] = None):
        self.api_key = api_key or settings.sarvam_api_key
        self.model = model or settings.sarvam_chat_model
        self.base_url = (base_url or settings.sarvam_base_url).rstrip("/")
        self.last_error: Optional[str] = None
        self._header_style = None      # discovered on the first successful call

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def complete(self, system: str, user: str, temperature: float = 0.0,
                 max_tokens: int = 700) -> Optional[str]:
        """One chat completion, or None when the model is unavailable or the call fails.

        Sarvam accepts either an `api-subscription-key` header or a bearer token depending on the
        endpoint, so both are tried once and the working one is remembered.
        """
        if not self.available:
            self.last_error = "no api key configured"
            return None

        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        styles = [self._header_style] if self._header_style else ["subscription", "bearer"]
        for style in styles:
            headers = ({"api-subscription-key": self.api_key} if style == "subscription"
                       else {"Authorization": f"Bearer {self.api_key}"})
            headers["Content-Type"] = "application/json"
            try:
                response = requests.post(f"{self.base_url}/v1/chat/completions",
                                         headers=headers, json=payload, timeout=TIMEOUT)
            except requests.RequestException as e:
                self.last_error = f"{type(e).__name__}: {e}"
                continue
            if response.status_code in (401, 403):
                self.last_error = f"HTTP {response.status_code} with {style} header"
                continue
            if not response.ok:
                self.last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                continue
            try:
                self._header_style = style
                message = response.json()["choices"][0]["message"]
            except (ValueError, KeyError, IndexError) as e:
                self.last_error = f"unexpected response shape: {type(e).__name__}"
                return None
            # A reasoning model leaves `content` null and puts its working in `reasoning_content`
            # until the token budget allows an answer. Prefer the answer, fall back to the working.
            content = message.get("content") or message.get("reasoning_content") or ""
            if not content.strip():
                self.last_error = "model returned an empty reply; raise max_tokens"
                return None
            return content
        return None

    def complete_json(self, system: str, user: str, **kwargs) -> Optional[dict]:
        """A completion parsed as JSON, tolerating the fences models like to add."""
        text = self.complete(system, user, **kwargs)
        if not text:
            return None
        block = JSON_BLOCK.search(text)
        if not block:
            self.last_error = "no JSON object in the reply"
            return None
        try:
            return json.loads(block.group(0))
        except ValueError as e:
            self.last_error = f"invalid JSON: {e}"
            return None
