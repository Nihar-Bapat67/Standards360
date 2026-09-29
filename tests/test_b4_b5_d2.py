"""Tests for B4 (citation verdicts), B5 (the sufficiency gate) and D2 (the composer).

B4's relevance judgement needs the index; those tests skip without it. Everything else runs on the
catalogue alone, and the language model is switched off so the deterministic paths are what is
measured.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HAS_DB = (ROOT / "data" / "catalogue.db").exists()
HAS_INDEX = (ROOT / "data" / "index" / "faiss.index").exists()
pytestmark = pytest.mark.skipif(not HAS_DB, reason="catalogue.db is git-ignored; run the A1 loader")

from app.core.confidence import ConfidenceResult  # noqa: E402
from app.deliver.composer import Composer  # noqa: E402
from app.understand.citation_validator import CitationValidator  # noqa: E402
from app.understand.extractor import RequirementExtractor  # noqa: E402
from app.understand.sufficiency import SufficiencyGate  # noqa: E402
from contracts.requirement import RequirementObject  # noqa: E402
from contracts.retrieval import (  # noqa: E402
    AlliedResult, AlliedStandard, Evidence, RetrievalResult, RetrievedStandard,
)


@pytest.fixture(scope="module")
def validator():
    """No retrieval engine: existence and currency only, which is the offline path."""
    return CitationValidator()


@pytest.fixture(scope="module")
def gate():
    return SufficiencyGate(extractor=RequirementExtractor(use_llm=False), use_llm=False)


# ---------------------------------------------------------------- B4

def test_superseded_citation_is_replaced(validator):
    verdict = validator.validate(["IS 12269:2013"])[0]
    assert verdict.verdict == "replace"
    assert verdict.replacement == "IS 269:2015"
    assert verdict.severity.value == "high"


def test_older_edition_is_replaced_not_kept(validator):
    """A tender citing a year BIS never published must not be reported as correct."""
    verdict = validator.validate(["IS 1161:1998"])[0]
    assert verdict.verdict == "replace"
    assert verdict.replacement == "IS 1161:2014"


def test_invented_number_is_removed(validator):
    verdict = validator.validate(["IS 99999:2021"])[0]
    assert verdict.verdict == "remove"
    assert verdict.exists is False


def test_current_citation_without_an_engine_is_flagged_for_verification(validator):
    """Without retrieval we cannot judge relevance, and silence is not a verdict."""
    verdict = validator.validate(["IS 269:2015"])[0]
    assert verdict.verdict == "verify"
    assert verdict.relevant is None


def test_recommended_standards_the_tender_omitted_are_added(validator):
    verdicts = validator.validate(["IS 269:2015"], recommended=["IS 4031 (Part 1):1996"])
    added = [v for v in verdicts if v.verdict == "add"]
    assert added and added[0].citation == "IS 4031 (Part 1):1996"


def test_a_replacement_is_not_also_reported_as_missing(validator):
    verdicts = validator.validate(["IS 12269:2013"], recommended=["IS 269:2015"])
    assert [v.verdict for v in verdicts] == ["replace"]


@pytest.mark.skipif(not HAS_INDEX, reason="data/index is git-ignored; run the A4 builder")
def test_irrelevant_citation_is_detected_with_the_engine():
    from app.core.retrieval import RetrievalEngine
    validator = CitationValidator(engine=RetrievalEngine())
    verdict = validator.validate(["IS 1786:2008"], query="structural steel tubes for pipe truss")[0]
    assert verdict.verdict == "remove"
    assert verdict.relevant is False


# ---------------------------------------------------------------- B5

def _requirement(**kwargs):
    base = dict(product="steel tubes", category="steel_tubes", attributes={},
                not_specified=["type", "application"])
    base.update(kwargs)
    return RequirementObject(**base)


def _confidence(score):
    return ConfidenceResult(score=score, band="high" if score >= 0.75 else "low",
                            should_ask=False, signals={}, drivers=[])


def test_missing_fields_produce_questions(gate):
    result = gate.check(_requirement(), _confidence(0.80))
    assert result.status == "need_more_info"
    assert {q["field"] for q in result.questions} == {"type", "application"}
    assert result.can_proceed_anyway is True


def test_complete_requirement_with_good_confidence_proceeds(gate):
    result = gate.check(_requirement(attributes={"type": "seamless", "application": "structural"},
                                     not_specified=[]), _confidence(0.82))
    assert result.status == "ok"
    assert result.questions == []


def test_low_confidence_does_not_ask_when_required_fields_are_present(gate):
    result = gate.check(_requirement(attributes={"type": "seamless", "application": "structural"},
                                     not_specified=[]), _confidence(0.35))
    assert result.status == "ok"
    assert result.questions == []


def test_answers_are_merged_and_the_gap_closes(gate):
    requirement = _requirement()
    merged = gate.apply_answers(requirement, {"type": "seamless", "application": "structural use"})
    assert merged.attributes["type"] == "seamless"
    assert merged.not_specified == []
    assert requirement.not_specified == ["type", "application"]      # the original is untouched


def test_at_most_three_questions_are_asked(gate):
    requirement = RequirementObject(product="pipe", category="pipes_plastic",
                                    not_specified=["material", "diameter", "pressure_class"])
    assert len(gate.check(requirement, _confidence(0.2)).questions) <= 3


# ---------------------------------------------------------------- D2

def _retrieval(is_number="IS 1161:2014"):
    return RetrievalResult(query="steel tubes", standards=[
        RetrievedStandard(is_number=is_number, record_id=2740, title="Steel tubes for structural purposes",
                          score=0.98, match=0.98,
                          evidence=Evidence(clause="1", clause_id=f"{is_number}#1", role="scope",
                                            quote="This standard covers steel tubes..."))])


def _allied():
    return AlliedResult(seeds=["IS 1161:2014"], total=2, groups={
        "test_method": [AlliedStandard(is_number="IS 1608 (Part 1):2022", relation="test_method",
                                       weight=0.95, hops=1, title="Tensile testing")],
        "related_product": [AlliedStandard(is_number="IS 1239 (Part 1):2004", relation="related_product",
                                           weight=0.60, hops=1, title="Steel tubes")]})


def test_every_depth_names_the_same_primary_standard():
    recommendation = Composer(use_llm=False).compose(
        _requirement(), _retrieval(), _allied(), _confidence(0.8))
    assert recommendation.primary == "IS 1161:2014"
    assert len(recommendation.options) == 3
    assert all(o.standards[0] == "IS 1161:2014" for o in recommendation.options)


def test_depths_grow_and_the_middle_one_is_the_default():
    recommendation = Composer(use_llm=False).compose(
        _requirement(), _retrieval(), _allied(), _confidence(0.8))
    a, b, c = recommendation.options
    assert len(a.standards) <= len(b.standards) <= len(c.standards)
    assert b.default is True
    assert "IS 1608 (Part 1):2022" in b.standards            # a test method belongs at depth B
    assert "IS 1239 (Part 1):2004" in c.standards            # a related product only at depth C


def test_explanation_passes_the_validity_guard():
    recommendation = Composer(use_llm=False).compose(
        _requirement(), _retrieval(), _allied(), _confidence(0.8))
    assert "IS 1161:2014" in recommendation.explanation
    assert recommendation.removed_by_guard == []


def test_no_retrieval_result_is_reported_honestly():
    recommendation = Composer(use_llm=False).compose(
        _requirement(), RetrievalResult(query="something obscure"))
    assert recommendation.status == "no_match"
    assert recommendation.primary is None
    assert "no" in recommendation.explanation.lower()
