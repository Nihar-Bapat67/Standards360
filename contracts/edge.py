"""Pydantic contracts for Indian Standards Cross-Reference Extraction (Module A3).

Defines the single source of truth for extracted citation edges and A3 manifest entries.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RelationType(str, Enum):
    """Classified relation between citing standard and cited standard.

    Matches C2 graph traversal weights exactly.
    """
    NORMATIVE_REFERENCE = "normative_reference"
    TEST_METHOD = "test_method"
    TERMINOLOGY = "terminology"
    SAFETY = "safety"
    INSTALLATION = "installation"
    RELATED_PRODUCT = "related_product"
    PRODUCT = "product"
    SAME_FAMILY_PART = "same_family_part"
    UNCERTAIN = "uncertain"


class EdgeRecord(BaseModel):
    """A directed, typed reference edge from one Indian Standard to another."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    from_is: str = Field(..., description="Citing standard identifier (from document/A2)")
    to_is: str = Field(..., description="Cited target standard identifier")
    relation: RelationType = Field(..., description="Classified semantic relationship")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0.0 - 1.0")
    clause_id: str = Field(..., description="A2 clause_id where citation was discovered")
    evidence_text: str = Field(..., description="Sentence or excerpt containing the citation")
    to_in_catalogue: bool = Field(..., description="Whether cited target exists in A1 catalogue.db")
    extraction_method: str = Field(default="regex+llm", description="Method used for extraction/classification")
    flags: List[str] = Field(default_factory=list, description="Diagnostic flags")


class A3ManifestEntry(BaseModel):
    """Manifest status for a single standard processed by A3."""
    model_config = ConfigDict(populate_by_name=True)

    is_number: str = Field(..., description="Standard identifier")
    n_citations_found: int = Field(default=0, description="Total raw citation mentions detected")
    n_edges_emitted: int = Field(default=0, description="Total validated edges emitted")
    n_rejected_false_positive: int = Field(default=0, description="False-positive or self-header mentions rejected")
    n_target_not_in_catalogue: int = Field(default=0, description="Citations to standards outside catalogue scope")

