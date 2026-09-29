"""Tests for B1 (input handling), B3 (requirement extraction) and C5 (confidence).

B3 is tested with the language model switched off, so the rules layer is what is measured. That is
deliberate: the rules are what the system falls back to when there is no key, no network, or a
confidential document that must not leave the machine.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HAS_DB = (ROOT / "data" / "catalogue.db").exists()
pytestmark = pytest.mark.skipif(not HAS_DB, reason="catalogue.db is git-ignored; run the A1 loader")

from app.core.confidence import ConfidenceScorer  # noqa: E402
from app.understand.extractor import RequirementExtractor  # noqa: E402
from app.understand.input_handler import InputHandler  # noqa: E402
from contracts.retrieval import AlliedResult, AlliedStandard, Evidence, RetrievalResult, RetrievedStandard  # noqa: E402


@pytest.fixture(scope="module")
def extractor():
    """Rules only: no key, no network, so the offline path is what these tests cover."""
    return RequirementExtractor(use_llm=False)


# ---------------------------------------------------------------- B1

def test_short_text_is_recognised_as_a_product_name():
    payload = InputHandler().read_text("steel tubes")
    assert payload.source == "product_name"
    assert payload.richness == "name_only"


def test_a_specification_paragraph_is_not_a_product_name():
    payload = InputHandler().read_text(
        "Supply of 500 MT ordinary Portland cement, 43 grade, for RCC structural work as per IS 8112")
    assert payload.richness == "spec_only"
    assert "Portland" in payload.text


def test_pdf_is_read_with_its_page_count():
    pdfs = sorted((ROOT / "data" / "raw" / "bis_pdf").glob("*.pdf")) if (ROOT / "data" / "raw" / "bis_pdf").exists() else []
    if not pdfs:
        pytest.skip("no PDFs available locally")
    payload = InputHandler().read(str(pdfs[0]))
    assert payload.source == "pdf"
    assert payload.pages > 0
    assert len(payload.text) > 200


def test_unsupported_file_type_is_refused(tmp_path):
    odd = tmp_path / "spec.xyz"
    odd.write_text("some text", encoding="utf-8")
    with pytest.raises(ValueError):
        InputHandler().read(str(odd))


# ---------------------------------------------------------------- B3

def test_cited_standards_are_extracted_and_normalised(extractor):
    requirement = extractor.extract(
        "Cement shall conform to IS 8112:1989, IS-456 : 2000 and IS 4031 (Part 1).")
    assert "IS 8112:1989" in requirement.cited_standards
    assert "IS 456:2000" in requirement.cited_standards
    assert any(c.startswith("IS 4031") for c in requirement.cited_standards)


def test_attributes_and_category_come_from_the_text(extractor):
    requirement = extractor.extract(
        "Supply of 500 MT ordinary Portland cement, 43 grade, for RCC structural work")
    assert requirement.category == "cement"
    assert requirement.attributes.get("quantity", "").startswith("500")
    assert "43" in requirement.attributes.get("grade", "")
    assert "RCC" in requirement.attributes.get("application", "")


def test_missing_fields_become_questions(extractor):
    requirement = extractor.extract("steel tubes")
    assert requirement.category == "steel_tubes"
    assert set(requirement.not_specified) == {"type", "application"}
    questions = extractor.questions_for(requirement)
    assert len(questions) == 2
    assert all(q["ask"] for q in questions)


def test_structural_steel_tube_query_uses_tube_fields(extractor):
    requirement = extractor.extract(
        "Supply of 200 MT structural steel tubes YSt 240, 50 NB medium class, "
        "for pipe truss of an industrial shed")

    assert requirement.category == "steel_tubes"
    assert requirement.attributes["application"] == "pipe truss of an industrial shed"
    assert requirement.not_specified == ["type"]
    assert extractor.questions_for(requirement)[0]["ask"].startswith("Seamless, electric resistance welded")


def test_a_type_already_stated_is_not_asked_about(extractor):
    requirement = extractor.extract(
        "Galvanized mild steel tubes, medium class, 25 mm nominal bore, for internal water supply")
    assert "type" not in requirement.not_specified
    assert requirement.attributes["type"].lower().startswith("galvani")


def test_rules_only_extraction_is_marked_as_such(extractor):
    assert extractor.extract("43 grade OPC").extracted_by == "rules"


# ---------------------------------------------------------------- C5

def _result(scores, matches=None):
    matches = matches or scores
    return RetrievalResult(
        query="q",
        standards=[
            RetrievedStandard(is_number=f"IS {100 + i}:2020", score=s, match=m,
                              evidence=Evidence(clause="1", clause_id=f"IS {100 + i}:2020#1",
                                                role="scope", quote="..."))
            for i, (s, m) in enumerate(zip(scores, matches))
        ],
    )


def test_a_strong_unambiguous_match_scores_high():
    result = ConfidenceScorer().score(_result([0.99, 0.30]), required=["grade"], present=["grade"])
    assert result.band == "high"
    assert result.should_ask is False


def test_a_close_second_place_lowers_confidence():
    close = ConfidenceScorer().score(_result([0.99, 0.98]), required=["grade"], present=["grade"])
    clear = ConfidenceScorer().score(_result([0.99, 0.30]), required=["grade"], present=["grade"])
    assert close.score < clear.score
    assert "another standard scores almost as highly" in close.drivers


def test_missing_required_fields_force_a_question():
    result = ConfidenceScorer().score(_result([0.99, 0.10]), required=["type", "application"], present=[])
    assert result.should_ask is True
    assert any("missing" in d for d in result.drivers)


def test_graph_agreement_adds_to_the_score():
    retrieval = _result([0.99, 0.60])
    allied = AlliedResult(seeds=["IS 100:2020"], total=1, groups={
        "test_method": [AlliedStandard(is_number="IS 101:2020", relation="test_method", weight=0.95, hops=1)]})
    with_graph = ConfidenceScorer().score(retrieval, allied, required=[], present=[])
    without_graph = ConfidenceScorer().score(retrieval, None, required=[], present=[])
    assert with_graph.score > without_graph.score
    assert with_graph.signals["s4"] == 1.0


def test_no_results_means_no_confidence():
    result = ConfidenceScorer().score(RetrievalResult(query="q"))
    assert result.score == 0.0
    assert result.band == "low"
    assert result.should_ask is False


def test_no_results_asks_only_when_required_fields_are_missing():
    result = ConfidenceScorer().score(RetrievalResult(query="q"), required=["application"], present=[])
    assert result.should_ask is True
