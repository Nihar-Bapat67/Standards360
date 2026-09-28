"""Tests for D4, the API layer.

These run the real pipeline behind the endpoint, so they need the catalogue and the index. They are
the closest thing to an integration test the project has: what a procurement portal would receive is
exactly what is asserted here.
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


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from app.api.main import app
    with TestClient(app) as test_client:
        yield test_client


def test_health_reports_what_is_being_served(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["index"]["clauses"] > 1000
    assert body["catalogue"] > 30000


def test_analyze_returns_the_published_contract(client):
    body = client.post("/v1/analyze", json={
        "text": "Supply of 200 MT structural steel tubes YSt 240, 50 NB medium class, for pipe truss"
    }).json()
    assert body["status"] in ("complete", "need_more_info")
    assert body["primary"] == "IS 1161:2014"
    assert body["options"] and body["options"][1]["default"] is True
    assert body["evidence"] and body["evidence"][0]["clause"]
    assert body["certification"] is not None
    assert body["seconds"] > 0


def test_general_question_is_answered_without_a_standard_recommendation(client):
    body = client.post("/v1/analyze/stream", json={
        "text": "What is the difference between IS and ISO?",
    }).text
    result_frame = next(frame for frame in body.split("\n\n") if frame.startswith("event: result"))
    result = __import__("json").loads(next(line[5:].strip() for line in result_frame.splitlines()
                                             if line.startswith("data:")))

    assert result["intent"] == "general_question"
    assert result["primary"] is None
    assert "Indian Standard" in result["explanation"]


def test_standard_lookup_uses_catalogue_and_does_not_run_recommendation(client):
    body = client.post("/v1/analyze", json={"text": "What is IS 269:2015?"}).json()

    assert body["intent"] == "standard_lookup"
    assert body["primary"] == "IS 269:2015"
    assert body["primary_title"]
    assert body["options"] == []


def test_every_depth_starts_from_the_same_primary(client):
    body = client.post("/v1/analyze", json={"text": "mild steel wire 4 mm annealed for binding"}).json()
    primaries = {option["standards"][0] for option in body["options"]}
    assert primaries == {body["primary"]}


def test_a_thin_description_asks_instead_of_guessing(client):
    body = client.post("/v1/analyze", json={"text": "steel tubes"}).json()
    assert body["status"] == "need_more_info"
    assert body["questions"]


def test_answers_can_be_supplied_to_close_the_loop(client):
    first = client.post("/v1/analyze", json={"text": "steel tubes"}).json()
    assert first["questions"]
    second = client.post("/v1/analyze", json={
        "text": "steel tubes",
        "answers": {"type": "electric resistance welded", "application": "structural use in a shed"},
    }).json()
    assert second["requirement"]["attributes"].get("type")
    assert len(second["questions"]) < len(first["questions"])


def test_a_superseded_citation_comes_back_as_a_verdict(client):
    body = client.post("/v1/analyze", json={
        "text": "Steel tubes for structural purposes as per IS 1161:1998"}).json()
    verdicts = {v["citation"]: v for v in body["verdicts"]}
    assert verdicts["IS 1161:1998"]["verdict"] == "replace"
    assert verdicts["IS 1161:1998"]["replacement"] == "IS 1161:2014"


def test_empty_text_is_rejected(client):
    assert client.post("/v1/analyze", json={"text": "   "}).status_code == 422


def test_unsupported_upload_is_refused(client):
    files = {"file": ("notes.exe", b"binary", "application/octet-stream")}
    assert client.post("/v1/analyze/upload", files=files).status_code == 415


def test_upload_forwards_conversation_context(client, monkeypatch):
    from app.api import main

    captured = {}

    class StubPipeline:
        def analyze(self, **kwargs):
            captured.update(kwargs)
            return object()

    monkeypatch.setattr(main, "_shape", lambda _result: main.AnalyzeResponse(status="complete"))
    monkeypatch.setattr(main.app.state, "pipeline", StubPipeline())
    response = client.post(
        "/v1/analyze/upload",
        files={"file": ("spec.txt", b"steel pipe specification", "text/plain")},
        data={
            "history": '[{"role":"user","text":"steel pipes"}]',
            "previous_requirement": '{"product":"steel pipes","category":"pipes_plastic",'
                                    '"attributes":{"type":"PVC"},"cited_standards":[]}',
        },
    )

    assert response.status_code == 200
    assert captured["history"] == [{"role": "user", "text": "steel pipes"}]
    assert captured["previous_requirement"]["product"] == "steel pipes"


def test_standard_lookup_returns_catalogue_facts(client):
    body = client.get("/v1/standard/IS 269:2015").json()
    assert body["resolved"]["current"] == "IS 269:2015"
    assert body["certification"]["mandatory"] is True
    assert body["certification"]["labs_available"] > 0


def test_unknown_standard_is_a_404(client):
    assert client.get("/v1/standard/IS 99999:2021").status_code == 404


# ---------------------------------------------------------------- C4.5, POST /v1/labs

def test_labs_endpoint_orders_by_distance(client):
    body = client.post("/v1/labs", json={"standards": ["IS 269:2015"], "place": "Nagpur",
                                         "limit": 5}).json()
    assert body["origin"]["precision"] == "town"
    assert body["total"] > 20
    measured = [lab["distance_km"] for lab in body["labs"] if lab["distance_km"] is not None]
    assert measured == sorted(measured)
    assert body["labs"][0]["directions_url"].startswith("https://www.google.com/maps/")


def test_labs_endpoint_works_without_a_location(client):
    body = client.post("/v1/labs", json={"standards": ["IS 269:2015"]}).json()
    assert body["origin"] is None
    assert body["labs"] and all(lab["directions_url"] for lab in body["labs"])


def test_an_unrecognised_town_says_so_rather_than_pretending(client):
    """Returning an unordered list silently would look as though the location had been understood."""
    body = client.post("/v1/labs", json={"standards": ["IS 269:2015"], "place": "Wakanda"}).json()
    assert body["origin"] is None
    assert "not recognised" in body["note"]
    assert body["labs"], "the laboratories are still listed"


def test_labs_endpoint_rejects_an_empty_request(client):
    assert client.post("/v1/labs", json={"standards": []}).status_code == 422
    assert client.post("/v1/labs", json={"standards": ["IS 269:2015"],
                                         "lat": 200, "lon": 0}).status_code == 422
