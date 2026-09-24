"""Contracts for B4, B5 and D2 (manual §9).

These complete the set the online pipeline agrees on: a verdict per citation the tender already
carries, the gate's decision about whether we know enough, and the single recommendation with its
three citation depths.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from contracts.analysis import CertificationAnswer, Severity, VersionWarning
from contracts.retrieval import AlliedStandard, Evidence


class CitationVerdict(BaseModel):
    """B4 output, one per standard the tender already cites."""
    model_config = ConfigDict(extra="forbid")

    citation: str
    exists: bool
    status: str = Field(..., description="current | superseded | withdrawn | not_found")
    relevant: Optional[bool] = Field(default=None,
                                     description="None when relevance could not be judged, which is "
                                                 "not the same as judging it irrelevant")
    relevance_score: Optional[float] = None
    verdict: str = Field(..., description="keep | replace | remove | add | verify")
    replacement: Optional[str] = None
    reason: str
    severity: Severity
    title: Optional[str] = None


class SufficiencyResult(BaseModel):
    """B5 output, read by D4 to decide what to show the user."""
    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="ok | need_more_info")
    confidence: float
    band: str
    missing: List[str] = Field(default_factory=list)
    questions: List[Dict[str, str]] = Field(default_factory=list)
    can_proceed_anyway: bool = True
    drivers: List[str] = Field(default_factory=list)


class DepthOption(BaseModel):
    """One citation depth. Every depth names the same primary standard."""
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    standards: List[str] = Field(default_factory=list)
    default: bool = False
    rationale: str = ""


class Recommendation(BaseModel):
    """D2 output: one answer, three depths, with everything the document needs."""
    model_config = ConfigDict(extra="forbid")

    primary: Optional[str] = None
    primary_title: str = ""
    amendments: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Amendments in force on the primary standard. An amendment modifies a standard "
                    "without replacing it, so the edition year stays the same and the citation must "
                    "read 'as amended'. Carried here so no reader mistakes an amendment year for a "
                    "newer edition")
    primary_as_cited: str = Field(
        default="", description="How the primary should appear in a tender, amendments included")
    confidence: float = 0.0
    band: str = "low"
    evidence: Optional[Evidence] = None
    options: List[DepthOption] = Field(default_factory=list)
    allied: Dict[str, List[AlliedStandard]] = Field(default_factory=dict)
    verdicts: List[CitationVerdict] = Field(default_factory=list)
    warnings: List[VersionWarning] = Field(default_factory=list)
    certification: Optional[CertificationAnswer] = None
    explanation: str = Field(default="", description="Generated prose, already passed through D1")
    removed_by_guard: List[str] = Field(default_factory=list)
    status: str = Field(default="complete", description="complete | need_more_info | no_match")
