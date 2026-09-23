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
    bis_contact: Optional[str]

    @property
    def has_llm(self) -> bool:
        """Whether a language model is available. Every module must work without one."""
        return bool(self.sarvam_api_key)

    def describe(self) -> str:
        """Safe to print or log: says whether a key is present, never what it is."""
        return (f"Sarvam key {'present' if self.has_llm else 'absent'}, "
                f"model {self.sarvam_chat_model}")


def _build() -> Settings:
    load_env()
    return Settings(
        sarvam_api_key=os.environ.get("SARVAM_API_KEY") or None,
        # sarvam-m was retired. Of the two replacements, measured on this project's prompts:
        # sarvam-105b reasons first and answers in 10 to 17 s, while sarvam-105b-conversations
        # answers the same extraction in 0.5 s. Latency matters more than depth for our prompts,
        # which only structure or phrase text that the pipeline has already established.
        sarvam_chat_model=os.environ.get("SARVAM_CHAT_MODEL", "sarvam-105b-conversations"),
        sarvam_base_url=os.environ.get("SARVAM_BASE_URL", "https://api.sarvam.ai"),
        bis_contact=os.environ.get("BIS_CONTACT") or None,
    )


settings = _build()
