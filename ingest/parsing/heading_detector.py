"""Multi-Signal Heading Detection and False-Positive Rejection.

Combines numbering pattern regex, typography (font flags/size/capitalization),
and hierarchical sequence sanity checking. Prevents false headings from
table rows or requirement numbers (e.g. '43 grade OPC' or '28 days strength').
"""

import re
from typing import Optional, Tuple, List


# Numbers that commonly represent specifications, grades, or durations, NOT clause numbers
REJECT_PREFIX_PATTERNS = [
    re.compile(r"^\d+\s*(?:grade|days?|hours?|minutes?|min|percent|%|mm|cm|m|kg|MPa|N/mm2|°C|deg|kN|sieve)\b", re.IGNORECASE),
    re.compile(r"^\d+\s*(?:to|-)\s*\d+\b", re.IGNORECASE), # ranges like "10 to 20 mm"
    re.compile(r"^\([a-z0-9ivxlcdm]+\)", re.IGNORECASE), # sub-item lists like "(a)", "(i)"
]


class HeadingCandidate:
    def __init__(self, clause_num: str, title: str, raw_line: str, is_bold: bool, font_size: float, page_num: int):
        self.clause_num = clause_num
        self.title = title.strip()
        self.raw_line = raw_line.strip()
        self.is_bold = is_bold
        self.font_size = font_size
        self.page_num = page_num

    def __repr__(self):
        return f"<Heading {self.clause_num}: '{self.title}' (p.{self.page_num})>"


def is_sequence_valid(prev_num: Optional[str], cur_num: str) -> bool:
    """Validate hierarchical sequence sanity between consecutive clauses.

    Enforces logical tree progression:
      None -> '0', '1', 'FOREWORD', 'ANNEX A'
      '1'  -> '1.1' or '2'
      '4'  -> '4.1' or '5'
      '4.1'-> '4.2' or '4.1.1' or '5'
      '4.2.3' -> '4.2.4' or '4.3' or '5'
    Rejects erratic leaps (e.g. '1' -> '43').
    """
    if cur_num.startswith(("ANNEX", "APPENDIX", "FOREWORD")):
        return True

    if prev_num is None:
        # Starting clause must be 0, 1, or foreword
        return cur_num in ("0", "1", "1.0")

    if prev_num.startswith(("ANNEX", "APPENDIX")):
        # In annexes, allow sub-clauses like A-1, B-1 or annex boundaries
        return True

    # Parse numeric parts
    try:
        prev_parts = [int(p) for p in prev_num.split(".")]
        cur_parts = [int(p) for p in cur_num.split(".")]
    except ValueError:
        return False

    # 1. Direct child: e.g. 4 -> 4.1, 4.1 -> 4.1.1
    if len(cur_parts) == len(prev_parts) + 1:
        if cur_parts[:-1] == prev_parts and cur_parts[-1] == 1:
            return True

    # 2. Sibling or pop-back to ancestor:
    # e.g. 4.1 -> 4.2
    # e.g. 4.2.1 -> 4.3 or 5
    for k in range(min(len(prev_parts), len(cur_parts)), 0, -1):
        if len(cur_parts) == k and cur_parts[:k-1] == prev_parts[:k-1] and cur_parts[k-1] == prev_parts[k-1] + 1:
            return True

    # Allow occasional skipped sub-clause (e.g. 4.1 -> 4.3 if BIS omitted 4.2) within 1-2 steps
    if len(cur_parts) == len(prev_parts) and cur_parts[:-1] == prev_parts[:-1]:
        diff = cur_parts[-1] - prev_parts[-1]
        if 1 <= diff <= 2:
            return True

    # Allow top-level increment even if prior sub-clause was deep (e.g. 4.3.2 -> 5)
    if len(cur_parts) == 1 and len(prev_parts) > 1:
        if cur_parts[0] == prev_parts[0] + 1:
            return True

    return False


def detect_heading_line(line_text: str, is_bold: bool, font_size: float, page_num: int, next_line_text: str = "") -> Optional[Tuple[str, str]]:
    """Test whether a line (or line + next_line) matches heading syntax and typographic requirements.

    Returns (clause_num, title) or None if rejected.
    """
    text = line_text.strip()
    if not text:
        return None

    # Gate 1: Check false-positive rejection patterns
    for pat in REJECT_PREFIX_PATTERNS:
        if pat.search(text):
            return None

    # Gate 2: Pattern matching
    # Annexes
    m_annex = re.match(r"^(ANNEX\s+[A-Z]|APPENDIX\s+[A-Z])(?:\s+([^\n]+))?$", text, re.IGNORECASE)
    if m_annex:
        return m_annex.group(1).upper(), (m_annex.group(2) or "").strip()

    # Foreword
    m_fore = re.match(r"^(FOREWORD|PREFACE)\b(?:\s*—?\s*(.*))?$", text, re.IGNORECASE)
    if m_fore:
        return "0", m_fore.group(1).title() + (f" - {m_fore.group(2)}" if m_fore.group(2) else "")

    # Standard numbered clauses: "1.", "1.1", "2. Chemical Requirements — ..."
    m_num = re.match(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s*(.*)$", text)
    if not m_num:
        return None

    clause_num = m_num.group(1)
    remainder = m_num.group(2).strip()

    # If remainder is empty, look at next_line_text
    consumed_next_line = False
    if not remainder and next_line_text:
        next_clean = next_line_text.strip()
        # Ensure next line isn't another numbered clause or table
        if not re.match(r"^\d{1,2}\.", next_clean) and not next_clean.startswith("|"):
            remainder = next_clean
            consumed_next_line = True

    # Gate 3: Reject false positives in remainder
    if remainder and remainder[0].islower():
        return None
    if remainder.startswith((")", "]", "/", ":")):
        return None

    # Gate 4: Typography
    has_caps = remainder.isupper() if remainder else False
    if not is_bold and not has_caps and font_size < 10.5 and not consumed_next_line:
        return None

    # Clean up em-dash or separator in remainder
    remainder = re.sub(r"^[\—\-\:\.\s]+", "", remainder).strip()
    
    # Extract title if followed by em-dash or separator
    title_match = re.match(r"^([A-Za-z0-9 ,/&()’'-]{2,60}?)(?:[\—\-\:]|\s{2,}|\.\s+)(.*)$", remainder)
    if title_match:
        title = title_match.group(1).strip()
    else:
        words = remainder.split()
        if len(words) <= 6:
            title = remainder
        else:
            title = " ".join(words[:4])

    return clause_num, title

