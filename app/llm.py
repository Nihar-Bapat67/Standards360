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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.llm_providers import CompatibleChatProvider  # noqa: E402

TIMEOUT = 45
JSON_BLOCK = re.compile(r"\{.*\}", re.S)


class LLM:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 base_url: Optional[str] = None):
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.model = model or settings.llm_model
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.provider_name = settings.llm_provider
        self.provider = CompatibleChatProvider(self.provider_name, self.api_key,
                               self.model, self.base_url)
        self.last_error: Optional[str] = None

    @property
    def available(self) -> bool:
        return bool(self.provider.api_key and settings.llm_no_retention_confirmed)

    def complete(self, system: str, user: str, temperature: float = 0.0,
                 max_tokens: int = 700) -> Optional[str]:
        """One chat completion, or None when the model is unavailable or the call fails.

        Sarvam accepts either an `api-subscription-key` header or a bearer token depending on the
        endpoint, so both are tried once and the working one is remembered.
        """
        if not self.available:
            self.last_error = ("provider no-retention terms not confirmed"
                               if self.provider.api_key else "no api key configured")
            return None

        content, self.last_error = self.provider.complete(system, user, temperature, max_tokens)
        return content

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
