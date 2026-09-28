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

import asyncio
import json
import os
import queue
import sys
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.deliver.document import DocumentGenerator  # noqa: E402
from app.pipeline import AnalysisResult, Pipeline  # noqa: E402
from app.understand.language import supported as supported_languages  # noqa: E402
from contracts.analysis import CertificationAnswer, LabAnswer  # noqa: E402
from contracts.answer import CitationVerdict  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
# One Server-Sent Event: an event name, a JSON body, then the blank line that terminates the frame.
SSE_FRAME = "event: {name}\ndata: {body}\n\n"
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
    history: List[Dict[str, str]] = Field(default_factory=list, max_length=16,
                                           description="Recent conversation turns used to resolve follow-ups")
    previous_requirement: Optional[dict] = Field(default=None,
                                                  description="Structured requirement from the prior analysis")


class LabsRequest(BaseModel):
    """Where to get a product tested, for the standards an analysis has already recommended.

    The location is optional and may arrive three ways, in decreasing precision: a device coordinate
    the browser supplied, a town the user typed, or a state. Without any of them the laboratories are
    still returned, in catalogue order and without distances.
    """
    model_config = ConfigDict(extra="forbid")

    standards: List[str] = Field(..., description="IS numbers, as returned by /v1/analyze")
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    place: Optional[str] = Field(default=None, description="A town or state the user typed")
    limit: int = Field(default=8, ge=1, le=50)


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
    primary_as_cited: str = ""
    amendments: List[Dict[str, str]] = Field(default_factory=list)
    options: List[OptionOut] = Field(default_factory=list)
    allied: Dict[str, List[dict]] = Field(default_factory=dict)
    warnings: List[dict] = Field(default_factory=list)
    verdicts: List[CitationVerdict] = Field(default_factory=list)
    certification: Optional[CertificationAnswer] = None
    evidence: List[EvidenceOut] = Field(default_factory=list)
    explanation: str = ""
    removed_by_guard: List[str] = Field(default_factory=list)
    language: str = Field(default="en", description="The language this answer is written in")
    pdf_url: Optional[str] = Field(default=None, description="Filled once D3 generates the document")
    seconds: float = 0.0
    intent: str = "standards_recommendation"


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

# In development the interface runs on Vite's own port and has to call across origins. In production
# this process serves the built interface itself, so the two share an origin and CORS is not used at
# all. `STANDARDS360_ORIGINS` narrows it for the one deployment shape where they are split — a
# comma-separated list, for example "https://gem.gov.in,https://eprocure.gov.in".
_origins = [o.strip() for o in os.environ.get("STANDARDS360_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])


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
                              language=request.lang,
                              answers=request.answers, state=request.state,
                              history=request.history, previous_requirement=request.previous_requirement)
    return _shape(result)


@app.post("/v1/analyze/upload", response_model=AnalyzeResponse)
async def analyze_upload(file: UploadFile = File(...), persona: str = Form("procurement"),
                         state: Optional[str] = Form(None), lang: str = Form("auto"),
                         history: str = Form("[]"), previous_requirement: str = Form("")):
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
        try:
            conversation_history = json.loads(history)
            prior_requirement = json.loads(previous_requirement) if previous_requirement else None
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Conversation context must be valid JSON") from error
        if not isinstance(conversation_history, list):
            raise HTTPException(status_code=422, detail="Conversation history must be a list")
        pipeline: Pipeline = app.state.pipeline
        result = pipeline.analyze(file_path=temporary, persona=persona, state=state,
                                  language=lang, history=conversation_history,
                                  previous_requirement=prior_requirement)
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
                              language=request.lang,
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


@app.post("/v1/analyze/stream")
def analyze_stream(request: AnalyzeRequest):
    """The same analysis, reported stage by stage as Server-Sent Events.

    A full request takes several seconds because retrieval embeds the query and the composer calls a
    language model. Rather than show the user a spinner for that whole time, the pipeline reports
    each module as it finishes and this endpoint forwards those reports. The events are real: they
    come from `Pipeline.analyze`'s own `on_stage` callback, not from a timer in the browser.

    Events: `stage` for each module, then `result` with the identical AnalyzeResponse the plain
    endpoint returns, or `error` if the run failed.
    """
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    pipeline: Pipeline = app.state.pipeline
    events: "queue.Queue" = queue.Queue()

    def run():
        try:
            result = pipeline.analyze(
                text=request.text, persona=request.persona,
                language=request.lang,
                answers=request.answers, state=request.state,
                history=request.history, previous_requirement=request.previous_requirement,
                on_stage=lambda module, message, detail=None: events.put(
                    ("stage", {"module": module, "message": message, "detail": detail or {}})))
            events.put(("result", _shape(result).model_dump()))
        except Exception as exc:  # the browser must learn that it failed, not hang
            events.put(("error", {"detail": f"{type(exc).__name__}: {exc}"}))
        finally:
            events.put((None, None))

    threading.Thread(target=run, daemon=True).start()

    async def emit():
        while True:
            try:
                name, payload = events.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue
            if name is None:
                return
            body = json.dumps(payload, default=str)
            yield SSE_FRAME.format(name=name, body=body)

    return StreamingResponse(emit(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/v1/languages")
def languages():
    """The languages the interface may offer, and whether translation is actually live.

    `translation` is false when no API key is configured. The product still answers in that state —
    it simply answers in English — and the interface uses this to say so rather than offering a
    language switch that silently does nothing.
    """
    pipeline: Pipeline = app.state.pipeline
    return {"languages": supported_languages(), "translation": pipeline.language.available}


@app.post("/v1/labs", response_model=LabAnswer)
def labs(request: LabsRequest):
    """Module C4.5: the BIS-recognised laboratories that can test these standards, nearest first.

    Separate from /v1/analyze on purpose. The user grants location access after they have seen which
    standards apply, and re-running the whole pipeline to answer a follow-up question about
    laboratories would cost seconds for no benefit — this is a catalogue lookup and some arithmetic.
    """
    if not [n for n in request.standards if n.strip()]:
        raise HTTPException(status_code=422, detail="standards must not be empty")
    pipeline: Pipeline = app.state.pipeline
    finder = pipeline.certification.finder
    origin = finder.resolve_origin(lat=request.lat, lon=request.lon, place=request.place)
    if origin is None and (request.place or "").strip():
        # The town was not recognised. Say so rather than quietly returning an unordered list that
        # looks as though the location was understood.
        answer = finder.find(request.standards, None, limit=request.limit)
        answer.note = (f"“{request.place.strip()}” was not recognised as a town or state holding a "
                       f"BIS-recognised laboratory, so no distances are shown. Try a nearby city, or "
                       f"share your location.")
        return answer
    return finder.find(request.standards, origin, limit=request.limit)


@app.get("/v1/meta")
def meta():
    """Figures the landing page states, read from the live catalogue and the frozen gold set.

    The interface must never print a number we cannot produce on demand, so every headline figure
    on the marketing page is served from here rather than typed into the markup.
    """
    pipeline: Pipeline = app.state.pipeline
    catalogue = pipeline.resolver.cat
    index = pipeline.engine.meta
    con = catalogue.con
    def one(sql):
        try:
            return con.execute(sql).fetchone()[0]
        except Exception:
            return None

    results_path = ROOT / "eval" / "results.json"
    evaluation = {}
    if results_path.exists():
        try:
            raw = json.loads(results_path.read_text(encoding="utf-8"))
            evaluation = {"gold_records": raw.get("gold_records"),
                          "evaluated_at": raw.get("evaluated_at"), **raw.get("overall_raw", {})}
        except Exception:
            evaluation = {}

    return {
        "catalogue": {
            "total": one("SELECT COUNT(*) FROM standards"),
            "current": one("SELECT COUNT(*) FROM standards WHERE withdrawn = 0"),
            "withdrawn": one("SELECT COUNT(*) FROM standards WHERE withdrawn = 1"),
            "with_replacement": one("SELECT COUNT(*) FROM standards WHERE withdrawn = 1 "
                                    "AND superseded_by IS NOT NULL AND superseded_by <> ''"),
            "cross_references": one("SELECT COUNT(*) FROM xrefs"),
            "qco": one("SELECT COUNT(*) FROM standards WHERE qco_status IS NOT NULL AND qco_status <> ''"),
            "labs": one("SELECT COUNT(DISTINCT name) FROM labs"),
            "lab_states": one("SELECT COUNT(DISTINCT state) FROM labs"),
            "labs_with_contact": one("SELECT COUNT(*) FROM lab_directory WHERE phone <> ''"),
        },
        "index": {"model": index.get("model"), "clauses": index.get("rows_indexed"),
                  "standards": index.get("standards_indexed"), "built_at": index.get("built_at")},
        "evaluation": evaluation,
        "sectors": ["CED - Civil Engineering", "MTD - Metallurgical Engineering"],
    }


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
        primary_as_cited=recommendation.primary_as_cited,
        amendments=recommendation.amendments,
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
        language=getattr(result, "language", "en"),
        seconds=result.seconds,
        intent=result.plan.intent,
    )


# ---------------------------------------------------------------- the built interface

# In production the web interface is served by this same process, so a deployment is one command and
# one port. In development the front end runs on Vite's own server and calls across via CORS, so the
# absence of a build is normal rather than an error.
WEB_DIST = ROOT / "web" / "dist"

if WEB_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        """Serve the single-page app, letting it own client-side routing.

        A request for a real file gets that file; anything else gets index.html so a deep link such
        as /workspace works on a fresh load rather than 404ing.
        """
        candidate = (WEB_DIST / full_path).resolve()
        if full_path and candidate.is_file() and WEB_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
