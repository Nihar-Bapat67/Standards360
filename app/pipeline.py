"""The online pipeline, wired end to end.

One object that owns the loaded models and runs a request through every stage in the order the
manual sets out. The API, the web interface and any script all call this, so there is one path
through the system and no second implementation to keep in step.

    B1 read the input          ->  B3 extract the requirement
    C4 certification (starts from the category, so it runs alongside retrieval)
    C1 retrieve  ->  C2 allied  ->  C3 versions  ->  C5 confidence
    B5 gate: answer, or ask two short questions
    B4 verdicts on what the tender already cited
    D2 compose one answer at three depths  ->  D1 guard the prose

Loading the models costs about 40 seconds, so a Pipeline is built once and reused. Everything after
that runs in about a second.

    from app.pipeline import Pipeline
    Pipeline.shared().analyze(text="500 MT of 43 grade OPC for RCC work, as per IS 8112")
"""

import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.allied import AlliedExpander  # noqa: E402
from app.core.certification import CertificationEngine  # noqa: E402
from app.core.confidence import ConfidenceScorer  # noqa: E402
from app.core.retrieval import RetrievalEngine  # noqa: E402
from app.core.version_resolver import VersionResolver  # noqa: E402
from app.deliver.composer import Composer  # noqa: E402
from app.understand.citation_validator import CitationValidator  # noqa: E402
from app.understand.extractor import RequirementExtractor  # noqa: E402
from app.understand.input_handler import InputHandler  # noqa: E402
from app.understand.sufficiency import SufficiencyGate  # noqa: E402
from contracts.answer import Recommendation, SufficiencyResult  # noqa: E402
from contracts.requirement import InputPayload, RequirementObject  # noqa: E402

ALLIED_DEPTH = 2


class AnalysisResult:
    """Everything one request produced, before it is shaped for a particular client."""

    def __init__(self, payload: InputPayload, requirement: RequirementObject,
                 sufficiency: SufficiencyResult, recommendation: Recommendation,
                 query: str, seconds: float):
        self.payload = payload
        self.requirement = requirement
        self.sufficiency = sufficiency
        self.recommendation = recommendation
        self.query = query
        self.seconds = seconds

    @property
    def needs_more_info(self) -> bool:
        return self.sufficiency.status == "need_more_info"


class Pipeline:
    _instance: Optional["Pipeline"] = None

    def __init__(self, use_llm: bool = True, warm: bool = True):
        self.input_handler = InputHandler()
        self.extractor = RequirementExtractor(use_llm=use_llm)
        self.engine = RetrievalEngine(warm=warm)
        self.allied = AlliedExpander()
        self.resolver = VersionResolver()
        self.certification = CertificationEngine(resolver=self.resolver)
        self.confidence = ConfidenceScorer()
        self.gate = SufficiencyGate(extractor=self.extractor, use_llm=use_llm)
        self.validator = CitationValidator(resolver=self.resolver, engine=self.engine)
        self.composer = Composer(resolver=self.resolver, use_llm=use_llm)

    @classmethod
    def shared(cls, **kwargs) -> "Pipeline":
        if cls._instance is None:
            cls._instance = cls(**kwargs)
        return cls._instance

    # ---------------------------------------------------------------- public

    def analyze(self, text: Optional[str] = None, file_path: Optional[str] = None,
                persona: str = "procurement", language: str = "en",
                answers: Optional[Dict[str, str]] = None,
                state: Optional[str] = None,
                on_stage: Optional[Callable[[str, str, dict], None]] = None) -> AnalysisResult:
        """Run one request all the way through.

        `answers` carries the user's replies to an earlier round of questions; supplying them is
        what closes B5's loop, and the merged requirement then travels the same path as a first
        request would.

        `on_stage(module, message, detail)` is called as each stage finishes, so a caller that can
        stream — the SSE endpoint the web interface uses — can report real progress instead of
        showing a spinner for ten seconds. It is optional and never changes the result; a caller
        that passes nothing gets exactly the behaviour it always had.
        """
        started = time.time()
        stage = on_stage or (lambda module, message, detail=None: None)

        payload = (self.input_handler.read(file_path) if file_path
                   else self.input_handler.read_text(text or ""))
        # Pasted text has no pages, so reporting "0 page(s)" would be both wrong and odd to read.
        stage("B1",
              (f"Read {payload.pages} page{'s' if payload.pages != 1 else ''} of the {payload.source}"
               if payload.pages else "Read the specification"),
              {"source": payload.source, "pages": payload.pages, "richness": payload.richness})

        requirement = self.extractor.extract(payload, language=language)
        if answers:
            requirement = self.gate.apply_answers(requirement, answers)
        stage("B3", f"Extracted the requirement: {requirement.product or 'unnamed product'}",
              {"product": requirement.product, "category": requirement.category,
               "attributes": requirement.attributes, "cited": requirement.cited_standards,
               "extracted_by": requirement.extracted_by})

        query = self.engine.build_query(requirement.model_dump())
        stage("C1", f"Searching {self.engine.index.ntotal} clauses", {"query": query})
        retrieval = self.engine.search(query, top_k=5)
        stage("C1", (f"Best match {retrieval.standards[0].is_number}" if retrieval.standards
                     else "No standard matched closely enough"),
              {"standards": [{"is_number": s.is_number, "title": s.title, "source": s.source}
                             for s in retrieval.standards[:5]]})

        allied = None
        certification = None
        warnings = []
        if retrieval.standards:
            primary = retrieval.standards[0].is_number
            allied = self.allied.expand([primary], depth=ALLIED_DEPTH)
            recommended = [primary] + [a.is_number for group in allied.groups.values() for a in group][:6]
            stage("C2", f"{sum(len(g) for g in allied.groups.values())} allied standards, by role",
                  {"groups": {k: len(v) for k, v in allied.groups.items()}})
            certification = self.certification.for_standards(recommended[:4], persona=persona, state=state)
            stage("C4", ("Compulsory BIS certification applies"
                         if certification and certification.certification_required
                         else "No compulsory certification stated by BIS"),
                  {"required": bool(certification and certification.certification_required),
                   "labs": certification.labs_available if certification else 0})
            warnings = self.resolver.resolve(primary).warnings
            stage("C3", f"{len(warnings)} version warning(s)", {"warnings": len(warnings)})

        required = self.extractor.fields.get(requirement.category, {}).get("required", [])
        confidence = self.confidence.score(retrieval, allied, required=required,
                                           present=list(requirement.attributes))
        stage("C5", f"Confidence {confidence.score} ({confidence.band})",
              {"score": confidence.score, "band": confidence.band, "drivers": confidence.drivers})
        sufficiency = self.gate.check(requirement, confidence)

        verdicts = self.validator.validate(
            requirement.cited_standards, query=query,
            recommended=[retrieval.standards[0].is_number] if retrieval.standards else [])
        # Every citation warning the tender earned belongs in the document, not only the primary's.
        for verdict in verdicts:
            if verdict.verdict in ("replace", "remove") and verdict.severity.value == "high":
                warnings = warnings + [w for w in self.resolver.resolve(verdict.citation).warnings
                                       if w.severity.value == "high"]

        if verdicts:
            stage("B4", f"Judged {len(verdicts)} citation(s) already in the tender",
                  {"verdicts": [{"citation": v.citation, "verdict": v.verdict} for v in verdicts]})

        recommendation = self.composer.compose(requirement, retrieval, allied, confidence,
                                               verdicts, certification, warnings)
        stage("D2", "Composed the answer at three citation depths",
              {"removed_by_guard": recommendation.removed_by_guard})
        if sufficiency.status == "need_more_info" and recommendation.status == "complete":
            recommendation.status = "need_more_info"

        return AnalysisResult(payload, requirement, sufficiency, recommendation, query,
                              round(time.time() - started, 2))

    def standards_in(self, result: AnalysisResult, option_id: str = "B") -> List[str]:
        """The standards of one citation depth, for the document generator."""
        for option in result.recommendation.options:
            if option.id.upper() == option_id.upper():
                return option.standards
        return [result.recommendation.primary] if result.recommendation.primary else []
