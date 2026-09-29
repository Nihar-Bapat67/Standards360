"""Module B5: Sufficiency Gate and Clarifier, for scenario S5 (and it rescues S3 and S4).

Checks whether required product details are missing. If so, it asks for those facts, one short
question at a time, in the user's own language. Retrieval confidence still affects the confidence
band, but low confidence alone does not interrupt the user with a clarification.

The required-field table is hand written per category and lives in `config/required_fields.yaml`.
It turns a missing product detail into a specific, answerable question.

The gate never guesses and never silently proceeds, but it also never blocks: `can_proceed_anyway`
lets a user accept a weaker answer deliberately.

    from app.understand.sufficiency import SufficiencyGate
    gate = SufficiencyGate()
    gate.check(requirement, confidence)
    gate.apply_answers(requirement, {"type": "seamless"})
"""

import sys
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.confidence import ConfidenceResult  # noqa: E402
from app.llm import LLM  # noqa: E402
from app.understand.extractor import RequirementExtractor  # noqa: E402
from contracts.answer import SufficiencyResult  # noqa: E402
from contracts.requirement import RequirementObject  # noqa: E402

MAX_QUESTIONS = 3       # two or three short questions, never an interrogation
TRANSLATE_PROMPT = ("Translate each question into {language}. Keep them short and natural for a "
                    "government procurement officer. Reply with one JSON object mapping the original "
                    "English question to its translation, and nothing else.")


class SufficiencyGate:
    def __init__(self, extractor: Optional[RequirementExtractor] = None, llm: Optional[LLM] = None,
                 use_llm: bool = True):
        self.extractor = extractor or RequirementExtractor(use_llm=use_llm)
        self.llm = llm or (LLM() if use_llm else None)

    # ---------------------------------------------------------------- public

    def check(self, requirement: RequirementObject,
              confidence: Optional[ConfidenceResult] = None) -> SufficiencyResult:
        """Proceed, or ask for exactly what is missing."""
        score = confidence.score if confidence else 0.0
        band = confidence.band if confidence else "low"
        drivers = confidence.drivers if confidence else []
        missing = list(requirement.not_specified)

        if not missing:
            return SufficiencyResult(status="ok", confidence=score, band=band,
                                     missing=[], questions=[], can_proceed_anyway=True,
                                     drivers=drivers)

        questions = self.extractor.questions_for(requirement)[:MAX_QUESTIONS]
        if requirement.language and requirement.language != "en":
            questions = self._translate(questions, requirement.language)

        return SufficiencyResult(status="need_more_info", confidence=score, band=band,
                                 missing=missing, questions=questions,
                                 can_proceed_anyway=True, drivers=drivers)

    def apply_answers(self, requirement: RequirementObject,
                      answers: Dict[str, str]) -> RequirementObject:
        """Merge the user's replies back into the requirement and re-check what is still missing.

        This is the only genuine loop in the system, and it closes here: the merged requirement goes
        back through retrieval exactly as a first-time request would.
        """
        merged = requirement.model_copy(deep=True)
        for field, value in (answers or {}).items():
            value = (value or "").strip()
            if not value:
                continue
            if field == "description":
                merged.product = f"{merged.product} {value}".strip()[:120]
            else:
                merged.attributes[field] = value[:80]
        required = self.extractor.fields.get(merged.category, {}).get("required", [])
        merged.not_specified = [f for f in required if f not in merged.attributes]
        return merged

    # ---------------------------------------------------------------- internals

    def _translate(self, questions, language: str):
        """Ask the model to translate the questions. Without a key, the English text is kept."""
        if not (self.llm and self.llm.available and questions):
            return questions
        payload = "\n".join(q["ask"] for q in questions)
        mapping = self.llm.complete_json(TRANSLATE_PROMPT.format(language=language), payload,
                                         max_tokens=400)
        if not isinstance(mapping, dict):
            return questions
        return [{**q, "ask": mapping.get(q["ask"], q["ask"])} for q in questions]
