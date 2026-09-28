"""Configuration and secrets.

Secrets are read from the environment, or from a `.env` file at the project root which git ignores.
Nothing in this repository ever contains a key: the file is local to each developer's machine.

    SARVAM_API_KEY=...        used by B2 (translation) and the phrasing calls in B3, B5 and D2
    BIS_CONTACT=...           polite contact header for the A1 crawler

    from app.config import settings
    settings.sarvam_api_key      # None when unset, so callers can fall back to offline behaviour
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


def load_env(path: Path = ENV_FILE) -> None:
    """Read KEY=value lines into the environment without overwriting anything already set."""
    if not path.exists():
        return
    # PowerShell's `echo x >> .env` writes UTF-16 with a byte order mark, so the encoding of this
    # file cannot be assumed. Try the usual ones and give up quietly rather than crash at import.
    raw = path.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
        try:
            text = raw.decode(encoding)
            if "=" in text:
                break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if text is None:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    sarvam_api_key: Optional[str]
    sarvam_chat_model: str
    sarvam_base_url: str
    llm_provider: str
    llm_api_key: Optional[str]
    llm_model: str
    llm_base_url: str
    llm_no_retention_confirmed: bool
    bis_contact: Optional[str]

    @property
    def has_llm(self) -> bool:
        """Whether a language model is available. Every module must work without one."""
        return bool(self.llm_api_key)

    def describe(self) -> str:
        """Safe to print or log: says whether a key is present, never what it is."""
        return (f"LLM provider {self.llm_provider}, key {'present' if self.has_llm else 'absent'}, "
            f"model {self.llm_model}")


def _build() -> Settings:
    load_env()
    provider = os.environ.get("LLM_PROVIDER", "sarvam").strip().lower()
    defaults = {
        "sarvam": ("sarvam-105b-conversations", "https://api.sarvam.ai"),
        "openai": ("gpt-4o-mini", "https://api.openai.com/v1"),
        "gemini": ("gemini-2.5-flash", "https://generativelanguage.googleapis.com/v1beta/openai"),
        "groq": ("llama-3.3-70b-versatile", "https://api.groq.com/openai/v1"),
        "openrouter": ("openai/gpt-4o-mini", "https://openrouter.ai/api/v1"),
    }
    default_model, default_url = defaults.get(provider, defaults["sarvam"])
    sarvam_key = os.environ.get("SARVAM_API_KEY") or None
    return Settings(
        sarvam_api_key=sarvam_key,
        # sarvam-m was retired. Of the two replacements, measured on this project's prompts:
        # sarvam-105b reasons first and answers in 10 to 17 s, while sarvam-105b-conversations
        # answers the same extraction in 0.5 s. Latency matters more than depth for our prompts,
        # which only structure or phrase text that the pipeline has already established.
        sarvam_chat_model=os.environ.get("SARVAM_CHAT_MODEL", "sarvam-105b-conversations"),
        sarvam_base_url=os.environ.get("SARVAM_BASE_URL", "https://api.sarvam.ai"),
        llm_provider=provider,
        llm_api_key=(os.environ.get("LLM_API_KEY") or (sarvam_key if provider == "sarvam" else None)),
        llm_model=os.environ.get("LLM_MODEL", os.environ.get("SARVAM_CHAT_MODEL", default_model)),
        llm_base_url=os.environ.get("LLM_BASE_URL", os.environ.get("SARVAM_BASE_URL", default_url)),
        llm_no_retention_confirmed=os.environ.get("LLM_NO_RETENTION_CONFIRMED", "false").lower() == "true",
        bis_contact=os.environ.get("BIS_CONTACT") or None,
    )


settings = _build()
