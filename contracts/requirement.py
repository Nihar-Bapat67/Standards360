"""The RequirementObject (manual §9), produced by B3 and read by B4, B5, C1 and C4."""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class InputPayload(BaseModel):
    """B1 output: any of the four input types reduced to text plus a note of where it came from."""
    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., description="pdf | docx | text | image | product_name")
    text: str
    pages: int = 0
    spec_section_page: Optional[int] = Field(default=None,
                                             description="Page where the technical specification appears to start")
    richness: str = Field(..., description="full_tender | spec_only | name_only")
    filename: Optional[str] = None
    notes: List[str] = Field(default_factory=list, description="Anything the user should know, such as OCR being unavailable")


class RequirementObject(BaseModel):
    """B3 output. The one shape the whole online pipeline agrees on."""
    model_config = ConfigDict(extra="forbid")

    product: str = ""
    category: str = Field(default="", description="Matches the key used by the required-field table")
    attributes: Dict[str, str] = Field(default_factory=dict)
    cited_standards: List[str] = Field(default_factory=list, description="Empty for scenario S1")
    not_specified: List[str] = Field(default_factory=list,
                                     description="Required fields for this category that the text never gave")
    language: str = "en"
    source: str = "text"
    richness: str = "spec_only"
    extracted_by: str = Field(default="rules", description="rules | llm | llm+rules")
