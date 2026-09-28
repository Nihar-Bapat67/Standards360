"""Module B2: Language Handler.

Detects the language a request arrived in, translates it to English before retrieval, and puts the
answer back into the language the person is reading. The engine itself stays English-only: the
clause index, the BM25 titles and the cross-encoder are all English, so translating at the edges is
both cheaper and more accurate than making every stage multilingual.

**The rule that governs this module.** A standard's identifier must survive translation unchanged.
Left to itself the translator transliterates them — "IS 269:2015" comes back as "आई.एस. 269:2015" in
Hindi, "ஐஎஸ் 269:2015" in Tamil, and BIS becomes "बी.आई.एस." — and a citation written that way cannot
be pasted into a tender or looked up in the catalogue. So every identifier is masked with a numeric
placeholder before the text is sent and restored afterwards. Placeholders were tested against Hindi,
Tamil and Bengali and pass through untouched.

Authoritative BIS text is never translated at all. A quoted clause stays in the language BIS
published it in, and only the explanation around it is translated.

    from app.understand.language import LanguageHandler
    handler = LanguageHandler()
    handler.detect("स्टील ट्यूब")                      -> "hi"
    handler.to_english("स्टील ट्यूब")                  -> ("Steel tube", "hi")
    handler.from_english("Steel tubes apply.", "hi")  -> "स्टील ट्यूब लागू होते हैं।"
"""

import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.config import settings  # noqa: E402

TIMEOUT = 30
# mayura:v1 accepts 1000 characters per call, so longer text is split on sentence boundaries.
MAX_CHARS = 900


@dataclass(frozen=True)
class Language:
    code: str          # what the interface and the API use
    sarvam: str        # what Sarvam's endpoints expect
    english: str
    native: str
    script: Optional[str]   # the Unicode block that identifies it, for offline detection
    # mayura:v1 is the better translator but covers eleven of our twelve; Assamese is rejected with
    # a 400 and has to go through sarvam-translate:v1. Tested per language, not assumed.
    model: str = "mayura:v1"


# The twelve languages the product supports. Odia is `od-IN` at Sarvam, not the `or` of ISO 639-1,
# which is a real trap: `or-IN` is rejected with a 400.
LANGUAGES: Tuple[Language, ...] = (
    Language("en", "en-IN", "English", "English", None),
    Language("hi", "hi-IN", "Hindi", "हिन्दी", "DEVANAGARI"),
    Language("mr", "mr-IN", "Marathi", "मराठी", "DEVANAGARI"),
    Language("gu", "gu-IN", "Gujarati", "ગુજરાતી", "GUJARATI"),
    Language("bn", "bn-IN", "Bengali", "বাংলা", "BENGALI"),
    Language("ta", "ta-IN", "Tamil", "தமிழ்", "TAMIL"),
    Language("te", "te-IN", "Telugu", "తెలుగు", "TELUGU"),
    Language("kn", "kn-IN", "Kannada", "ಕನ್ನಡ", "KANNADA"),
    Language("ml", "ml-IN", "Malayalam", "മലയാളം", "MALAYALAM"),
    Language("pa", "pa-IN", "Punjabi", "ਪੰਜਾਬੀ", "GURMUKHI"),
    Language("od", "od-IN", "Odia", "ଓଡ଼ିଆ", "ORIYA"),
    Language("as", "as-IN", "Assamese", "অসমীয়া", "BENGALI", "sarvam-translate:v1"),
)

BY_CODE: Dict[str, Language] = {lang.code: lang for lang in LANGUAGES}
BY_SARVAM: Dict[str, Language] = {lang.sarvam: lang for lang in LANGUAGES}

# Unicode ranges, used when no API key is configured so the product still works offline. Devanagari
# carries both Hindi and Marathi and Bengali script carries both Bengali and Assamese, so those
# collapse to the more common member; the API distinguishes them properly when it is available.
SCRIPT_RANGES: Tuple[Tuple[int, int, str], ...] = (
    (0x0900, 0x097F, "hi"),
    (0x0A00, 0x0A7F, "pa"),
    (0x0A80, 0x0AFF, "gu"),
    (0x0980, 0x09FF, "bn"),
    (0x0B00, 0x0B7F, "od"),
    (0x0B80, 0x0BFF, "ta"),
    (0x0C00, 0x0C7F, "te"),
    (0x0C80, 0x0CFF, "kn"),
    (0x0D00, 0x0D7F, "ml"),
)

# What must never be translated or transliterated.
#
#   IS 1786, IS 4031 (Part 1):1996, IS/IEC 60947-1, IS/ISO 9001, SP 21
#   BIS, QCO, ISI, CRS, ISO, IEC, BS, EN, ASTM, DIN
#
# The IS pattern is deliberately greedy about the part and year so the whole citation travels as one
# unit; splitting it would let the translator reorder the pieces.
PROTECTED = re.compile(
    r"""(
        \b(?:IS|SP)\s*/\s*(?:IEC|ISO|TS|TR)\s*\d[\d\-]*(?:\s*\(\s*Part\s*[\dIVX]+\s*\))?(?:\s*:\s*\d{4})?
      | \b(?:IS|SP)\s*\d{1,5}(?:\s*\(\s*(?:Part|Sec|Section)\s*[\dIVX]+\s*\))?(?:\s*:\s*\d{4})?
      | \b(?:ISO|IEC|ASTM|DIN|BS|EN)\s*\d(?:[\d\-.]*\d)?
      | \b(?:BIS|QCO|ISI|CRS|RCC|PVC|uPVC|CPVC|HDPE|TMT|OPC|PPC|GeM|CPPP)\b
    )""",
    re.VERBOSE | re.IGNORECASE,
)


# Domain phrases a general translator reads in the wrong sense. "Allied standards" came back from
# Hindi as "मित्र देशों के मानक" — the standards of allied *nations* — because the military reading of
# "allied" is the commoner one. Rewriting to an unambiguous synonym before translating costs nothing
# and fixes it in every target language at once. These are prose substitutions only; identifiers are
# handled by the mask above and never appear here.
GLOSSARY: Tuple[Tuple[str, str], ...] = (
    (r"allied standards", "associated standards"),
    (r"allied standard", "associated standard"),
    (r"standard mark", "certification mark"),
    (r"citation depth", "level of citation detail"),
    # "Find the standard" on its own is ambiguous, and translators read "standard" as an adjective
    # or as "standard text": it came back as "usual" in Tamil and "acceptable text" in Bengali.
    # Naming what kind of standard it is fixes the phrase in every target language at once.
    (r"find the standard", "find the applicable Indian Standard"),
    (r"the standard that applies", "the Indian Standard that applies"),
)


class TranslationUnavailable(RuntimeError):
    """Raised inside the module and always handled; callers get the original text instead."""


class LanguageHandler:
    """Detection and translation, with the identifier guard built in.

    Every method degrades rather than fails. Without an API key `detect` falls back to the script
    heuristic and the translate methods return their input unchanged, which is why a request in
    Hindi still produces an answer offline — just an English one.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key if api_key is not None else settings.sarvam_api_key
        self.base_url = (base_url or settings.sarvam_base_url).rstrip("/")
        self.last_error: Optional[str] = None

    @property
    def available(self) -> bool:
        return bool(self.api_key and settings.llm_no_retention_confirmed)

    # ---------------------------------------------------------------- identifiers

    @staticmethod
    def protect(text: str) -> Tuple[str, List[str]]:
        """Replace every identifier with a placeholder the translator leaves alone."""
        found: List[str] = []

        def swap(match: "re.Match[str]") -> str:
            found.append(match.group(0))
            return f"#{len(found) - 1}#"

        return PROTECTED.sub(swap, text), found

    @staticmethod
    def restore(text: str, found: List[str]) -> str:
        """Put the identifiers back, exactly as they were written."""
        for index, original in enumerate(found):
            # The translator occasionally pads a placeholder with spaces or native digits; accept
            # either form rather than leaving "#3#" visible to the reader.
            text = re.sub(rf"#\s*{index}\s*#", original.replace("\\", r"\\"), text)
        return text

    # ---------------------------------------------------------------- detection

    def detect(self, text: str) -> str:
        """The language code of `text`, defaulting to English.

        Latin-script input short-circuits without a network call, which covers the common case for
        nothing.
        """
        stripped = (text or "").strip()
        if not stripped:
            return "en"

        script_guess = self._by_script(stripped)
        if script_guess == "en":
            return "en"

        if self.available:
            identified = self._identify(stripped[:400])
            if identified:
                return identified
        return script_guess

    @staticmethod
    def _by_script(text: str) -> str:
        counts: Dict[str, int] = {}
        for character in text:
            point = ord(character)
            for low, high, code in SCRIPT_RANGES:
                if low <= point <= high:
                    counts[code] = counts.get(code, 0) + 1
                    break
        if not counts:
            return "en"
        return max(counts, key=lambda code: counts[code])

    def _identify(self, text: str) -> Optional[str]:
        try:
            response = requests.post(
                f"{self.base_url}/text-lid",
                headers={"api-subscription-key": self.api_key, "Content-Type": "application/json"},
                json={"input": text},
                timeout=TIMEOUT,
            )
            if not response.ok:
                self.last_error = f"text-lid HTTP {response.status_code}"
                return None
            code = response.json().get("language_code")
            language = BY_SARVAM.get(code or "")
            return language.code if language else None
        except requests.RequestException as error:
            self.last_error = f"text-lid {type(error).__name__}"
            return None

    # ---------------------------------------------------------------- translation

    def to_english(self, text: str, source: Optional[str] = None) -> Tuple[str, str]:
        """Translate into English for retrieval. Returns the English text and the source language."""
        language = source or self.detect(text)
        if language == "en" or not text.strip():
            return text, "en"
        translated = self._translate(text, BY_CODE[language].sarvam, "en-IN")
        return (translated or text), language

    def from_english(self, text: str, target: str) -> str:
        """Translate an answer into the reader's language, leaving identifiers alone."""
        if target == "en" or target not in BY_CODE or not (text or "").strip():
            return text
        return self._translate(text, "en-IN", BY_CODE[target].sarvam) or text

    def from_english_many(self, texts: List[str], target: str) -> List[str]:
        """Translate several short strings at once.

        A finished answer has an explanation, a certification statement, some warnings and a couple
        of questions to translate. Done one after another that is several seconds; the calls are
        independent, so they go out together.
        """
        if target == "en" or target not in BY_CODE:
            return texts
        if not texts:
            return []
        with ThreadPoolExecutor(max_workers=min(8, len(texts))) as pool:
            return list(pool.map(lambda text: self.from_english(text, target), texts))

    # ---------------------------------------------------------------- internals

    def _translate(self, text: str, source: str, target: str) -> Optional[str]:
        if not self.available:
            self.last_error = "no api key configured"
            return None

        for pattern, replacement in GLOSSARY:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        masked, found = self.protect(text)
        pieces = self._split(masked)
        model = (BY_SARVAM.get(target) or BY_SARVAM.get(source) or LANGUAGES[0]).model
        try:
            translated = "".join(self._call(piece, source, target, model) for piece in pieces)
        except TranslationUnavailable:
            return None

        restored = self.restore(translated, found)

        # 3. The translator sometimes drops a whole phrase, and with it a placeholder. Losing "BIS"
        # from a sentence is cosmetic, but losing a standard's number would leave the reader with an
        # explanation that no longer says which standard it is about. When that happens the English
        # text is returned instead, which is honest and still correct.
        lost = [original for index, original in enumerate(found)
                if f"#{index}#" in translated and original not in restored]
        dropped = [original for index, original in enumerate(found) if f"#{index}#" not in translated]
        if any(re.match(r"(?i)(?:IS|SP)", item) for item in dropped + lost):
            self.last_error = f"translation dropped an identifier: {dropped + lost}"
            return None
        return restored

    def _call(self, text: str, source: str, target: str, model: str) -> str:
        """One translation call, retried twice.

        Sending a whole dictionary at once earns a 429, and a single rejected call would otherwise
        leave that string in English for good. Two retries with a widening pause recover nearly all
        of them; anything still failing falls back rather than blocking.
        """
        payload = {
            "input": text,
            "source_language_code": source,
            "target_language_code": target,
            "model": model,
            "mode": "formal",
            # Native numerals would turn "43 grade" into a form nobody can match against a
            # standard, so the digits stay international.
            "numerals_format": "international",
        }
        headers = {"api-subscription-key": self.api_key, "Content-Type": "application/json"}

        for attempt in range(3):
            try:
                response = requests.post(f"{self.base_url}/translate", headers=headers,
                                         json=payload, timeout=TIMEOUT)
            except requests.RequestException as error:
                self.last_error = f"translate {type(error).__name__}"
                if attempt == 2:
                    raise TranslationUnavailable from error
                time.sleep(1.5 * (attempt + 1))
                continue

            if response.ok:
                return response.json().get("translated_text", "")

            self.last_error = f"translate HTTP {response.status_code}: {response.text[:120]}"
            # A 4xx that is not throttling will not improve on a retry.
            if response.status_code not in (429, 500, 502, 503, 504):
                raise TranslationUnavailable
            if attempt == 2:
                raise TranslationUnavailable
            time.sleep(1.5 * (attempt + 1))

        raise TranslationUnavailable

    @staticmethod
    def _split(text: str) -> List[str]:
        """Break text into pieces the translator will accept, preferring sentence boundaries."""
        if len(text) <= MAX_CHARS:
            return [text]

        pieces: List[str] = []
        current = ""
        for sentence in re.split(r"(?<=[.!?।])\s+", text):
            if len(current) + len(sentence) + 1 > MAX_CHARS and current:
                pieces.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip() if current else sentence
        if current:
            pieces.append(current)

        # A single sentence longer than the limit still has to go somewhere.
        final: List[str] = []
        for piece in pieces:
            while len(piece) > MAX_CHARS:
                final.append(piece[:MAX_CHARS])
                piece = piece[MAX_CHARS:]
            if piece:
                final.append(piece)
        return [f"{piece} " for piece in final[:-1]] + final[-1:] if len(final) > 1 else final


def supported() -> List[Dict[str, str]]:
    """The language list the interface renders in its selector."""
    return [
        {"code": lang.code, "english": lang.english, "native": lang.native, "sarvam": lang.sarvam}
        for lang in LANGUAGES
    ]
