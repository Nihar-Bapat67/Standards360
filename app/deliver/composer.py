"""Module D2: Recommendation Composer.

Assembles everything upstream into **one** recommendation with an adjustable breadth. All three
depths name the same primary standard; they differ only in how many allied standards travel with it.
That is the "options with confidence" requirement, and it is honest, because the right amount of
citation genuinely depends on the tender's value and risk, which is the user's call and not ours.

This is not the top three standards. C1 returns a ranked list of candidates; D2 returns depth levels.
Presenting them as three competing guesses would destroy the user's confidence for no reason.

The only sentence a model writes is the explanation, and it is written from a fixed list of numbers
and then passed through D1 before it leaves this module.

    from app.deliver.composer import Composer
    Composer().compose(requirement, retrieval, allied, confidence, verdicts, certification)
"""

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.version_resolver import VersionResolver  # noqa: E402
from app.deliver.validity_guard import ValidityGuard  # noqa: E402
from app.llm import LLM  # noqa: E402
from contracts.analysis import CertificationAnswer, VersionWarning  # noqa: E402
from contracts.answer import CitationVerdict, DepthOption, Recommendation  # noqa: E402
from contracts.requirement import RequirementObject  # noqa: E402
from contracts.retrieval import AlliedResult, RetrievalResult  # noqa: E402

# Which relations belong at which depth. Depth B is what a careful officer would cite; depth C adds
# the context standards that matter on a high-value or high-risk tender.
DEPTH_B_RELATIONS = ("normative_reference", "test_method", "terminology", "safety")
DEPTH_C_RELATIONS = DEPTH_B_RELATIONS + ("installation", "related_product", "same_family_part")
DEPTH_B_LIMIT, DEPTH_C_LIMIT = 6, 12

SYSTEM_PROMPT = (
    "You write one short paragraph for an Indian government tender, in plain formal English. "
    "You may mention ONLY the standard numbers given to you, exactly as written. Never invent a "
    "standard number, a date, a price or a test result. State what the primary standard covers, why "
    "the allied standards are cited, and any warning you are given. Three sentences at most."
)


class Composer:
    def __init__(self, llm: Optional[LLM] = None, guard: Optional[ValidityGuard] = None,
                 resolver: Optional[VersionResolver] = None, use_llm: bool = True):
        self.llm = llm or (LLM() if use_llm else None)
        self.guard = guard or ValidityGuard()
        self.resolver = resolver or VersionResolver()

    # ---------------------------------------------------------------- public

    def compose(self, requirement: RequirementObject, retrieval: RetrievalResult,
                allied: Optional[AlliedResult] = None, confidence=None,
                verdicts: Optional[List[CitationVerdict]] = None,
                certification: Optional[CertificationAnswer] = None,
                warnings: Optional[List[VersionWarning]] = None) -> Recommendation:
        if not retrieval or not retrieval.standards:
            return Recommendation(
                status="no_match",
                explanation="No Indian Standard in the indexed corpus matches this description "
                            "closely enough to recommend. The catalogue may still hold one; the "
                            "text for it has not been ingested.",
                confidence=0.0, band="low",
                verdicts=verdicts or [], warnings=warnings or [], certification=certification)

        top = retrieval.standards[0]
        resolved = self.resolver.resolve(top.is_number)
        primary = resolved.current or top.is_number
        groups = (allied.groups if allied else {})

        options = self._depths(primary, groups)
        allowed = [primary] + [s for option in options for s in option.standards]
        allowed += [v.replacement for v in (verdicts or []) if v.replacement]

        # The paragraph speaks about the recommended standard, so only its own warnings go into the
        # prompt. Warnings about what the tender cited belong in the citation-review table, and
        # mixing them produced sentences implying the recommended standard had been withdrawn.
        own_warnings = [w for w in (warnings or []) if w.cited in (primary, top.is_number)]
        explanation, removed = self._explain(requirement, primary, resolved.title or top.title,
                                             options, own_warnings or resolved.warnings, allowed)

        return Recommendation(
            primary=primary,
            primary_title=resolved.title or top.title,
            confidence=confidence.score if confidence else 0.0,
            band=confidence.band if confidence else "low",
            evidence=top.evidence,
            options=options,
            allied=groups,
            verdicts=verdicts or [],
            # The pipeline collects warnings from the primary and from every cited standard, so the
            # same sentence can arrive twice. A tender annexure must not repeat itself.
            warnings=self._unique(list(warnings or []) + resolved.warnings),
            certification=certification,
            explanation=explanation,
            removed_by_guard=removed,
            status="complete",
        )

    # ---------------------------------------------------------------- internals

    @staticmethod
    def _depths(primary: str, groups) -> List[DepthOption]:
        """Three depths over the same primary standard."""
        def pick(relations, limit):
            chosen = []
            for relation in relations:
                for allied in groups.get(relation, []):
                    if allied.is_number != primary and allied.is_number not in chosen:
                        chosen.append(allied.is_number)
            return chosen[:limit]

        depth_b = pick(DEPTH_B_RELATIONS, DEPTH_B_LIMIT)
        depth_c = pick(DEPTH_C_RELATIONS, DEPTH_C_LIMIT)
        return [
            DepthOption(id="A", label="Mandatory only", standards=[primary],
                        rationale="The product standard alone. Use for low-value purchases."),
            DepthOption(id="B", label="Recommended", standards=[primary] + depth_b, default=True,
                        rationale="The product standard with its normative references, test methods "
                                  "and terminology. This is what a complete tender normally cites."),
            DepthOption(id="C", label="Comprehensive", standards=[primary] + depth_c,
                        rationale="Adds installation and related product standards, for high-value "
                                  "or high-risk work."),
        ]

    def _explain(self, requirement, primary, title, options, warnings, allowed):
        """One constrained sentence or three, then D1. Falls back to a deterministic sentence."""
        recommended = next((o for o in options if o.default), options[0])
        allied = [s for s in recommended.standards if s != primary]
        deterministic = self._plain_sentence(primary, title, allied, warnings)

        if not (self.llm and self.llm.available):
            checked = self.guard.check(deterministic, allowed=allowed)
            return checked.text, checked.removed

        prompt = (
            f"Product described by the officer: {requirement.product or 'not stated'}"
            f"{', ' + ', '.join(f'{k}: {v}' for k, v in list(requirement.attributes.items())[:4]) if requirement.attributes else ''}.\n"
            f"Primary standard: {primary} — {title}.\n"
            f"Allied standards you may mention: {', '.join(allied) if allied else 'none'}.\n"
            f"Warnings to convey: {'; '.join(w.message for w in warnings[:3]) if warnings else 'none'}.\n"
            "Write the paragraph."
        )
        written = self.llm.complete(SYSTEM_PROMPT, prompt, max_tokens=400)
        checked = self.guard.check(written or deterministic, allowed=allowed)
        # A generated paragraph that loses its numbers to the guard is worse than the plain one.
        if not checked.text.strip() or len(checked.removed) > 1:
            fallback = self.guard.check(deterministic, allowed=allowed)
            return fallback.text, checked.removed
        return checked.text, checked.removed

    @staticmethod
    def _unique(warnings: List[VersionWarning]) -> List[VersionWarning]:
        seen, out = set(), []
        for warning in warnings:
            key = (warning.severity, warning.message)
            if key not in seen:
                seen.add(key)
                out.append(warning)
        return out

    @staticmethod
    def _plain_sentence(primary, title, allied, warnings) -> str:
        parts = [f"{primary} ({title}) is the applicable Indian Standard for this item."]
        if allied:
            parts.append("It should be cited together with " + ", ".join(allied) +
                         ", which cover the referenced requirements and test methods.")
        for warning in (warnings or [])[:2]:
            parts.append(warning.message)
        return " ".join(parts)
