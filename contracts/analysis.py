"""Contracts for the online analysis modules (manual §9).

These are the shapes C3, C4 and D1 return. They are frozen in the sense that §9 means: the fields
may gain optional members, but nothing downstream should read a field that is not defined here.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CitationStatus(str, Enum):
    CURRENT = "current"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"
    NOT_FOUND = "not_found"


class VersionWarning(BaseModel):
    """One thing worth telling the user about a standard's currency."""
    model_config = ConfigDict(extra="forbid")

    severity: Severity
    cited: str = Field(..., description="The identifier as the user wrote it")
    message: str = Field(..., description="Plain sentence for the document")
    action: Optional[str] = Field(default=None, description="What the user should do about it")


class ResolvedStandard(BaseModel):
    """C3 output for one cited or recommended standard."""
    model_config = ConfigDict(extra="forbid")

    cited: str
    status: CitationStatus
    exists: bool
    record_id: Optional[int] = None
    cited_edition: Optional[str] = Field(default=None, description="The edition matching the cited year")
    current: Optional[str] = Field(default=None, description="The edition in force today")
    current_record_id: Optional[int] = None
    title: Optional[str] = None
    replacement_chain: List[str] = Field(default_factory=list,
                                         description="Withdrawn to replacement, followed to the end")
    amendments: List[dict] = Field(default_factory=list)
    warnings: List[VersionWarning] = Field(default_factory=list)


class LabSuggestion(BaseModel):
    """One BIS-recognised laboratory, as C4.5 offers it to a manufacturer.

    `address`, `phone` and `email` come from the BIS laboratory directory and are absent for the few
    laboratories BIS lists without them. `distance_km` is a straight line between two town centres,
    not a road distance, and is absent whenever the user's location is unknown or either town has no
    coordinate — see `app/core/labs.py`. `hours` is always absent: BIS does not publish opening times
    for recognised laboratories, and this project does not fill a gap with a guess.
    """
    model_config = ConfigDict(extra="forbid")

    name: str
    city: str
    state: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    distance_km: Optional[float] = Field(default=None,
                                         description="Straight-line distance between town centres, in km")
    same_city: bool = False
    same_state: bool = False
    directions_url: Optional[str] = Field(default=None, description="Google Maps directions link")
    hours: Optional[str] = Field(default=None, description="Not published by BIS; always None")
    tests: List[str] = Field(default_factory=list,
                             description="Which of the standards asked about this laboratory is recognised for")


class Origin(BaseModel):
    """Where the user is, as C4.5 resolved it, and how precisely."""
    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., description="What to show the user, e.g. 'Pune, Maharashtra'")
    lat: Optional[float] = None
    lon: Optional[float] = None
    precision: str = Field(..., description="device | town | state")


class LabAnswer(BaseModel):
    """C4.5 output: where to get a product tested, nearest first."""
    model_config = ConfigDict(extra="forbid")

    standards: List[str] = Field(default_factory=list, description="The standards the laboratories were matched on")
    total: int = Field(default=0, description="Recognised laboratories for these standards, before the list was cut")
    origin: Optional[Origin] = None
    note: str = Field(default="", description="How the location was read, or why no distance is shown")
    labs: List[LabSuggestion] = Field(default_factory=list)
    hours_note: str = Field(default="", description="The honest statement about opening times")
    attribution: str = ""


class StandardCertification(BaseModel):
    """What BIS states about certification for one standard."""
    model_config = ConfigDict(extra="forbid")

    is_number: str
    record_id: Optional[int] = None
    mandatory: bool = Field(..., description="True only when BIS states Mandatory Certification")
    stated: bool = Field(..., description="False when BIS leaves the field blank, which is not the same as 'not required'")
    qco_status: Optional[str] = None
    qco_date: Optional[str] = None
    in_force: Optional[bool] = Field(default=None, description="Whether the QCO date has passed")
    scheme: Optional[str] = None
    scheme_basis: Optional[str] = Field(default=None, description="Why that scheme was inferred, so it can be checked")
    labs_available: int = 0
    nearest_labs: List[LabSuggestion] = Field(default_factory=list)


class CertificationAnswer(BaseModel):
    """C4 output for a set of recommended standards, phrased for one persona."""
    model_config = ConfigDict(extra="forbid")

    certification_required: bool
    persona: str
    statement: str = Field(..., description="The sentence the document should carry")
    standards: List[StandardCertification] = Field(default_factory=list)
    labs_available: int = 0
    nearest_labs: List[LabSuggestion] = Field(default_factory=list)
    not_stated: List[str] = Field(default_factory=list,
                                  description="Standards where BIS states nothing; never reported as 'not required'")


class GuardResult(BaseModel):
    """D1 output: generated prose after every unverifiable standard number is removed."""
    model_config = ConfigDict(extra="forbid")

    text: str
    removed: List[str] = Field(default_factory=list)
    reasons: dict = Field(default_factory=dict)
    clean: bool = Field(..., description="True when nothing had to be removed")
