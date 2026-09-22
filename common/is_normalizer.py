"""Common Indian Standards Number Normalization Utility.

Reusable utility across Standards360 (A2, A3, C3) for canonicalizing IS numbers,
handling Part notations, Roman numerals, and extracting {family, part, year}.
"""

import re
from dataclasses import dataclass
from typing import Optional, Dict

ROMAN_NUMERALS: Dict[str, str] = {
    "I": "1",
    "II": "2",
    "III": "3",
    "IV": "4",
    "V": "5",
    "VI": "6",
    "VII": "7",
    "VIII": "8",
    "IX": "9",
    "X": "10",
    "XI": "11",
    "XII": "12",
    "XIII": "13",
    "XIV": "14",
    "XV": "15",
}


@dataclass(frozen=True)
class NormalizedIS:
    raw: str
    canonical: str        # e.g. 'IS 269:2015' or 'IS 10124 (Part 1):1988'
    family: str           # e.g. 'IS 269' or 'IS 10124 (Part 1)'
    base_number: str      # e.g. '269' or '10124'
    part: Optional[str]   # e.g. '1', '2' or None
    year: Optional[int]   # e.g. 2015 or None (unspecified)


def roman_to_arabic_part(part_str: str) -> str:
    """Convert Roman numeral part (e.g. 'II' or 'Part II') to Arabic ('2' or 'Part 2')."""
    if not part_str:
        return ""
    p = part_str.strip().upper()
    return ROMAN_NUMERALS.get(p, part_str.strip())


def normalize_part_string(part_raw: str) -> str:
    """Normalize arbitrary part/section strings to clean standard format."""
    p = part_raw.strip()
    # Check if purely roman numerals
    if p.upper() in ROMAN_NUMERALS:
        return ROMAN_NUMERALS[p.upper()]
    # Check if prefixed with Part or Sec
    m = re.match(r"^(?:Part|Sec|Section)?\s*([A-Za-z0-9/]+)$", p, re.I)
    if m:
        val = m.group(1).upper()
        if val in ROMAN_NUMERALS:
            return ROMAN_NUMERALS[val]
        return m.group(1)
    return p


def parse_is_number(text: str) -> Optional[NormalizedIS]:
    """Parse any Indian Standard identifier into a canonical NormalizedIS object.

    Handles:
      'IS 269' -> family='IS 269', part=None, year=None
      'IS 269:2015' -> family='IS 269', part=None, year=2015
      'IS-269' -> family='IS 269'
      'I.S. 269' -> family='IS 269'
      'IS 10124 (Part 1)' -> family='IS 10124 (Part 1)', part='1'
      'IS 10124 (Part II):1988' -> family='IS 10124 (Part 2)', part='2', year=1988
    """
    if not text:
        return None

    # Clean leading/trailing noise
    s = text.strip()
    
    # Regex matching variations of IS prefix, number, part, and year
    pattern = re.compile(
        r"(?:(?:I\.?\s*S\.?|IS)\s*[:\s\-]?\s*)(\d{3,5})"
        r"(?:\s*[\(/]\s*(?:Part|Sec|Section)?\s*([A-Za-z0-9/\s]+)[\)/])?"
        r"(?:\s*[:\-]\s*(\d{4}))?",
        re.IGNORECASE
    )

    m = pattern.search(s)
    if not m:
        return None

    base_num = m.group(1)
    raw_part = m.group(2)
    raw_year = m.group(3)

    part = normalize_part_string(raw_part) if raw_part else None
    year = int(raw_year) if raw_year else None

    # Construct clean family
    if part:
        family = f"IS {base_num} (Part {part})"
    else:
        family = f"IS {base_num}"

    # Construct canonical representation
    if year:
        canonical = f"{family}:{year}"
    else:
        canonical = family

    return NormalizedIS(
        raw=s,
        canonical=canonical,
        family=family,
        base_number=base_num,
        part=part,
        year=year,
    )


def norm_is_lookup_key(text: str) -> str:
    """Create a punctuation-agnostic uppercase key for dictionary matching.

    Normalizes Roman numerals to Arabic so 'Part II' matches 'Part 2'.
    """
    s = text.upper()
    # Normalize Roman numerals in Part
    for roman, arabic in ROMAN_NUMERALS.items():
        s = re.sub(rf"\(PART\s*{roman}\)", f"PART{arabic}", s)
        s = re.sub(rf"PART\s*{roman}\b", f"PART{arabic}", s)
    s = re.sub(r"\(PART\s*(\w+)\)", r"PART\1", s)
    s = re.sub(r"[\s\(\)\:\-_/.]", "", s)
    return s


def is_same_standard_family(is_a: str, is_b: str) -> bool:
    """Check if two identifiers share the exact base standard family (ignoring part/year)."""
    norm_a = parse_is_number(is_a)
    norm_b = parse_is_number(is_b)
    if not norm_a or not norm_b:
        return False
    return norm_a.base_number == norm_b.base_number

