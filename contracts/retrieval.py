"""Contracts for the retrieval side of Stage C (C1 and C2)."""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    """The clause a recommendation rests on. Every recommended standard carries one."""
    model_config = ConfigDict(extra="forbid")

    clause: str
    clause_id: str
    role: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    quote: str = Field(..., description="Short extract shown to the user; never the full clause")


class RetrievedStandard(BaseModel):
    """One standard returned by C1, with the clause that matched."""
    model_config = ConfigDict(extra="forbid")

    is_number: str
    record_id: Optional[int] = None
    title: str = ""
    department: str = ""
    source: str = Field(default="clause",
                        description="clause: matched on indexed text, with a clause as evidence. "
                                    "title: matched on the standard's catalogue title only, because "
                                    "no text is held for it. cited: named as the authority inside a "
                                    "clause that matched. Only 'clause' carries quotable evidence")
    score: float = Field(..., description="Ranking score: reranker probability, or the fusion score")
    fusion_score: float = 0.0
    match: Optional[float] = Field(default=None,
                                   description="Absolute 0..1 match of the evidence clause to the query, "
                                               "from the cross-encoder. Comparable across queries, "
                                               "unlike the fusion score, so C5 uses it as signal s1")
    evidence: Optional[Evidence] = None


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    standards: List[RetrievedStandard] = Field(default_factory=list)
    reranked: bool = False
    considered_clauses: int = 0
    seconds: float = 0.0


class AlliedStandard(BaseModel):
    """A standard reached by walking the relationship map outward from a recommendation."""
    model_config = ConfigDict(extra="forbid")

    is_number: str = Field(..., description="Current edition, after version resolution")
    cited_as: Optional[str] = Field(default=None, description="How the source standard referred to it")
    record_id: Optional[int] = None
    title: str = ""
    relation: str
    weight: float
    hops: int
    paths: List[str] = Field(default_factory=list, description="Every route by which it was reached")
    evidence: Optional[str] = Field(default=None, description="Sentence from A3 that asserts the relationship")
    superseded: bool = Field(default=False, description="True when the reference pointed at a withdrawn edition")


class AlliedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seeds: List[str] = Field(default_factory=list)
    groups: Dict[str, List[AlliedStandard]] = Field(default_factory=dict)
    total: int = 0
