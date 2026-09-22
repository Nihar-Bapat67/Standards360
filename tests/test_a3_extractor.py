"""Unit tests for Module A3: Cross-Reference Extractor.

Tests IS identifier normalizer, citation regex detection, false-positive rejection traps,
semantic relation classification, and deterministic serialization.
"""

import json
import pytest

from common.is_normalizer import (
    parse_is_number,
    norm_is_lookup_key,
    is_same_standard_family,
)
from contracts.edge import RelationType, EdgeRecord
from ingest.extract_refs import (
    CatalogueReferenceStore,
    process_clause_citations,
    classify_relation,
)


def test_is_normalizer_formats():
    # Various real-world formats
    res1 = parse_is_number("IS 269:2015")
    assert res1.family == "IS 269"
    assert res1.year == 2015
    assert res1.part is None
    assert res1.canonical == "IS 269:2015"

    res2 = parse_is_number("IS-269")
    assert res2.family == "IS 269"
    assert res2.year is None

    res3 = parse_is_number("I.S. 269")
    assert res3.family == "IS 269"

    # Part notation
    res4 = parse_is_number("IS 10124 (Part 1)")
    assert res4.family == "IS 10124 (Part 1)"
    assert res4.part == "1"

    # Roman numerals in Part
    res5 = parse_is_number("IS 432 (Part II):1982")
    assert res5.family == "IS 432 (Part 2)"
    assert res5.part == "2"
    assert res5.year == 1982


def test_lookup_key_roman_normalization():
    # Normalizer converts Roman numerals so Part II matches Part 2 in catalogue lookup
    key_roman = norm_is_lookup_key("IS 432 (Part II)")
    key_arabic = norm_is_lookup_key("IS 432 (Part 2)")
    assert key_roman == key_arabic


def test_same_standard_family():
    assert is_same_standard_family("IS 456 (Part 1)", "IS 456 (Part 2)") is True
    assert is_same_standard_family("IS 269:1989", "IS 269:2015") is True
    assert is_same_standard_family("IS 269", "IS 455") is False


def test_false_positive_rejection():
    # Mock catalogue
    class MockCat:
        def is_in_catalogue(self, target): return True
        def get_aspect(self, target): return "Product Specification"

    mock_cat = MockCat()

    # 1. Reflexive self-header mention (IS 269 citing IS 269 without part diff)
    clause_self = {
        "is": "IS 269:1989",
        "clause_id": "IS 269:1989#1",
        "role": "scope",
        "title": "Scope",
        "text": "1. Scope — Covers requirements of 33 grade ordinary Portland cement according to IS 269:1989.",
    }
    edges, n_found, n_rej = process_clause_citations(clause_self, mock_cat)
    # Self-citation must be rejected
    assert len(edges) == 0
    assert n_found == 1
    assert n_rej == 1

    # 2. Price figures with IS
    clause_price = {
        "is": "IS 500:1990",
        "clause_id": "IS 500:1990#2",
        "role": "requirements",
        "title": "Requirements",
        "text": "Price Rs. IS 200 per meter.",
    }
    edges_p, n_f_p, n_r_p = process_clause_citations(clause_price, mock_cat)
    assert len(edges_p) == 0


def test_same_family_part_classification():
    # Standard citing different part of its own family
    src = parse_is_number("IS 10124 (Part 10):1988")
    tgt = parse_is_number("IS 10124 (Part 1):1988")
    ev = "Requirements shall conform to IS 10124 (Part 1) : 1988."
    rel, conf = classify_relation(src, tgt, "requirements", "Requirements", ev, "Product Specification")
    assert rel == RelationType.SAME_FAMILY_PART
    assert conf >= 0.90


def test_relation_classification_rules():
    src = parse_is_number("IS 269:1989")
    
    # Test method
    tgt_tm = parse_is_number("IS 4031")
    ev_tm = "When tested in accordance with methods given in IS 4031."
    rel_tm, conf_tm = classify_relation(src, tgt_tm, "requirements", "Testing", ev_tm, "Methods of tests")
    assert rel_tm == RelationType.TEST_METHOD
    assert conf_tm >= 0.90

    # Terminology
    tgt_term = parse_is_number("IS 4845")
    ev_term = "Definitions given in IS 4845 shall apply."
    rel_term, conf_term = classify_relation(src, tgt_term, "terminology", "Terminology", ev_term, "Terminology")
    assert rel_term == RelationType.TERMINOLOGY

    # Related Product
    tgt_mat = parse_is_number("IS 3812")
    ev_mat = "Fly ash used shall conform to IS 3812."
    rel_mat, conf_mat = classify_relation(src, tgt_mat, "requirements", "Raw Materials", ev_mat, "Product Specification")
    assert rel_mat == RelationType.RELATED_PRODUCT


def test_edge_serialization_determinism():
    edge = EdgeRecord(
        from_is="IS 269:1989",
        to_is="IS 4032:1985",
        relation=RelationType.TEST_METHOD,
        confidence=0.98,
        clause_id="IS 269:1989#2",
        evidence_text="Chemical Requirements — When tested in accordance with the methods given in IS 4032.",
        to_in_catalogue=True,
        flags=[],
    )
    dump1 = json.dumps(edge.model_dump(), sort_keys=True)
    dump2 = json.dumps(edge.model_dump(), sort_keys=True)
    assert dump1 == dump2

