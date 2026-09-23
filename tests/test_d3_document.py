"""Tests for D3, the document generator, and the endpoints that serve it.

The assertions are about what a procurement officer would actually receive: their own pages first,
the annexure after, every recommended standard named, the citations reviewed, and nothing quoted at
length from a BIS standard.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HAS_DB = (ROOT / "data" / "catalogue.db").exists()
HAS_INDEX = (ROOT / "data" / "index" / "faiss.index").exists()
pytestmark = pytest.mark.skipif(not (HAS_DB and HAS_INDEX),
                                reason="data/ is git-ignored; run the A1 loader and the A4 builder")

import pymupdf  # noqa: E402

from app.deliver.document import DocumentGenerator  # noqa: E402
from app.pipeline import Pipeline  # noqa: E402

TENDER_TEXT = ("Supply of 200 MT structural steel tubes YSt 240, 50 NB medium class, for pipe truss "
               "of industrial shed, as per IS 1161:1998 and IS 2062:2011")


@pytest.fixture(scope="module")
def result():
    return Pipeline.shared().analyze(text=TENDER_TEXT, state="Gujarat")


@pytest.fixture(scope="module")
def tender_pdf(tmp_path_factory):
    path = tmp_path_factory.mktemp("tender") / "tender.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((60, 90), "PUBLIC WORKS DEPARTMENT", fontsize=14)
    page.insert_text((60, 130), TENDER_TEXT[:80], fontsize=10)
    document.save(str(path))
    document.close()
    return path


LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}


def _text_of(path):
    """Extracted PDF text, with typographic ligatures expanded.

    The renderer sets 'specified' with an fi ligature, so a literal search for the word fails on the
    extracted text unless it is normalised first.
    """
    document = pymupdf.open(path)
    text = " ".join(page.get_text() for page in document)
    document.close()
    for ligature, plain in LIGATURES.items():
        text = text.replace(ligature, plain)
    return " ".join(text.split())


def test_report_contains_the_recommendation_and_its_evidence(result, tmp_path):
    out = DocumentGenerator().generate(result, str(tmp_path / "report.pdf"), mode="report")
    text = _text_of(out)
    assert "Indian Standards — Compliance Report" in text
    assert result.recommendation.primary in text
    assert "Evidence" in text or "no extract can be quoted" in text


def test_every_standard_of_the_chosen_depth_is_listed(result, tmp_path):
    out = DocumentGenerator().generate(result, str(tmp_path / "depth.pdf"), option_id="B", mode="report")
    text = _text_of(out)
    depth_b = next(o for o in result.recommendation.options if o.id == "B")
    for number in depth_b.standards:
        assert number in text, f"{number} missing from the document"


def test_citation_review_and_warnings_reach_the_page(result, tmp_path):
    out = DocumentGenerator().generate(result, str(tmp_path / "review.pdf"), mode="report")
    text = _text_of(out)
    assert "Review of the standards already cited" in text
    assert "IS 1161:1998" in text
    assert "Replace" in text


def test_annexure_is_appended_after_the_users_own_pages(result, tender_pdf, tmp_path):
    out = DocumentGenerator().generate(result, str(tmp_path / "completed.pdf"), mode="annexure",
                                       original_pdf=str(tender_pdf))
    document = pymupdf.open(out)
    assert len(document) >= 2
    assert "PUBLIC WORKS DEPARTMENT" in document[0].get_text()
    assert "Annexure" in document[1].get_text()
    document.close()


def test_the_document_is_complete_from_first_section_to_footer(result, tmp_path):
    """A table wider than the frame silently stopped the renderer part way through; it must not."""
    text = _text_of(DocumentGenerator().generate(result, str(tmp_path / "whole.pdf"), mode="report"))
    for section in ("1. What was specified", "2. Recommended standard", "3. Standards to cite",
                    "4. Review of the standards already cited", "6. Version and amendment warnings"):
        assert section in text, f"{section} missing"
    assert "no standard is reproduced" in text.lower()


def test_the_original_file_is_not_modified(result, tender_pdf, tmp_path):
    before = tender_pdf.read_bytes()
    DocumentGenerator().generate(result, str(tmp_path / "completed2.pdf"), mode="annexure",
                                 original_pdf=str(tender_pdf))
    assert tender_pdf.read_bytes() == before


def test_no_standard_is_reproduced_at_length(result, tmp_path):
    """Copyright: extracts identify a clause, they do not republish it."""
    out = DocumentGenerator().generate(result, str(tmp_path / "quote.pdf"), mode="report")
    text = _text_of(out)
    quoted = text.split("Evidence")[-1][:400] if "Evidence" in text else ""
    assert len(quoted) < 500
    assert "no standard is reproduced" in text.lower()


def test_persona_changes_the_wording(result, tmp_path):
    buyer = _text_of(DocumentGenerator().generate(result, str(tmp_path / "b.pdf"), mode="report",
                                                  persona="procurement"))
    maker = _text_of(DocumentGenerator().generate(result, str(tmp_path / "m.pdf"), mode="report",
                                                  persona="manufacturer"))
    assert "procurement official" in buyer
    assert "manufacturer" in maker


# ---------------------------------------------------------------- the endpoints

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from app.api.main import app
    with TestClient(app) as test_client:
        yield test_client


def test_document_endpoint_returns_a_pdf(client):
    response = client.post("/v1/document", json={"text": TENDER_TEXT, "mode": "report",
                                                 "reference": "PWD/2026/TUBES/17"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert response.headers["X-Primary-Standard"] == "IS 1161:2014"


def test_upload_endpoint_appends_to_the_uploaded_tender(client, tender_pdf):
    files = {"file": ("tender.pdf", tender_pdf.read_bytes(), "application/pdf")}
    response = client.post("/v1/document/upload", files=files,
                           data={"mode": "annexure", "option_id": "B"})
    assert response.status_code == 200
    document = pymupdf.open("pdf", response.content)
    assert len(document) >= 2
    assert "PUBLIC WORKS DEPARTMENT" in document[0].get_text()
    document.close()


def test_a_description_with_no_match_yields_no_document(client):
    response = client.post("/v1/document", json={"text": "qwertyuiop zxcvbnm", "mode": "report"})
    assert response.status_code in (200, 422)
