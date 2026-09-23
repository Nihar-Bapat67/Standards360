"""Tests for C3 (version resolution), C4 (certification) and D1 (validity guard).

These run against the real catalogue, because that is the point of the three modules: they make no
inferences, so a test against fixtures would only prove the fixtures. Every expectation below was
verified on the BIS portal data held in data/catalogue.db.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.skipif(not (ROOT / "data" / "catalogue.db").exists(),
                                reason="catalogue.db is git-ignored; run `python ingest/collect.py load`")

from app.core.certification import CertificationEngine  # noqa: E402
from app.core.version_resolver import VersionResolver  # noqa: E402
from app.deliver.validity_guard import ValidityGuard  # noqa: E402
from contracts.analysis import CitationStatus, Severity  # noqa: E402


@pytest.fixture(scope="module")
def resolver():
    return VersionResolver()


@pytest.fixture(scope="module")
def certification():
    return CertificationEngine()


@pytest.fixture(scope="module")
def guard():
    return ValidityGuard()


# ---------------------------------------------------------------- C3

def test_current_standard_is_reported_as_current(resolver):
    result = resolver.resolve("IS 269:2015")
    assert result.status is CitationStatus.CURRENT
    assert result.current == "IS 269:2015"
    assert not [w for w in result.warnings if w.severity is Severity.HIGH]


def test_withdrawn_standard_resolves_to_its_replacement(resolver):
    result = resolver.resolve("IS 12269:2013")
    assert result.status is CitationStatus.SUPERSEDED
    assert result.current == "IS 269:2015"
    assert result.replacement_chain[-1] == "IS 269:2015"
    assert any(w.severity is Severity.HIGH for w in result.warnings)


def test_old_year_of_a_superseded_family_is_high_severity(resolver):
    """The tender case from the manual: IS 8112:1989 was never in the catalogue, but the family
    has been merged into IS 269, so this is a defect rather than version drift."""
    result = resolver.resolve("IS 8112:1989")
    assert result.current == "IS 269:2015"
    assert any(w.severity is Severity.HIGH for w in result.warnings)


def test_bare_family_number_means_the_current_edition(resolver):
    result = resolver.resolve("IS 1161")
    assert result.status is CitationStatus.CURRENT
    assert result.current == "IS 1161:2014"


def test_unknown_number_is_not_found(resolver):
    result = resolver.resolve("IS 99999:2021")
    assert result.status is CitationStatus.NOT_FOUND
    assert result.exists is False


def test_amendments_are_attached_and_reported_as_low_severity(resolver):
    result = resolver.resolve("IS 456:2000")
    assert result.amendments
    assert any(w.severity is Severity.LOW for w in result.warnings)


def test_identifier_variants_resolve_alike(resolver):
    for variant in ("IS 1161:2014", "IS-1161", "I.S. 1161 : 2014", "IS 1161 : 2014"):
        assert resolver.resolve(variant).current == "IS 1161:2014"


# ---------------------------------------------------------------- C4

def test_mandatory_certification_is_reported_with_its_qco_date(certification):
    answer = certification.for_standards(["IS 269:2015"], persona="procurement")
    assert answer.certification_required
    assert answer.standards[0].qco_date == "2003-02-17"
    assert answer.standards[0].in_force is True
    assert answer.standards[0].labs_available > 0
    assert "eligibility condition" in answer.statement


def test_blank_certification_is_not_stated_rather_than_not_required(certification):
    answer = certification.for_standards(["IS 4031 (Part 1)"], persona="procurement")
    assert answer.certification_required is False
    assert answer.not_stated
    assert "not a statement that certification is unnecessary" in answer.statement


def test_persona_changes_the_wording_not_the_facts(certification):
    buyer = certification.for_standards(["IS 1161:2014"], persona="procurement")
    maker = certification.for_standards(["IS 1161:2014"], persona="manufacturer")
    assert buyer.standards[0].qco_date == maker.standards[0].qco_date
    assert "Bidders" in buyer.statement
    assert "You must hold" in maker.statement


def test_scheme_inference_is_returned_with_its_basis(certification):
    electrical = certification.for_standards(["IS 694:2010"])
    assert "CRS" in electrical.standards[0].scheme
    assert electrical.standards[0].scheme_basis


def test_labs_in_the_requested_state_come_first(certification):
    answer = certification.for_standards(["IS 269:2015"], state="Maharashtra")
    assert answer.nearest_labs
    assert answer.nearest_labs[0].state.lower() == "maharashtra"


# ---------------------------------------------------------------- D1

def test_invented_number_is_removed_and_sentence_stays_readable(guard):
    result = guard.check("Refer IS 269:2015 and also IS 99999:2021 for testing.")
    assert result.text == "Refer IS 269:2015 for testing."
    assert result.removed == ["IS 99999:2021"]
    assert result.reasons["IS 99999:2021"] == "not in catalogue"


def test_real_standards_are_kept(guard):
    text = "Cement shall conform to IS 269:2015 and be tested per IS 4031 (Part 1):1996."
    result = guard.check(text)
    assert result.clean
    assert result.text == text


def test_overlong_number_cannot_pass_as_a_prefix(guard):
    result = guard.check("Bidders shall comply with IS 12345678.")
    assert "IS 12345678" in result.removed[0]


def test_allowed_list_blocks_a_standard_the_pipeline_did_not_retrieve(guard):
    result = guard.check("Use IS 1161:2014 and IS 456:2000.", allowed=["IS 1161:2014"])
    assert "IS 456:2000" in result.removed
    assert result.reasons["IS 456:2000"] == "not among the standards this answer retrieved"


def test_withdrawn_standards_are_kept_because_they_exist(guard):
    """D1 checks existence only. Currency is C3's judgement, and a withdrawn standard is real."""
    result = guard.check("The tender cites IS 12269:2013.")
    assert result.clean


def test_text_without_citations_is_untouched(guard):
    result = guard.check("No standards are mentioned in this sentence.")
    assert result.clean
