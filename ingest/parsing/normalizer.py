"""Text and IS Identifier Normalization Utilities.

Implements strict Unicode NFC normalization, explicit ligature replacement,
line-end dehyphenation, and canonical Indian Standard number matching.
"""

import re
import unicodedata
from typing import Tuple, Optional


LIGATURE_MAP = {
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb00": "ff",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\u2019": "'",
    "\u2018": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "—",  # keep em-dash as NFC
}


def normalize_unicode_text(text: str) -> str:
    """Normalize text using Unicode NFC, expanding ligatures and preserving units.

    Never use NFKC: NFKC turns 'm²' into 'm2' and 'SO₃' into 'SO3',
    corrupting SI units and chemical formulas required by procurement specs.
    """
    if not text:
        return ""
    
    # Explicit ligature and special quotes expansion
    for char, repl in LIGATURE_MAP.items():
        text = text.replace(char, repl)
    
    # Normalize strictly to NFC
    text = unicodedata.normalize("NFC", text)
    # Strip Private Use Area characters (e.g. font icon bullets)
    text = re.sub(r"[\ue000-\uf8ff]", "", text)
    return text


def dehyphenate_text(text: str) -> str:
    """Rejoin words split across line breaks with a hyphen (e.g. 'struc-' \\n 'tural' -> 'structural').

    Leaves genuine compound words intact when followed by uppercase or punctuation.
    """
    # Pattern: word ending in hyphen, newline, lowercase letters
    # Example: "produc-\ntion" -> "production"
    dehyphenated = re.sub(r"([A-Za-z]{2,})-\s*\n\s*([a-z]{2,})", r"\1\2", text)
    
    # Rejoin lines within paragraphs that do not end in terminal punctuation
    lines = dehyphenated.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            cleaned_lines.append(stripped)
        else:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("") # paragraph break
    
    # Rejoin wrapped lines with spaces unless there's a paragraph break
    result = []
    current_para = []
    for line in cleaned_lines:
        if line == "":
            if current_para:
                result.append(" ".join(current_para))
                current_para = []
        else:
            current_para.append(line)
    if current_para:
        result.append(" ".join(current_para))
    
    return "\n\n".join(result)


def canonicalize_is_number(raw: str) -> str:
    """Create a standardized IS number string (e.g. 'IS 269:2015')."""
    raw = raw.strip()
    # Normalize spaces around colons and parens
    raw = re.sub(r"\s*:\s*", ":", raw)
    raw = re.sub(r"\s*\(", " (", raw)
    raw = re.sub(r"\)\s*", ") ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def parse_is_identifier(text: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """Extract (canonical_is, family, year) from a standard title or heading banner.

    Example inputs:
      'IS 269 : 1989 ORDINARY PORTLAND CEMENT' -> ('IS 269:1989', 'IS 269', 1989)
      'IS 1489 (PART 1) : 1991 PORTLAND...' -> ('IS 1489 (Part 1):1991', 'IS 1489 (Part 1)', 1991)
    """
    # Pattern for IS number with word boundary on IS so 'BIS' is not matched
    pattern = re.compile(
        r"(?:SUMMARY\s+OF\s+)?(?:\bIS\b\s*[:\s]?\s*(\d+(?:\s*\([^\)]+\))?))(?:\s*[:\-]\s*(\d{4}))?",
        re.IGNORECASE
    )
    m = pattern.search(text)
    if not m:
        return None, None, None

    num_part = m.group(1).strip()
    raw_family = f"IS {num_part}"
    
    # Normalize Part notation
    raw_family = re.sub(r"\(PART\s*(\w+)\)", lambda match: f"(Part {match.group(1).upper()})", raw_family, flags=re.IGNORECASE)
    raw_family = re.sub(r"\(PART\s*(\w+)\s+AND\s+(\w+)\)", lambda match: f"(Part {match.group(1).upper()} and {match.group(2).upper()})", raw_family, flags=re.IGNORECASE)
    raw_family = re.sub(r"\s+", " ", raw_family).strip()

    year_str = m.group(2)
    year = int(year_str) if year_str else None

    if year:
        canonical = f"{raw_family}:{year}"
    else:
        canonical = raw_family

    return canonical, raw_family, year


def is_lookup_key(s: str) -> str:
    """Create a punctuation-agnostic key for robust dictionary matching."""
    s = s.upper()
    s = re.sub(r"\(PART\s*(\w+)\)", r"PART\1", s)
    s = re.sub(r"[\s\(\)\:\-_/.]", "", s)
    return s
