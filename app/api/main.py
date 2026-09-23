"""Module D4: API Layer.

One documented endpoint that does the whole job. The web interface is a client of this endpoint and
nothing more, which is what makes integration with a procurement portal a configuration rather than
a rewrite: GeM or CPPP would call exactly what our own front end calls.

    uvicorn app.api.main:app --port 8000
    curl -X POST localhost:8000/v1/analyze -H "Content-Type: application/json" \
         -d '{"text": "500 MT of 43 grade OPC for RCC work as per IS 8112", "persona": "procurement"}'

Interactive documentation is generated at /docs, and the OpenAPI schema at /openapi.json.

The models are loaded once while the service starts, because the first embedding costs 7 to 16
seconds on a cold process and no user should pay for that.
"""

import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.deliver.document import DocumentGenerator  # noqa: E402
from app.pipeline import AnalysisResult, Pipeline  # noqa: E402
from contracts.analysis import CertificationAnswer  # noqa: E402
from contracts.answer import CitationVerdict  # noqa: E402

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"}


# ---------------------------------------------------------------- request and response shapes

class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="Tender text, a specification, or a product name")
    lang: str = Field(default="auto", description="Language of the text; 'auto' for detection")
    persona: str = Field(default="procurement", description="procurement | manufacturer")
    output_mode: str = Field(default="annexure", description="annexure | report")
    state: Optional[str] = Field(default=None, description="Used to list the nearest testing laboratories")
    answers: Optional[Dict[str, str]] = Field(default=None,
                                              description="Replies to the questions of a previous call")


class OptionOut(BaseModel):
    id: str
    label: str
    confidence: float
    band: str
    standards: List[str]
    default: bool = False
    rationale: str = ""


class EvidenceOut(BaseModel):
    standard: str
    clause: str
    role: str
    page: Optional[int] = None
    quote: str


class AnalyzeResponse(BaseModel):
    """The only contract the front end and a procurement portal ever see (manual §9)."""
    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="complete | need_more_info | no_match")
    query: str = ""
    requirement: dict = Field(default_factory=dict)
    questions: List[Dict[str, str]] = Field(default_factory=list)
    confidence: float = 0.0
    band: str = "low"
    confidence_drivers: List[str] = Field(default_factory=list)
    primary: Optional[str] = None
    primary_title: str = ""
    options: List[OptionOut] = Field(default_factory=list)
    allied: Dict[str, List[dict]] = Field(default_factory=dict)
    warnings: List[dict] = Field(default_factory=list)
    verdicts: List[CitationVerdict] = Field(default_factory=list)
    certification: Optional[CertificationAnswer] = None
    evidence: List[EvidenceOut] = Field(default_factory=list)
    explanation: str = ""
    removed_by_guard: List[str] = Field(default_factory=list)
    pdf_url: Optional[str] = Field(default=None, description="Filled once D3 generates the document")
    seconds: float = 0.0


# ---------------------------------------------------------------- application

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pipeline = Pipeline.shared()
    yield


app = FastAPI(
    title="Standards360",
    version="0.1.0",
    summary="Maps a procurement specification to the applicable Indian Standards, their allied "
            "standards, current versions and certification obligations.",
    lifespan=lifespan,
)

# The front end is served from a different port in development; a deployment would narrow this.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    """Whether the service is ready, and what it is serving."""
    pipeline: Pipeline = app.state.pipeline
    meta = pipeline.engine.meta
    return {
        "status": "ok",
        "index": {"model": meta["model"], "clauses": meta["rows_indexed"],
                  "standards": meta["standards_indexed"], "built_at": meta["built_at"]},
        "catalogue": len(pipeline.resolver.cat._by_record),
        "llm": pipeline.extractor.llm.available if pipeline.extractor.llm else False,
    }


@app.post("/v1/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):
    """Analyse pasted text, a specification, or a bare product name."""
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    pipeline: Pipeline = app.state.pipeline
    result = pipeline.analyze(text=request.text, persona=request.persona,
                              language="en" if request.lang == "auto" else request.lang,
                              answers=request.answers, state=request.state)
    return _shape(result)


@app.post("/v1/analyze/upload", response_model=AnalyzeResponse)
async def analyze_upload(file: UploadFile = File(...), persona: str = Form("procurement"),
                         state: Optional[str] = Form(None), lang: str = Form("auto")):
    """Analyse an uploaded tender: PDF, DOCX, text file, or a screenshot."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415,
                            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(ALLOWED_SUFFIXES)}")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File larger than 25 MB")

    # The document may be pre-tender confidential, so it is written to a temporary file, read, and
    # deleted. Nothing is retained on disk and nothing is sent anywhere.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(content)
        temporary = handle.name
    try:
        pipeline: Pipeline = app.state.pipeline
        result = pipeline.analyze(file_path=temporary, persona=persona, state=state,
                                  language="en" if lang == "auto" else lang)
        return _shape(result)
    finally:
        Path(temporary).unlink(missing_ok=True)


class DocumentRequest(AnalyzeRequest):
    option_id: str = Field(default="B", description="Citation depth: A, B or C")
    mode: str = Field(default="report", description="annexure | report")
    reference: Optional[str] = Field(default=None, description="Tender reference printed on the document")


@app.post("/v1/document", response_class=Response)
def document(request: DocumentRequest):
    """Generate the PDF for pasted text: a standalone report, or a bare annexure."""
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    pipeline: Pipeline = app.state.pipeline
    result = pipeline.analyze(text=request.text, persona=request.persona,
                              language="en" if request.lang == "auto" else request.lang,
                              answers=request.answers, state=request.state)
    return _pdf_response(result, request.option_id, request.mode, request.persona,
                         request.reference, original=None)


@app.post("/v1/document/upload", response_class=Response)
async def document_upload(file: UploadFile = File(...), persona: str = Form("procurement"),
                          option_id: str = Form("B"), mode: str = Form("annexure"),
                          reference: Optional[str] = Form(None), state: Optional[str] = Form(None)):
    """Analyse an uploaded tender and return it with the annexure appended.

    Output mode 1 from the manual: the officer's own document comes back complete, which is how a
    tender actually carries this information.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail=f"Unsupported file type '{suffix}'")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File larger than 25 MB")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(content)
        temporary = handle.name
    try:
        pipeline: Pipeline = app.state.pipeline
        result = pipeline.analyze(file_path=temporary, persona=persona, state=state)
        original = temporary if (mode == "annexure" and suffix == ".pdf") else None
        return _pdf_response(result, option_id, mode, persona, reference, original=original)
    finally:
        Path(temporary).unlink(missing_ok=True)


@app.get("/v1/standard/{is_number:path}")
def standard(is_number: str):
    """Everything the catalogue holds about one standard, for a details panel in the interface."""
    pipeline: Pipeline = app.state.pipeline
    resolved = pipeline.resolver.resolve(is_number)
    if not resolved.exists:
        raise HTTPException(status_code=404, detail=f"{is_number} is not in the BIS catalogue")
    certification = pipeline.certification.for_standard(resolved.current or is_number)
    allied = pipeline.allied.expand([resolved.current or is_number], depth=1)
    return {
        "resolved": resolved.model_dump(),
        "certification": certification.model_dump(),
        "allied": {relation: [a.model_dump() for a in items] for relation, items in allied.groups.items()},
    }


# ---------------------------------------------------------------- shaping

def _pdf_response(result: AnalysisResult, option_id: str, mode: str, persona: str,
                  reference: Optional[str], original: Optional[str]) -> Response:
    """Render the document and return it as bytes, leaving nothing on disk."""
    if result.recommendation.status == "no_match":
        raise HTTPException(status_code=422,
                            detail="No standard matched this description, so there is nothing to "
                                   "put in a document. Add detail or answer the questions first.")
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "standards360.pdf"
        DocumentGenerator().generate(result, str(target), option_id=option_id, mode=mode,
                                     original_pdf=original, persona=persona, reference=reference)
        content = target.read_bytes()
    name = ("completed_tender.pdf" if mode == "annexure" and original
            else f"standards_{'annexure' if mode == 'annexure' else 'report'}.pdf")
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "X-Primary-Standard": result.recommendation.primary or "",
                             "X-Confidence": str(result.recommendation.confidence)})


def _shape(result: AnalysisResult) -> AnalyzeResponse:
    """Turn the pipeline's internal result into the published contract."""
    recommendation = result.recommendation
    evidence = []
    if recommendation.evidence and recommendation.primary:
        evidence.append(EvidenceOut(
            standard=recommendation.primary, clause=recommendation.evidence.clause,
            role=recommendation.evidence.role, page=recommendation.evidence.page_start,
            quote=recommendation.evidence.quote))

    return AnalyzeResponse(
        status=recommendation.status,
        query=result.query,
        requirement=result.requirement.model_dump(),
        questions=result.sufficiency.questions,
        confidence=recommendation.confidence,
        band=recommendation.band,
        confidence_drivers=result.sufficiency.drivers,
        primary=recommendation.primary,
        primary_title=recommendation.primary_title,
        options=[OptionOut(id=o.id, label=o.label, confidence=recommendation.confidence,
                           band=recommendation.band, standards=o.standards, default=o.default,
                           rationale=o.rationale) for o in recommendation.options],
        allied={relation: [a.model_dump() for a in items]
                for relation, items in recommendation.allied.items()},
        warnings=[w.model_dump() for w in recommendation.warnings],
        verdicts=recommendation.verdicts,
        certification=recommendation.certification,
        evidence=evidence,
        explanation=recommendation.explanation,
        removed_by_guard=recommendation.removed_by_guard,
        seconds=result.seconds,
    )
