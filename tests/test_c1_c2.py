"""Tests for C1 (hybrid retrieval) and C2 (allied expansion).

C1's tests need the A4 index, which is git-ignored, so they skip when it has not been built.
C2's tests need only the catalogue.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HAS_DB = (ROOT / "data" / "catalogue.db").exists()
HAS_INDEX = (ROOT / "data" / "index" / "faiss.index").exists()

pytestmark = pytest.mark.skipif(not HAS_DB, reason="catalogue.db is git-ignored; run the A1 loader")

from app.core.allied import AlliedExpander  # noqa: E402
from app.core.retrieval import RetrievalEngine  # noqa: E402
from app.core.version_resolver import VersionResolver  # noqa: E402
from contracts.analysis import CitationStatus  # noqa: E402


# ---------------------------------------------------------------- C1

@pytest.fixture(scope="module")
def engine():
    if not HAS_INDEX:
        pytest.skip("data/index is git-ignored; run `python ingest/build_index.py`")
    return RetrievalEngine()


def test_query_is_built_from_structured_fields_without_quantity():
    query = RetrievalEngine.build_query({
        "product": "Ordinary Portland Cement",
        "attributes": {"grade": "43", "quantity": "500 MT", "application": "RCC structural work"},
    })
    assert "Ordinary Portland Cement" in query
    assert "43" in query
    assert "RCC structural work" in query
    assert "500" not in query          # quantity carries no signal about which standard applies
    assert query.count("RCC structural work") == 1


def test_known_standard_is_retrieved_first_with_its_clause(engine):
    result = engine.search("steel tubes for structural purposes YSt 240", top_k=3)
    assert result.standards
    top = result.standards[0]
    assert top.is_number == "IS 1161:2014"
    assert top.evidence is not None
    assert top.evidence.clause
    assert top.evidence.quote


def test_reranking_is_available_and_orders_the_shortlist(engine):
    """Reranking is off by default because it lowered Hit@1 on the gold set, but it must work."""
    result = engine.search("steel tubes for structural purposes YSt 240", top_k=3, rerank=True)
    assert result.reranked
    assert result.standards[0].score >= result.standards[1].score
    assert result.standards[0].is_number == "IS 1161:2014"


def test_search_is_fast_enough_once_warm(engine):
    engine.search("mild steel wire for general engineering", top_k=3)
    result = engine.search("galvanized corrugated sheets for roofing", top_k=3)
    assert result.seconds < 5.0          # the manual's latency budget for a text query


def test_empty_query_returns_nothing_rather_than_guessing(engine):
    assert engine.search("   ").standards == []


# ---------------------------------------------------------------- C2

@pytest.fixture(scope="module")
def expander():
    return AlliedExpander()


def test_allied_standards_are_grouped_by_role(expander):
    result = expander.expand(["IS 1161:2014"], depth=1)
    assert result.total > 5
    assert "test_method" in result.groups
    numbers = [a.is_number for group in result.groups.values() for a in group]
    assert any(n.startswith("IS 1608") for n in numbers)     # the tensile test method


def test_allied_standards_are_reported_as_current_editions(expander):
    result = expander.expand(["IS 1161:2014"], depth=1)
    for group in result.groups.values():
        for allied in group:
            assert VersionResolver().resolve(allied.is_number).status is not CitationStatus.SUPERSEDED


def test_each_standard_appears_once_with_its_best_weight(expander):
    result = expander.expand(["IS 1161:2014"], depth=2)
    numbers = [a.is_number for group in result.groups.values() for a in group]
    assert len(numbers) == len(set(numbers))


def test_second_hop_is_weighted_below_the_first(expander):
    one = expander.expand(["IS 1161:2014"], depth=1)
    two = expander.expand(["IS 1161:2014"], depth=2)
    assert two.total > one.total
    far = [a for group in two.groups.values() for a in group if a.hops == 2]
    assert far and max(a.weight for a in far) < 1.0


def test_weak_seeds_are_not_expanded(expander):
    """C2.1: expanding from a weak match multiplies the error."""
    result = expander.expand(["IS 1161:2014"], scores={"IS 1161:2014": 0.42}, floor=0.80)
    assert result.total == 0


# ---------------------------------------------------------------- C3 regressions found through C2

def test_withdrawn_edition_falls_back_to_the_current_edition_of_its_family():
    result = VersionResolver().resolve("IS 10748:2004")
    assert result.current == "IS 10748:2025"
    assert result.status is CitationStatus.SUPERSEDED


def test_standard_republished_in_parts_is_followed():
    result = VersionResolver().resolve("IS 2062:2011")
    assert result.current == "IS 2062 (Part 1):2025"
    assert result.status is CitationStatus.SUPERSEDED


def test_merged_family_is_reported_as_superseded_not_current():
    result = VersionResolver().resolve("IS 8112:1989")
    assert result.status is CitationStatus.SUPERSEDED
    assert result.current == "IS 269:2015"
