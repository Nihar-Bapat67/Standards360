"""Module C4: Certification and QCO Engine.

Answers whether a product may legally be supplied without BIS certification, under which scheme,
from which date, and which laboratories can test it. Every answer is a lookup against the catalogue,
so each sentence it produces can be traced to a BIS record.

Two rules this module never breaks:

* A blank certification field means BIS states nothing. It is reported as "not stated", never as
  "not required", because a supplier reading "not required" in a tender could be misled.
* The scheme is inferred from the department, and the inference is returned with the answer so a
  human can check it. BIS does not publish the scheme name in this data.

    from app.core.certification import CertificationEngine
    CertificationEngine().for_standards(["IS 269:2015"], persona="procurement", state="Maharashtra")
"""

import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.catalogue import Catalogue, parse_any_is  # noqa: E402
from app.core.labs import LabFinder  # noqa: E402
from app.core.version_resolver import VersionResolver  # noqa: E402
from contracts.analysis import (  # noqa: E402
    CertificationAnswer,
    StandardCertification,
)

# Departments whose products are commonly registered under CRS rather than the ISI mark.
CRS_DEPARTMENTS = {"LITD", "ETD"}
ISI = "BIS Product Certification (ISI mark)"
CRS = "Compulsory Registration Scheme (CRS), to be confirmed against the notified QCO"


class CertificationEngine:
    def __init__(self, catalogue: Optional[Catalogue] = None, resolver: Optional[VersionResolver] = None,
                 finder: Optional[LabFinder] = None):
        self.cat = catalogue or Catalogue.shared()
        self.resolver = resolver or VersionResolver(self.cat)
        # C4.5 owns everything about laboratories, so the short list in the certification panel and
        # the full laboratory page describe the same laboratories in the same order.
        self.finder = finder or LabFinder(self.cat, self.resolver)

    # ---------------------------------------------------------------- public

    def for_standard(self, is_number: str, state: Optional[str] = None) -> StandardCertification:
        """What BIS states about certification for one standard, resolved to its current edition."""
        resolved = self.resolver.resolve(is_number)
        record_id = resolved.current_record_id or resolved.record_id
        row = self.cat.record(record_id) if record_id else None
        if row is None:
            return StandardCertification(is_number=is_number, mandatory=False, stated=False)

        certification = (row["certification"] or "").strip()
        qco_status = (row["qco_status"] or "").strip()
        qco_date = (row["qco_date"] or "").strip()
        mandatory = "mandatory" in certification.lower()
        stated = bool(certification) and certification.lower() != "none"

        labs = self.cat.labs(record_id)
        nearest = self.finder.rank(labs, self.finder.resolve_origin(place=state))[:5]
        department = (row["department"] or "")[:4].strip()
        scheme = scheme_basis = None
        if mandatory or qco_status:
            if department in CRS_DEPARTMENTS:
                scheme, scheme_basis = CRS, f"department {department}, where CRS commonly applies"
            else:
                scheme, scheme_basis = ISI, f"department {department}, where product certification applies"

        return StandardCertification(
            is_number=row["is_number"],
            record_id=record_id,
            mandatory=mandatory,
            stated=stated,
            qco_status=qco_status or None,
            qco_date=qco_date or None,
            in_force=self._in_force(qco_date),
            scheme=scheme,
            scheme_basis=scheme_basis,
            labs_available=len(labs),
            nearest_labs=nearest,
        )

    def for_standards(self, is_numbers: List[str], persona: str = "procurement",
                      state: Optional[str] = None) -> CertificationAnswer:
        """The certification panel for a whole recommendation, phrased for one persona."""
        results = [self.for_standard(n, state) for n in is_numbers]
        mandatory = [r for r in results if r.mandatory]
        not_stated = [r.is_number for r in results if not r.stated]

        labs, seen = [], set()
        for r in mandatory or results:
            for lab in r.nearest_labs:
                if lab.name not in seen:
                    seen.add(lab.name)
                    labs.append(lab)

        return CertificationAnswer(
            certification_required=bool(mandatory),
            persona=persona,
            statement=self._statement(mandatory, results, persona),
            standards=results,
            labs_available=sum(r.labs_available for r in mandatory) if mandatory else 0,
            nearest_labs=labs[:5],
            not_stated=not_stated,
        )

    # ---------------------------------------------------------------- internals

    @staticmethod
    def _in_force(qco_date: str) -> Optional[bool]:
        if not qco_date:
            return None
        try:
            return date.fromisoformat(qco_date) <= date.today()
        except ValueError:
            return None

    def _statement(self, mandatory: List[StandardCertification],
                   results: List[StandardCertification], persona: str) -> str:
        if not results:
            return "No standards were supplied, so certification could not be checked."
        if not mandatory:
            return ("BIS does not state compulsory certification for these standards. "
                    "This is not a statement that certification is unnecessary; confirm against the "
                    "relevant Quality Control Order before relying on it.")

        first = mandatory[0]
        names = ", ".join(r.is_number for r in mandatory)
        when = ""
        if first.qco_date:
            when = (f" The Quality Control Order has been in force since {first.qco_date}."
                    if first.in_force else
                    f" The Quality Control Order takes effect on {first.qco_date}.")
        labs = f" {first.labs_available} BIS-recognised laboratories can carry out the testing." \
            if first.labs_available else ""

        if persona == "manufacturer":
            return (f"You must hold a valid BIS licence under {first.scheme} before supplying goods "
                    f"covered by {names}.{when}{labs}")
        return (f"Compulsory BIS certification applies to {names}. Bidders must hold a valid licence "
                f"under {first.scheme}, and this should be stated as an eligibility condition.{when}{labs}")
