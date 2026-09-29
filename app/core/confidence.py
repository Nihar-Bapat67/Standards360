"""Module C5: Confidence Scorer.

Turns raw search scores into an honest figure. This matters more than it sounds: a similarity score
is not a probability, and showing one to a government officer as though it were is dishonest.

Four cheap signals, combined linearly, exactly as the manual's §17 A.5 sets out:

    s1  how well the winning clause answers the query          0..1
    s2  the margin over the runner-up, as min(margin / 0.30, 1) 0..1
    s3  required fields present / required fields total         0..1
    s4  graph agreement: does C2's expansion of the winner
        contain other standards C1 also ranked highly?          0 or 1

    confidence = 0.45*s1 + 0.20*s2 + 0.25*s3 + 0.10*s4
    bands: high >= 0.75, medium 0.50 to 0.75, low < 0.50

A formula the team can explain to a judge in one sentence is worth more than a model nobody can
defend. The weights are the manual's starting points and should be retuned on the gold set once
corpus coverage stops being the dominant error.

    from app.core.confidence import ConfidenceScorer
    ConfidenceScorer().score(retrieval_result, allied_result, required=["grade", "application"],
                             present=["grade", "application"])
"""

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from contracts.retrieval import AlliedResult, RetrievalResult  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

W_MATCH, W_MARGIN, W_FIELDS, W_GRAPH = 0.45, 0.20, 0.25, 0.10
MARGIN_FULL = 0.30      # a lead of this much over the runner-up counts as decisive
HIGH, MEDIUM = 0.75, 0.50
TITLE_ONLY_CEILING = 0.74   # matched on the catalogue title, with no clause to quote: never "high"


class ConfidenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float
    band: str
    should_ask: bool = Field(..., description="True when B5 should put a question to the user")
    signals: dict = Field(default_factory=dict)
    drivers: List[str] = Field(default_factory=list, description="Plain reasons, shown to the user")


class ConfidenceScorer:
    def score(self, retrieval: RetrievalResult, allied: Optional[AlliedResult] = None,
              required: Optional[List[str]] = None, present: Optional[List[str]] = None) -> ConfidenceResult:
        required = required or []
        present = present or []
        missing = [field for field in required if field not in present]
        if not retrieval or not retrieval.standards:
            return ConfidenceResult(score=0.0, band="low", should_ask=bool(missing),
                                    signals={"s1": 0.0, "s2": 0.0, "s3": 0.0, "s4": 0.0},
                                    drivers=["no standard matched the description"])

        standards = retrieval.standards
        top = standards[0]
        runner_up = standards[1].score if len(standards) > 1 else 0.0

        # s1: how well the winning clause actually answers the query. C1 attaches an absolute
        # cross-encoder score for this purpose; a fusion score cannot serve, because it is a rank
        # in disguise and the top result would always read as a perfect match.
        s1 = top.match if top.match is not None else self._relative(top.score, standards)

        # s2: the margin. A top score of 0.94 means little when the runner-up scored 0.93.
        if top.match is not None and len(standards) > 1 and standards[1].match is not None:
            best, second = top.match, standards[1].match
        else:
            best, second = (top.score, runner_up) if retrieval.reranked else (
                self._relative(top.score, standards), self._relative(runner_up, standards))
        s2 = min(max(best - second, 0.0) / MARGIN_FULL, 1.0)

        # s3: did we know what we needed to know about the product?
        s3 = 1.0 if not required else len([f for f in required if f in present]) / len(required)

        # s4: does the relationship map agree with the search?
        s4 = float(self._graph_agrees(standards, allied))

        score = round(W_MATCH * s1 + W_MARGIN * s2 + W_FIELDS * s3 + W_GRAPH * s4, 3)

        # A standard matched only on its catalogue title has no clause behind it, so the recommended
        # number may be right while nothing can be quoted to show why. That is worth less than a
        # clause match and must never read as high confidence.
        title_only = getattr(top, "source", "clause") == "title"
        if title_only:
            score = round(min(score, TITLE_ONLY_CEILING), 3)

        band = "high" if score >= HIGH else ("medium" if score >= MEDIUM else "low")
        return ConfidenceResult(
            score=score,
            band=band,
            should_ask=bool(missing),
            signals={"s1": round(s1, 3), "s2": round(s2, 3), "s3": round(s3, 3), "s4": s4},
            drivers=self._drivers(top, s1, s2, s3, s4, missing, title_only),
        )

    # ---------------------------------------------------------------- internals

    @staticmethod
    def _relative(value: float, standards) -> float:
        """Fusion scores are ranks in disguise, so they only mean anything against each other."""
        best = max((s.score for s in standards), default=0.0)
        return round(value / best, 4) if best else 0.0

    @staticmethod
    def _graph_agrees(standards, allied: Optional[AlliedResult]) -> bool:
        """True when a standard C1 also ranked highly appears in C2's expansion of the winner.

        Two independent routes reaching the same neighbourhood is real evidence; one route is not.
        """
        if not allied or not allied.groups or len(standards) < 2:
            return False
        expanded = {a.is_number.replace(" ", "").upper()
                    for group in allied.groups.values() for a in group}
        others = {s.is_number.replace(" ", "").upper() for s in standards[1:]}
        return bool(expanded & others)

    @staticmethod
    def _drivers(top, s1, s2, s3, s4, missing, title_only=False) -> List[str]:
        drivers = []
        if title_only:
            drivers.append(f"matched on the catalogue title of {top.is_number}; we hold no text for "
                           f"it, so no clause can be quoted")
        role = top.evidence.role if top.evidence else ""
        if s1 >= 0.9:
            drivers.append(f"the {role or 'matched'} clause of {top.is_number} matches the description closely")
        elif s1 >= 0.6:
            drivers.append(f"{top.is_number} matches, though not decisively")
        else:
            drivers.append(f"only a weak match to {top.is_number}")
        if s2 >= 0.8:
            drivers.append("it is clearly ahead of the next candidate")
        elif s2 <= 0.2:
            drivers.append("another standard scores almost as highly")
        if missing:
            drivers.append("missing from the description: " + ", ".join(missing))
        elif s3 == 1.0:
            drivers.append("every field this product category needs was given")
        if s4:
            drivers.append("the allied-standards map agrees with the search result")
        return drivers
