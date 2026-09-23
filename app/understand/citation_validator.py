"""Module B4: Citation Validator, for scenario S2 — the tender already names standards.

Judges every standard the officer already cited on three separate questions: does it exist, is it
current, and is it actually relevant to this product. Most officials take their standards from a
senior or last year's tender, so the list is usually part right and part wrong, and saying precisely
which part is the most persuasive thing this system does.

Nothing here is new machinery: existence and currency come from C3, relevance from C1, and the
missing standards from what C1 and C2 recommended. That reuse is why the module is short.

One rule it never breaks: when relevance cannot be judged, because we hold no text for that
standard, the verdict is "verify" and `relevant` stays None. Absence of evidence is never reported
as evidence of irrelevance.

    from app.understand.citation_validator import CitationValidator
    CitationValidator().validate(["IS 8112:1989", "IS 456:2000"], query="43 grade OPC for RCC work")
"""

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.catalogue import parse_any_is  # noqa: E402
from app.core.retrieval import RetrievalEngine  # noqa: E402
from app.core.version_resolver import VersionResolver  # noqa: E402
from contracts.analysis import CitationStatus, Severity  # noqa: E402
from contracts.answer import CitationVerdict  # noqa: E402

RELEVANT_AT = 0.50      # cross-encoder probability above which a cited standard fits the product
CLEARLY_OFF = 0.10      # below this the standard is about something else


class CitationValidator:
    def __init__(self, resolver: Optional[VersionResolver] = None,
                 engine: Optional[RetrievalEngine] = None):
        self.resolver = resolver or VersionResolver()
        self.engine = engine          # optional: without it, relevance is simply not judged

    def validate(self, citations: List[str], query: str = "",
                 recommended: Optional[List[str]] = None) -> List[CitationVerdict]:
        """Judge each citation, then add the standards the tender should have cited but did not."""
        verdicts = [self._judge(c, query) for c in citations]

        cited_keys = {self._key(v.citation) for v in verdicts}
        cited_keys |= {self._key(v.replacement) for v in verdicts if v.replacement}
        for standard in recommended or []:
            if self._key(standard) in cited_keys:
                continue
            resolved = self.resolver.resolve(standard)
            verdicts.append(CitationVerdict(
                citation=standard, exists=resolved.exists,
                status=resolved.status.value, relevant=True, verdict="add",
                reason="Recommended for this product but not cited in the tender.",
                severity=Severity.MEDIUM, title=resolved.title))
        return verdicts

    # ---------------------------------------------------------------- internals

    def _judge(self, citation: str, query: str) -> CitationVerdict:
        resolved = self.resolver.resolve(citation)

        if not resolved.exists:
            return CitationVerdict(
                citation=citation, exists=False, status=CitationStatus.NOT_FOUND.value,
                relevant=None, verdict="remove",
                reason="This number does not appear in the BIS catalogue.",
                severity=Severity.HIGH)

        score = self._relevance(query, resolved.current or citation)
        relevant = None if score is None else score >= RELEVANT_AT

        if resolved.status is CitationStatus.SUPERSEDED and resolved.current:
            return CitationVerdict(
                citation=citation, exists=True, status=resolved.status.value,
                relevant=relevant, relevance_score=score, verdict="replace",
                replacement=resolved.current,
                reason=f"Withdrawn and replaced by {resolved.current}.",
                severity=Severity.HIGH, title=resolved.title)

        if resolved.status is CitationStatus.WITHDRAWN:
            return CitationVerdict(
                citation=citation, exists=True, status=resolved.status.value,
                relevant=relevant, relevance_score=score, verdict="remove",
                reason="Withdrawn, and BIS names no replacement.",
                severity=Severity.HIGH, title=resolved.title)

        if score is not None and score < CLEARLY_OFF:
            return CitationVerdict(
                citation=citation, exists=True, status=resolved.status.value,
                relevant=False, relevance_score=score, verdict="remove",
                reason=f"{resolved.current or citation} covers a different subject: "
                       f"{(resolved.title or '')[:70]}.",
                severity=Severity.MEDIUM, title=resolved.title)

        # A different edition of the same standard is a drift, not a defect. Two ways it shows up:
        # the cited edition exists but a later one is in force, or the cited year is not an edition
        # BIS ever published ("IS 1161:1998" when the editions are 2014 and earlier).
        cited_year = (parse_any_is(citation) or None)
        cited_year = cited_year.year if cited_year else None
        drift = bool(resolved.current) and (
            (resolved.cited_edition and resolved.current != resolved.cited_edition)
            or (resolved.cited_edition is None and cited_year is not None))
        if drift:
            return CitationVerdict(
                citation=citation, exists=True, status=resolved.status.value,
                relevant=relevant, relevance_score=score, verdict="replace",
                replacement=resolved.current,
                reason=f"A later edition is in force: {resolved.current}.",
                severity=Severity.MEDIUM, title=resolved.title)

        # Currency is settled; only relevance is unknown, and that is worth saying plainly.
        if score is None:
            return CitationVerdict(
                citation=citation, exists=True, status=resolved.status.value,
                relevant=None, verdict="verify",
                reason="Current, but we hold no text for it, so its relevance to this product "
                       "could not be checked.",
                severity=Severity.LOW, title=resolved.title)

        return CitationVerdict(
            citation=citation, exists=True, status=resolved.status.value,
            relevant=relevant, relevance_score=score, verdict="keep",
            reason="Current and relevant to this product.", severity=Severity.LOW,
            title=resolved.title)

    def _relevance(self, query: str, is_number: str) -> Optional[float]:
        """How well the cited standard answers the requirement, or None when we cannot tell."""
        if not (self.engine and query.strip()):
            return None
        score = self.engine.score(query, is_number)
        return round(float(score), 4) if score else None

    @staticmethod
    def _key(is_number: Optional[str]) -> str:
        return (is_number or "").replace(" ", "").upper()
