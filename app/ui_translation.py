"""Translate the public interface dictionary through Google Cloud Translation."""

import html
import re
from pathlib import Path
from typing import Dict, List

import requests

from app.config import settings
from app.understand.language import BY_CODE, LanguageHandler

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "web" / "src" / "i18n" / "en.ts"
GOOGLE_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"
_CACHE: Dict[str, Dict[str, str]] = {}
_PAIR = re.compile(r"^\s*'([^']+)':\s*\n?\s*'((?:[^'\\]|\\.)*)'", re.MULTILINE)


class UITranslationUnavailable(RuntimeError):
    """Google translation is not configured or did not return a usable dictionary."""


def _english_dictionary() -> Dict[str, str]:
    source = SOURCE.read_text(encoding="utf-8")
    body = source.split("export const en = {", 1)[1]
    return {
        key: value.replace("\\'", "'").replace("\\\\", "\\")
        for key, value in _PAIR.findall(body)
        if key != "app.name"
    }


def _translate_batch(values: List[str], target: str, api_key: str) -> List[str]:
    try:
        response = requests.post(
            GOOGLE_TRANSLATE_URL,
            params={"key": api_key},
            json={"q": values, "source": "en", "target": target, "format": "text"},
            timeout=20,
        )
        response.raise_for_status()
        translations = response.json()["data"]["translations"]
        result = [html.unescape(item["translatedText"]) for item in translations]
    except (requests.RequestException, KeyError, TypeError, ValueError) as error:
        raise UITranslationUnavailable("Google Translate did not return a valid response") from error
    if len(result) != len(values):
        raise UITranslationUnavailable("Google Translate returned an incomplete response")
    return result


def translate_ui_dictionary(language: str) -> Dict[str, str]:
    """Return a translated dictionary, never sending the API key to the browser."""
    if language not in BY_CODE or language == "en":
        raise ValueError("Unsupported interface language")
    if not settings.google_translate_api_key:
        raise UITranslationUnavailable("Google Translate is not configured")
    if language in _CACHE:
        return _CACHE[language]

    english = _english_dictionary()
    keys = list(english)
    masked: List[str] = []
    protected: List[List[str]] = []
    placeholders: List[List[str]] = []
    for key in keys:
        value = english[key]
        found_placeholders: List[str] = []

        def protect_placeholder(match: re.Match[str]) -> str:
            found_placeholders.append(match.group(0))
            return f"__PLACEHOLDER_{len(found_placeholders) - 1}__"

        value = re.sub(r"\{[\w.]+\}", protect_placeholder, value)
        value, identifiers = LanguageHandler.protect(value)
        masked.append(value)
        protected.append(identifiers)
        placeholders.append(found_placeholders)

    target = "or" if language == "od" else language
    translated: List[str] = []
    for start in range(0, len(masked), 100):
        translated.extend(_translate_batch(masked[start:start + 100], target,
                                           settings.google_translate_api_key))

    dictionary: Dict[str, str] = {}
    for key, value, identifiers, found_placeholders in zip(keys, translated, protected, placeholders):
        restored = LanguageHandler.restore(value, identifiers)
        for index, placeholder in enumerate(found_placeholders):
            sentinel = f"__PLACEHOLDER_{index}__"
            if sentinel not in restored:
                raise UITranslationUnavailable("An interface interpolation token was not preserved")
            restored = restored.replace(sentinel, placeholder)
        if re.search(r"#\s*\d+\s*#", restored):
            raise UITranslationUnavailable("A protected interface identifier was not preserved")
        dictionary[key] = restored

    _CACHE[language] = dictionary
    return dictionary