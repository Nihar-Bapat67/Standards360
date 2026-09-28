"""Resolve a conversational turn into a retrieval-ready request plan.

This layer interprets user intent and carries forward structured context. It never supplies
authoritative standards data; citations are still extracted from user text and all recommendations
remain the responsibility of the existing catalogue-backed pipeline.
"""

import json
import re
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.llm import LLM
from contracts.requirement import RequirementObject

INTENTS = {
    "standards_recommendation",
    "standard_lookup",
    "citation_validation",
    "allied_standards",
    "test_methods",
    "certification",
    "qco",
    "explain_recommendation",
    "compare_standards",
    "general_question",
}

SYSTEM_PROMPT = """You prepare a procurement standards search from a conversational turn.
Use the prior structured requirement and recent user/assistant messages to resolve references,
follow-ups, and corrections. Return JSON only with keys: intent, product, category, attributes,
missing_information, clarification. Intent must be one of: standards_recommendation,
standard_lookup, citation_validation, allied_standards, test_methods, certification, qco,
explain_recommendation, compare_standards, general_question. Do not output standard numbers,
titles, clauses, status, amendments, or certification facts. Those come only from the authoritative
Standards360 pipeline. Ask a question only when missing information materially affects the request.
"""

GENERAL_ANSWER_PROMPT = """You are Standards360, an assistant for Indian Standards and procurement.
Stay strictly within BIS/Indian Standards, standards-based procurement, tenders, testing methods,
allied references, amendments, certification, and QCOs. If the message is only a greeting, greet the
user briefly and invite a standards-related question. If it is unrelated, do not answer the unrelated
question; politely say you can help only with standards/procurement topics and invite a relevant
question. Use the conversation context for short follow-ups.

Never claim that a standard exists, is current, has amendments, is mandatory, or relates to another
standard unless that fact is present in the supplied Standards360 result/context. Never invent an
IS number, title, clause, BIS relationship, or certification fact. When the supplied context does not
establish an authoritative fact, say it needs to be checked against the catalogue.
"""

GREETING = re.compile(
    r"\s*(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|namaste)[!.?,\s]*",
    re.IGNORECASE,
)
CONTEXTUAL_FOLLOWUP = re.compile(
    r"\s*(?:and\b|what about\b|why\b|is it\b|does it\b|will it\b|how about\b|"
    r"what does that\b|which of those\b|that one\b|those\b)",
    re.IGNORECASE,
)
STANDARDS_DOMAIN = re.compile(
    r"\b(?:standards?|IS\s*\d{2,5}|IS\s+and\s+ISO|ISO\s*\d{2,5}|BIS|Indian Standards?|procurement|tenders?|"
    r"QCO|quality control order|test methods?|allied references?|amendments?|"
    r"certification|ISI mark|compliance|conformity)\b",
    re.IGNORECASE,
)
OUT_OF_SCOPE_REPLY = (
    "I can answer only questions about Indian Standards and standards-based procurement, including "
    "applicable standards, test methods, current editions, and BIS certification. What product or "
    "tender requirement are you working with?"
)
GREETING_REPLY = "Hello! I can help you find or verify Indian Standards for a product or tender."


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = "standards_recommendation"
    product: str = ""
    category: str = ""
    attributes: Dict[str, str] = Field(default_factory=dict)
    missing_information: List[str] = Field(default_factory=list)
    clarification: Optional[str] = None
    retrieval_text: str = ""
    used_model: bool = False
    replace_context: bool = False


class AIQueryOrchestrator:
    """Structure a single turn, using a model when available and safe deterministic context otherwise."""

    def __init__(self, llm: Optional[LLM] = None, allowed_categories: Optional[List[str]] = None):
        self.llm = llm or LLM()
        self.allowed_categories = set(allowed_categories or [])

    def resolve(self, message: str, history: Optional[List[dict]] = None,
                previous: Optional[RequirementObject] = None) -> QueryPlan:
        history = (history or [])[-8:]
        if self.llm and self.llm.available:
            planned = self._with_model(message, history, previous)
            if planned is not None:
                return planned
        return self._deterministic(message, history, previous)

    def answer_general(self, message: str, history: Optional[List[dict]] = None) -> str:
        """Answer in-scope educational questions without pretending to consult BIS data."""
        if GREETING.fullmatch(message or ""):
            return GREETING_REPLY
        if not STANDARDS_DOMAIN.search(message or ""):
            has_context = bool(history and any(str(item.get("text", "")).strip() for item in history))
            if not has_context or not CONTEXTUAL_FOLLOWUP.match(message or ""):
                return OUT_OF_SCOPE_REPLY
        if self.llm and self.llm.available:
            context = json.dumps({"recent_messages": (history or [])[-6:], "question": message[:2000]},
                                 ensure_ascii=False)
            answer = self.llm.complete(GENERAL_ANSWER_PROMPT, context, max_tokens=400)
            if answer:
                return answer.strip()
        if re.search(r"\bdifference between\s+IS\s+and\s+ISO\b", message, re.I):
            return ("IS refers to an Indian Standard published by the Bureau of Indian Standards (BIS). "
                    "ISO refers to an International Standard published by the International Organization "
                    "for Standardization. They are different standards systems; an Indian Standard may "
                    "adopt or align with an ISO standard, but that relationship should be verified for "
                    "the specific standard in the BIS catalogue.")
        return OUT_OF_SCOPE_REPLY

    def _with_model(self, message: str, history: List[dict],
                    previous: Optional[RequirementObject]) -> Optional[QueryPlan]:
        context = {
            "current_message": message[:4000],
            "recent_messages": [
                {"role": item.get("role"), "content": str(item.get("text", ""))[:1000]}
                for item in history
            ],
            "previous_requirement": previous.model_dump() if previous else None,
        }
        result = self.llm.complete_json(SYSTEM_PROMPT, json.dumps(context, ensure_ascii=False),
                                       max_tokens=600)
        if not isinstance(result, dict):
            return None
        try:
            plan = QueryPlan.model_validate({**result, "used_model": True})
        except Exception:
            return None
        if plan.intent not in INTENTS:
            return None
        plan = self._sanitize(plan, message, previous)
        fallback_intent = self._deterministic(message, history, previous).intent
        if fallback_intent == "general_question":
            plan.intent = "general_question"
        elif plan.intent == "general_question":
            plan.intent = fallback_intent
        return plan

    def _deterministic(self, message: str, history: List[dict],
                       previous: Optional[RequirementObject]) -> QueryPlan:
        lowered = message.lower()
        correction = bool(re.match(r"\s*(?:sorry,?\s+)?(?:actually,?\s+)?(?:i meant|I mean|instead)\b", message, re.I))
        if re.search(r"\bdifference between\s+IS\s+and\s+ISO\b", message, re.I):
            intent = "general_question"
        elif re.search(r"\b(?:what is|is|whether|current|latest|amendments? for)\s+(?:the\s+)?IS\s*\d{2,5}", message, re.I):
            intent = "standard_lookup"
        elif re.search(r"\btests?\b|\btesting\b|\btest methods?\b", lowered):
            intent = "test_methods"
        elif re.search(r"\b(certification|certified|license|licence|ISI mark)\b", lowered):
            intent = "certification"
        elif re.search(r"\b(QCO|quality control order)\b", message, re.I):
            intent = "qco"
        elif re.search(r"\b(why|reason)\b", lowered) and previous:
            intent = "explain_recommendation"
        elif re.search(r"\b(compare|difference between)\b", lowered):
            intent = "compare_standards"
        elif re.search(r"\b(allied|related standards)\b", lowered):
            intent = "allied_standards"
        elif re.search(r"\b(keep|replace|remove|validate|check)\b", lowered) and re.search(r"\bIS\s*\d", message, re.I):
            intent = "citation_validation"
        elif GREETING.fullmatch(message or ""):
            intent = "general_question"
        elif re.match(r"\s*(?:i am|i'm|we are|we're|i work as|we manufacture)\b", lowered):
            intent = "general_question"
        elif re.search(r"\b(standard|standards|IS\s*\d|procure|procurement|supply|conform)\b", lowered):
            intent = "standards_recommendation"
        elif re.match(r"\s*(who|what|when|where|how|why|explain|define|tell me)\b", lowered):
            intent = "general_question"
        elif re.search(r"\b(cement|concrete|steel|pipe|pipes|tube|tubes|aggregate|"
                       r"reinforcement|tmt|opc|ppc|hdpe|pvc|ductile iron|structural)\b", lowered):
            intent = "standards_recommendation"
        else:
            intent = "general_question"

        context = None if correction else previous
        product = context.product if context else ""
        category = context.category if context else ""
        attributes = dict(context.attributes) if context else {}
        if context and message.strip():
            attributes = self._merge_follow_up(attributes, message)
        turn = re.sub(r"^\s*(?:sorry,?\s+)?(?:actually,?\s+)?(?:i meant|I mean|instead)\s+", "", message, flags=re.I) if correction else message
        retrieval_text = " ".join(part for part in [product, *attributes.values(), turn.strip()] if part)
        return QueryPlan(intent=intent, product=product, category=category,
                         attributes=attributes, retrieval_text=retrieval_text,
                         replace_context=correction)

    def _sanitize(self, plan: QueryPlan, message: str,
                  previous: Optional[RequirementObject]) -> QueryPlan:
        allowed_keys = {"type", "grade", "application", "diameter", "thickness", "pressure_class",
                        "size", "material", "quantity"}
        correction = bool(re.match(r"\s*(?:sorry,?\s+)?(?:actually,?\s+)?(?:i meant|I mean|instead)\b", message, re.I))
        context = None if correction else previous
        attrs = dict(context.attributes) if context else {}
        for key, value in plan.attributes.items():
            normalized = re.sub(r"\W+", "_", key.lower()).strip("_")
            if normalized in allowed_keys and isinstance(value, str) and value.strip():
                attrs[normalized] = value.strip()[:120]
        if plan.category and self.allowed_categories and plan.category not in self.allowed_categories:
            plan.category = context.category if context else ""
        plan.product = (plan.product or (context.product if context else "")).strip()[:120]
        plan.attributes = attrs
        plan.replace_context = correction
        # Standard identifiers are deliberately sourced only from the user's messages, never model output.
        turn = re.sub(r"^\s*(?:sorry,?\s+)?(?:actually,?\s+)?(?:i meant|I mean|instead)\s+", "", message, flags=re.I) if correction else message
        plan.retrieval_text = " ".join(part for part in [plan.product, *attrs.values(), turn.strip()] if part)
        return plan

    @staticmethod
    def _merge_follow_up(attributes: Dict[str, str], message: str) -> Dict[str, str]:
        """Deterministically attach common short answers to the prior requirement."""
        text = message.strip()
        lowered = text.lower()
        if len(text.split()) <= 8:
            if any(word in lowered for word in ("water supply", "water distribution", "drinking water", "irrigation", "drainage", "sewage")):
                attributes["application"] = text
            elif re.search(r"\b(?:\d{2,3}\s*grade|OPC\s*\d{2}|PPC|PSC)\b", text, re.I):
                attributes["grade"] = text
            elif re.search(r"\b(?:OPC|PPC|PSC|PVC|uPVC|HDPE|CPVC|ductile iron)\b", text, re.I):
                attributes["type"] = text
            elif not re.match(r"^(sorry|actually|i meant)\b", lowered):
                attributes["application"] = text
        else:
            attributes["context"] = text[:120]
        return attributes