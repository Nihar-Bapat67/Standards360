"""Module C3: Version and Amendment Resolver.

Answers one question for every standard the tender cites and every standard we recommend: is this
the edition in force today, and if not, what replaced it. There is no machine learning here, only
catalogue lookups and date comparisons, which is why it can be relied on inside a tender document.

    from app.core.version_resolver import VersionResolver
    VersionResolver().resolve("IS 8112:1989")
"""

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.catalogue import Catalogue, parse_any_is  # noqa: E402
from contracts.analysis import (  # noqa: E402
    CitationStatus,
    ResolvedStandard,
    Severity,
    VersionWarning,
)

MAX_HOPS = 6  # BIS data contains loops; a chain longer than this is a data fault, not a chain.


class VersionResolver:
    def __init__(self, catalogue: Optional[Catalogue] = None):
        self.cat = catalogue or Catalogue.shared()

    # ---------------------------------------------------------------- public

    def resolve(self, citation: str) -> ResolvedStandard:
        """Resolve one identifier, in any of the forms tenders use, to the edition in force."""
        parsed = parse_any_is(citation)
        if not parsed:
            return ResolvedStandard(
                cited=citation, status=CitationStatus.NOT_FOUND, exists=False,
                warnings=[VersionWarning(severity=Severity.HIGH, cited=citation,
                                         message=f"'{citation}' is not a recognisable Indian Standard number.",
                                         action="Check the number against the BIS portal.")])

        editions = self.cat.family(parsed)
        parts_only = False
        if not editions:
            # A tender writes 'IS 1239:2004' for a standard BIS publishes as 'IS 1239 (Part 1):2004'.
            # Fall back to the same number in its parts rather than declaring the citation unknown.
            editions = self.cat.same_number(parsed)
            parts_only = bool(editions)
            if parts_only and parsed.year is not None:
                dated = [r for r in editions if self.cat.year_of(r) == parsed.year]
                editions = dated or editions

        if not editions:
            return ResolvedStandard(
                cited=citation, status=CitationStatus.NOT_FOUND, exists=False,
                warnings=[VersionWarning(severity=Severity.HIGH, cited=citation,
                                         message=f"{parsed.canonical} does not appear in the BIS catalogue.",
                                         action="Remove the citation or verify it on the BIS portal.")])

        cited_row = self._edition_for_year(editions, parsed.year)
        family_current = next((r for r in editions if not r["withdrawn"]), None)
        chain: List[str] = []
        chained = None

        # A withdrawn edition may name its successor, which can sit in another family entirely
        # (IS 8112 was merged into IS 269). Follow that chain, but never let a failed chain throw
        # away a current edition of the same family: IS 10748:2004 is withdrawn and names nobody,
        # while IS 10748:2025 is in force.
        if cited_row is not None and cited_row["withdrawn"]:
            chained, chain = self._follow_chain(cited_row)
        elif family_current is None:
            chained, chain = self._follow_chain(editions[0])
        current_row = chained or family_current
        if chained is None:
            chain = []

        # Republished in parts: no current edition of this exact family, but the same number is in
        # force as a part. IS 2062:2011 is withdrawn; IS 2062 (Part 1):2025 carries the subject now.
        split_into = None
        if current_row is None:
            siblings = [r for r in self.cat.same_number(parsed) if not r["withdrawn"]]
            if siblings:
                split_into = siblings[0]
                current_row = split_into

        warnings = self._warnings(citation, parsed, cited_row, current_row, chain)
        if parts_only and current_row is not None:
            warnings.insert(0, VersionWarning(
                severity=Severity.MEDIUM, cited=citation,
                message=f"{parsed.family} is published in parts; {current_row['is_number']} is the "
                        f"matching part in force.",
                action=f"Cite {current_row['is_number']}, and add the other parts if they apply."))
        if split_into is not None:
            warnings = [VersionWarning(
                severity=Severity.HIGH, cited=citation,
                message=f"{parsed.family} has been withdrawn; the subject is now published as "
                        f"{split_into['is_number']}.",
                action=f"Replace the citation with {split_into['is_number']}.")]
        status = self._status(parsed, cited_row, current_row, chain)
        amendments = self.cat.amendments(current_row["record_id"]) if current_row is not None else []
        if amendments:
            latest = amendments[-1]
            warnings.append(VersionWarning(
                severity=Severity.LOW, cited=citation,
                message=f"{current_row['is_number']} carries {len(amendments)} amendment(s), "
                        f"the latest being {latest['number']} of {latest['year']}.",
                action="Cite the standard as amended."))

        return ResolvedStandard(
            cited=citation,
            status=status,
            exists=True,
            record_id=cited_row["record_id"] if cited_row is not None else None,
            cited_edition=cited_row["is_number"] if cited_row is not None else None,
            current=current_row["is_number"] if current_row is not None else None,
            current_record_id=current_row["record_id"] if current_row is not None else None,
            title=(current_row or cited_row or editions[0])["title"],
            replacement_chain=chain,
            amendments=amendments,
            warnings=warnings,
        )

    def resolve_all(self, citations: List[str]) -> List[ResolvedStandard]:
        return [self.resolve(c) for c in citations]

    # ---------------------------------------------------------------- internals

    def _edition_for_year(self, editions, year: Optional[int]):
        """The edition the user meant. A bare family number means 'whatever is current'."""
        if year is None:
            return next((r for r in editions if not r["withdrawn"]), editions[0])
        exact = [r for r in editions if self.cat.year_of(r) == year]
        if exact:
            return exact[0]
        return None

    def _follow_chain(self, row):
        """Walk 'superseded by' until a current standard is reached, guarding against loops."""
        chain = [row["is_number"]]
        seen = {row["record_id"]}
        current = row
        for _ in range(MAX_HOPS):
            if not current["withdrawn"]:
                return current, chain
            successor = parse_any_is(current["superseded_by"] or "")
            if not successor:
                return None, chain
            candidates = self.cat.family(successor)
            if successor.year is not None:
                candidates = [c for c in candidates if self.cat.year_of(c) == successor.year] or candidates
            nxt = next((c for c in candidates if c["record_id"] not in seen), None)
            if nxt is None:
                return None, chain
            seen.add(nxt["record_id"])
            chain.append(nxt["is_number"])
            current = nxt
        return (current if not current["withdrawn"] else None), chain

    def _status(self, parsed, cited_row, current_row, chain) -> CitationStatus:
        if cited_row is not None and not cited_row["withdrawn"]:
            return CitationStatus.CURRENT
        if cited_row is not None and cited_row["withdrawn"]:
            # A replacement exists, whether it was named explicitly or is simply the newer edition.
            return CitationStatus.SUPERSEDED if current_row is not None else CitationStatus.WITHDRAWN
        if current_row is None:
            return CitationStatus.WITHDRAWN
        # The cited year is not in the catalogue. If what is in force carries a different number,
        # the standard was superseded rather than merely re-dated: IS 8112:1989 to IS 269:2015.
        current_parsed = parse_any_is(current_row["is_number"] or "")
        if current_parsed and current_parsed.base_number != parsed.base_number:
            return CitationStatus.SUPERSEDED
        return CitationStatus.CURRENT

    def _warnings(self, citation, parsed, cited_row, current_row, chain) -> List[VersionWarning]:
        out: List[VersionWarning] = []

        if cited_row is None and parsed.year is not None:
            current_name = current_row["is_number"] if current_row is not None else None
            # The cited year is not in the catalogue. If the replacement belongs to a different
            # family, the standard was superseded, which is a defect, not a version drift. This is
            # the common tender case: 'IS 8112:1989' cited for cement that is now IS 269:2015.
            moved_family = (current_name is not None
                            and parse_any_is(current_name).base_number != parsed.base_number)
            if moved_family:
                route = " to ".join(chain) if len(chain) > 2 else None
                out.append(VersionWarning(
                    severity=Severity.HIGH, cited=citation,
                    message=f"{parsed.family} has been withdrawn and replaced by {current_name}. "
                            f"The cited {parsed.year} edition is not in the catalogue."
                            + (f" Replacement route: {route}." if route else ""),
                    action=f"Replace the citation with {current_name}."))
            else:
                out.append(VersionWarning(
                    severity=Severity.MEDIUM, cited=citation,
                    message=f"No {parsed.year} edition of {parsed.family} appears in the catalogue; "
                            f"the edition in force is {current_name or 'unknown'}.",
                    action=f"Cite {current_name}." if current_name else "Verify on the BIS portal."))
            return out

        if cited_row is not None and cited_row["withdrawn"]:
            if current_row is not None:
                route = " to ".join(chain) if len(chain) > 2 else None
                out.append(VersionWarning(
                    severity=Severity.HIGH, cited=citation,
                    message=f"{cited_row['is_number']} has been withdrawn and replaced by "
                            f"{current_row['is_number']}." + (f" Replacement route: {route}." if route else ""),
                    action=f"Replace the citation with {current_row['is_number']}."))
            else:
                out.append(VersionWarning(
                    severity=Severity.HIGH, cited=citation,
                    message=f"{cited_row['is_number']} has been withdrawn and BIS names no replacement.",
                    action="Remove the citation and confirm the correct standard with BIS."))
            return out

        if (cited_row is not None and current_row is not None
                and cited_row["record_id"] != current_row["record_id"]):
            out.append(VersionWarning(
                severity=Severity.MEDIUM, cited=citation,
                message=f"{cited_row['is_number']} is not the latest edition; "
                        f"{current_row['is_number']} is in force.",
                action=f"Consider citing {current_row['is_number']}."))
        return out
