"""Module D1: Validity Guard.

The last gate before any generated sentence reaches a user or a PDF. Every Indian Standard number
appearing in generated prose is checked against the catalogue, and anything that cannot be verified
is removed rather than softened.

Two points from the manual that shape the implementation:

* It inspects generated prose only. The recommended standards themselves come from database rows,
  so by construction they cannot be invented; the one component able to produce a fictitious number
  is the language model that writes the explanation.
* It validates against the whole catalogue of 35,553 records, not against the smaller set whose text
  we hold. A real standard outside our two sectors still exists and must not be deleted.

    from app.deliver.validity_guard import ValidityGuard
    ValidityGuard().check("Refer IS 269:2015 and also IS 99999:2021 for testing.")
"""

import re
import sys
from pathlib import Path
from typing import Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.catalogue import Catalogue, parse_any_is  # noqa: E402
from common.is_normalizer import norm_is_lookup_key  # noqa: E402
from contracts.analysis import GuardResult  # noqa: E402

# Any IS citation as it appears in prose, including parts, sections and a year.
CITATION = re.compile(
    r"\bIS\s*[:\s\-]?\s*\d{2,10}"       # a longer digit run is captured on purpose, so that a
    r"(?:\s*\(\s*(?:Part|Sec|Section)[^)]*\))?"   # fabricated number such as 'IS 12345678' is seen
    r"(?:\s*[:\-]\s*\d{4})?",                     # whole and rejected, not silently truncated
    re.IGNORECASE,
)
MAX_DIGITS = 5  # BIS numbers run to five digits; anything longer is not a standard number.
# Leftovers after a citation is cut out of a sentence: ' and also ,' or ' , and '.
TIDY = [
    (re.compile(r"\s*,?\s*(?:and|or)\s+also\s*(?=[.,;:]|$)", re.I), ""),
    (re.compile(r"\s*,?\s+(?:and|or)\s*(?=[.,;:]|$)", re.I), ""),
    (re.compile(r"\s+,"), ","),
    (re.compile(r",\s*(?=[.;:])"), ""),
    (re.compile(r"\(\s*\)"), ""),
    (re.compile(r"\s{2,}"), " "),
    (re.compile(r"\s+([.,;:])"), r"\1"),
]


class ValidityGuard:
    def __init__(self, catalogue: Optional[Catalogue] = None):
        self.cat = catalogue or Catalogue.shared()

    def check(self, text: str, allowed: Optional[Iterable[str]] = None) -> GuardResult:
        """Remove every standard number that is not verifiable.

        `allowed` is the explicit list of numbers the generator was permitted to mention. When it is
        given, a number outside it is removed even if it exists, because the generator has then
        reached for a standard the pipeline did not retrieve.
        """
        if not text:
            return GuardResult(text="", removed=[], reasons={}, clean=True)

        allowed_keys = None
        if allowed is not None:
            allowed_keys = set()
            for item in allowed:
                parsed = parse_any_is(item)
                if parsed:
                    allowed_keys.add(norm_is_lookup_key(parsed.family))
                    allowed_keys.add(norm_is_lookup_key(parsed.canonical))

        removed, reasons = [], {}
        for citation in {m.group(0) for m in CITATION.finditer(text)}:
            reason = self._reject_reason(citation, allowed_keys)
            if reason:
                removed.append(citation.strip())
                reasons[citation.strip()] = reason

        cleaned = text
        for citation in sorted(removed, key=len, reverse=True):
            cleaned = self._cut(cleaned, citation)
        for pattern, replacement in TIDY:
            cleaned = pattern.sub(replacement, cleaned)

        return GuardResult(text=cleaned.strip(), removed=sorted(removed), reasons=reasons,
                           clean=not removed)

    @staticmethod
    def _cut(text: str, citation: str) -> str:
        """Remove a citation together with the words that joined it to the sentence.

        Cutting the number alone would leave 'Refer IS 269:2015 and also for testing.', so the
        conjunction or comma that introduced it goes with it.
        """
        cit = re.escape(citation)
        patterns = [
            rf",?\s*(?:and|or)\s+(?:also\s+)?{cit}",   # '... and also IS 99999:2021'
            rf"{cit}\s*,?\s*(?:and|or)\s+(?:also\s+)?",  # first item of a list
            rf"\s*,\s*{cit}",                           # '..., IS 99999:2021'
            rf"\s*{cit}",
        ]
        for pattern in patterns:
            new = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE)
            if new != text:
                return new
        return text

    def _reject_reason(self, citation: str, allowed_keys) -> Optional[str]:
        digits = re.search(r"\d+", citation)
        if digits and len(digits.group(0)) > MAX_DIGITS:
            return "not a readable standard number"
        parsed = parse_any_is(citation)
        if not parsed:
            return "not a readable standard number"
        if not self.cat.exists(citation):
            return "not in catalogue"
        if allowed_keys is not None:
            keys = {norm_is_lookup_key(parsed.family), norm_is_lookup_key(parsed.canonical)}
            if not (keys & allowed_keys):
                return "not among the standards this answer retrieved"
        return None
