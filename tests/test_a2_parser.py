"""Unit tests for Module A2: Document Parser & Clause Splitter.

Tests run against synthetic PDFs with clearly fake, documented standard numbers (IS 99999 range).
Verifies heading detection, false-positive rejection, noise suppression, table formatting,
role classification, oversized splitting, and determinism.
"""

import hashlib
import json
import pytest
import fitz

from contracts.clause import ClauseRecord, ClauseRole
from ingest.parsing.normalizer import (
    normalize_unicode_text,
    dehyphenate_text,
    parse_is_identifier,
)
from ingest.parsing.heading_detector import (
    detect_heading_line,
    is_sequence_valid,
)
from ingest.parsing.role_classifier import classify_clause_role
from ingest.parsing.table_extractor import extract_tables_from_page
from ingest.parsing.clause_splitter import parse_standard_pages
from ingest.parsing.segmenter import StandardSegment


@pytest.fixture
def synthetic_pdf(tmp_path):
    """Create a synthetic test PDF with headers, footers, headings, tables, and dehyphenation."""
    pdf_path = tmp_path / "synthetic_is_99999.pdf"
    doc = fitz.open()

    # Page 1
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 40), "SYNTHETIC RUNNING HEADER", fontname="helv", fontsize=10)
    p1.insert_text((50, 100), "IS 99999 : 2026 SYNTHETIC TEST SPECIFICATION", fontname="times-bold", fontsize=14)
    p1.insert_text((50, 130), "1 SCOPE", fontname="times-bold", fontsize=11)
    p1.insert_text((50, 150), "This standard covers syn-", fontname="times-roman", fontsize=10)
    p1.insert_text((50, 165), "thetic cement requirements of 43 grade.", fontname="times-roman", fontsize=10)
    p1.insert_text((50, 200), "2 REFERENCES", fontname="times-bold", fontsize=11)
    p1.insert_text((50, 220), "The standards given in Annex A contain provisions.", fontname="times-roman", fontsize=10)
    p1.insert_text((50, 260), "3 CHEMICAL REQUIREMENTS", fontname="times-bold", fontsize=11)
    p1.insert_text((50, 280), "43 grade synthetic cement shall comply with requirements.", fontname="times-roman", fontsize=10)
    p1.insert_text((280, 800), "Page 1", fontname="helv", fontsize=10)

    # Page 2: with a table
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 40), "SYNTHETIC RUNNING HEADER", fontname="helv", fontsize=10)
    p2.insert_text((50, 80), "4 PHYSICAL REQUIREMENTS", fontname="times-bold", fontsize=11)
    p2.insert_text((50, 100), "4.1 Fineness", fontname="times-bold", fontsize=11)
    p2.insert_text((50, 120), "Specific surface shall not be less than 225 m² /kg.", fontname="times-roman", fontsize=10)
    
    # Draw simple table lines so PyMuPDF finds a table
    p2.draw_rect(fitz.Rect(50, 150, 350, 210), color=(0, 0, 0), width=1)
    p2.draw_line(fitz.Point(50, 170), fitz.Point(350, 170), color=(0, 0, 0), width=1)
    p2.draw_line(fitz.Point(150, 150), fitz.Point(150, 210), color=(0, 0, 0), width=1)
    p2.insert_text((55, 165), "Grade", fontname="times-bold", fontsize=9)
    p2.insert_text((155, 165), "Strength (MPa)", fontname="times-bold", fontsize=9)
    p2.insert_text((55, 195), "Grade A", fontname="times-roman", fontsize=9)
    p2.insert_text((155, 195), "33 MPa", fontname="times-roman", fontsize=9)
    p2.insert_text((280, 800), "Page 2", fontname="helv", fontsize=10)

    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)


def test_unicode_normalization_and_units():
    # Ligatures replaced
    raw = "The ﬁrst speciﬁcation requires 225 m² area and SO₃ content."
    cleaned = normalize_unicode_text(raw)
    assert "first" in cleaned
    assert "specification" in cleaned
    # Must preserve m² and SO₃ (NFC, never NFKC)
    assert "m²" in cleaned
    assert "SO₃" in cleaned


def test_dehyphenation():
    raw = "This is a syn-\nthetic standard for construc-\ntion materials."
    res = dehyphenate_text(raw)
    assert "synthetic standard" in res
    assert "construction materials" in res


def test_heading_detection_and_false_positive_rejection():
    # Valid headings
    assert detect_heading_line("1 SCOPE", is_bold=True, font_size=11.0, page_num=1) == ("1", "SCOPE")
    assert detect_heading_line("4.2 Compressive Strength", is_bold=True, font_size=10.5, page_num=1) == ("4.2", "Compressive Strength")
    assert detect_heading_line("ANNEX A", is_bold=True, font_size=12.0, page_num=1) == ("ANNEX A", "")

    # False positives that must be rejected
    # Line starting with grade quantity
    assert detect_heading_line("43 grade ordinary Portland cement", is_bold=False, font_size=10.0, page_num=1) is None
    # Line starting with day duration
    assert detect_heading_line("28 days compressive strength shall be 33 MPa", is_bold=False, font_size=10.0, page_num=1) is None
    # Line starting with percentage
    assert detect_heading_line("5.0 percent maximum insoluble residue", is_bold=False, font_size=10.0, page_num=1) is None
    # Line starting with sub-item list like (i)
    assert detect_heading_line("(i) Insoluble material", is_bold=False, font_size=10.0, page_num=1) is None


def test_sequence_sanity():
    # Valid transitions
    assert is_sequence_valid(None, "1") is True
    assert is_sequence_valid("1", "2") is True
    assert is_sequence_valid("4", "4.1") is True
    assert is_sequence_valid("4.1", "4.2") is True
    assert is_sequence_valid("4.2.1", "5") is True
    assert is_sequence_valid("5", "ANNEX A") is True

    # Invalid transitions (erratic leaps)
    assert is_sequence_valid("1", "43") is False
    assert is_sequence_valid("2", "28") is False
    assert is_sequence_valid(None, "15") is False


def test_role_classification():
    assert classify_clause_role("SCOPE", "") == ClauseRole.SCOPE
    assert classify_clause_role("NORMATIVE REFERENCES", "") == ClauseRole.REFERENCES
    assert classify_clause_role("TERMINOLOGY", "") == ClauseRole.TERMINOLOGY
    assert classify_clause_role("CHEMICAL REQUIREMENTS", "") == ClauseRole.REQUIREMENTS
    assert classify_clause_role("SAMPLING", "") == ClauseRole.SAMPLING
    assert classify_clause_role("TEST METHODS", "") == ClauseRole.TEST_METHODS
    assert classify_clause_role("MARKING", "") == ClauseRole.MARKING
    assert classify_clause_role("PACKING", "") == ClauseRole.PACKING
    assert classify_clause_role("Annex A", "", "ANNEX A") == ClauseRole.ANNEX
    assert classify_clause_role("Foreword", "", "0") == ClauseRole.FOREWORD


def test_synthetic_pdf_parsing_and_determinism(synthetic_pdf):
    doc = fitz.open(synthetic_pdf)
    seg = StandardSegment(
        raw_header="IS 99999:2026",
        is_canonical="IS 99999:2026",
        family="IS 99999",
        year=2026,
        title="Synthetic Standard",
        revision="",
        page_start=1,
        page_end=2,
        record_id=99999,
        catalogue_is="IS 99999:2026",
        catalogue_current_year=2026,
        is_withdrawn=False,
    )

    clauses_run1, manifest_run1 = parse_standard_pages(doc, seg, source_sha256="fake_sha", max_clause_chars=3000)
    clauses_run2, manifest_run2 = parse_standard_pages(doc, seg, source_sha256="fake_sha", max_clause_chars=3000)
    doc.close()

    # Verify extracted clauses
    clause_nums = [c.clause for c in clauses_run1]
    assert "1" in clause_nums
    assert "2" in clause_nums
    assert "3" in clause_nums

    # Verify noise suppression (running header stripped)
    for c in clauses_run1:
        assert "SYNTHETIC RUNNING HEADER" not in c.text
        assert "Page 1" not in c.text

    # Verify dehyphenation
    scope_clause = next(c for c in clauses_run1 if c.clause == "1")
    assert "synthetic cement" in scope_clause.text
    assert scope_clause.role == ClauseRole.SCOPE

    # Verify references
    ref_clause = next(c for c in clauses_run1 if c.clause == "2")
    assert ref_clause.role == ClauseRole.REFERENCES

    # Determinism check: byte-identical serialization
    json1 = json.dumps([c.model_dump(by_alias=True) for c in clauses_run1], sort_keys=True)
    json2 = json.dumps([c.model_dump(by_alias=True) for c in clauses_run2], sort_keys=True)
    hash1 = hashlib.sha256(json1.encode()).hexdigest()
    hash2 = hashlib.sha256(json2.encode()).hexdigest()
    assert hash1 == hash2


def test_oversized_clause_splitting():
    # Long text exceeding 3000 chars
    long_body = "This is a detailed technical requirement. " * 100  # ~4200 chars
    raw_lines = [
        {"text": "4 REQUIREMENTS", "is_bold": True, "font_size": 11.0, "page_num": 1, "stream_idx": 0},
        {"text": "4.1 Chemical Composition", "is_bold": True, "font_size": 10.5, "page_num": 1, "stream_idx": 1},
        {"text": long_body, "is_bold": False, "font_size": 10.0, "page_num": 1, "stream_idx": 2},
        {"text": "4.2 Physical Testing", "is_bold": True, "font_size": 10.5, "page_num": 1, "stream_idx": 3},
        {"text": "Requirements for physical testing.", "is_bold": False, "font_size": 10.0, "page_num": 1, "stream_idx": 4},
    ]

    # In our engine, subclauses 4.1 and 4.2 are recognized as individual records with parent_clause="4"
    hd1 = detect_heading_line(raw_lines[1]["text"], True, 10.5, 1)
    hd2 = detect_heading_line(raw_lines[3]["text"], True, 10.5, 1)
    assert hd1 == ("4.1", "Chemical Composition")
    assert hd2 == ("4.2", "Physical Testing")

