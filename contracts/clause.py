"""Pydantic contracts for Indian Standards Clause Parsing (Module A2).

These models define the single source of truth for clauses, manifests,
and quarantine records produced by Stage A2 and consumed by Stage A3/A4.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ClauseRole(str, Enum):
    """Semantic role of a clause within a standard."""
    SCOPE = "scope"
    REFERENCES = "references"
    TERMINOLOGY = "terminology"
    REQUIREMENTS = "requirements"
    SAMPLING = "sampling"
    TEST_METHODS = "test_methods"
    MARKING = "marking"
    PACKING = "packing"
    ANNEX = "annex"
    FOREWORD = "foreword"
    OTHER = "other"


class ClauseRecord(BaseModel):
    """A single structured clause extracted from an Indian Standard.

    Keeps the four manual keys ('is', 'clause', 'title', 'text') exactly,
    plus required enrichment fields for citation attribution and retrieval.
    """
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    is_standard: str = Field(..., alias="is", description="Canonical IS identifier with year, e.g. 'IS 269:1989'")
    clause: str = Field(..., description="Clause designation, e.g. '1', '4.2', 'ANNEX A'")
    title: str = Field(..., description="Heading or title of the clause")
    text: str = Field(..., description="Cleaned, normalized text content of the clause")
    
    clause_id: str = Field(..., description="Unique, stable ID: '<is>#<clause>'")
    record_id: Optional[int] = Field(default=None, description="A1 catalogue record_id of the standard this clause belongs to")
    family: str = Field(..., description="Standard family without year or section, e.g. 'IS 269'")
    year: int = Field(..., description="Year of publication/edition from which text was parsed")
    level: int = Field(default=1, description="Nesting level (1 for top-level, 2 for sub-clause)")
    parent_clause: Optional[str] = Field(default=None, description="Parent clause number if sub-clause")
    role: ClauseRole = Field(default=ClauseRole.OTHER, description="Classified semantic role of clause")
    page_start: int = Field(..., description="1-indexed starting page in the source document")
    page_end: int = Field(..., description="1-indexed ending page in the source document")
    has_table: bool = Field(default=False, description="Whether the clause contains structured table data")
    flags: List[str] = Field(default_factory=list, description="Diagnostic flags (e.g. text_version_differs_from_current)")


class StandardManifestEntry(BaseModel):
    """Manifest status for a single standard processed by the parser."""
    model_config = ConfigDict(populate_by_name=True)

    is_number: str = Field(..., description="Canonical standard number")
    record_id: Optional[int] = Field(default=None, description="Catalogue record ID if matched")
    status: str = Field(..., description="Execution status: 'parsed' or 'quarantined'")
    reason: Optional[str] = Field(default=None, description="Reason if quarantined or flagged")
    page_range: List[int] = Field(default_factory=list, description="[page_start, page_end] in source PDF")
    n_clauses: int = Field(default=0, description="Total clauses extracted")
    has_scope: bool = Field(default=False, description="Whether a scope clause was identified")
    has_references: bool = Field(default=False, description="Whether a references clause was identified")
    text_coverage_ratio: float = Field(default=1.0, description="Clause text length / cleaned page text length")
    flags: List[str] = Field(default_factory=list, description="Integrity and anomaly flags")
    sha256: str = Field(..., description="SHA-256 hash of the source document")


class QuarantineEntry(BaseModel):
    """Entry describing a standard that could not be parsed."""
    model_config = ConfigDict(populate_by_name=True)

    is_number: str = Field(..., description="Standard identifier")
    reason: str = Field(..., description="High-level quarantine category")
    details: str = Field(..., description="Detailed diagnostic explanation")
    page_range: Optional[List[int]] = Field(default=None, description="Page range if known")

