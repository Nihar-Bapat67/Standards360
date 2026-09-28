"""Tests for C4.5, the nearest-testing-laboratory finder.

Like C3 and C4, this module makes no inferences: it joins the BIS recognised-laboratory directory to
the standards being recommended and does arithmetic on coordinates. So the tests run against the
real catalogue, and the distances below were checked against the actual geography rather than
against whatever the code happens to return.

The arithmetic itself is tested separately from the database, because a haversine that is wrong by a
factor is the one defect that would be invisible in a list of plausible-looking numbers.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.labs import (  # noqa: E402
    PlaceBook,
    haversine_km,
    place_key,
    round_distance,
    usable_email,
    usable_phone,
)

pytestmark = pytest.mark.skipif(not (ROOT / "data" / "catalogue.db").exists(),
                                reason="catalogue.db is git-ignored; run `python ingest/collect.py load`")

from app.core.labs import LabFinder  # noqa: E402

# A standard with a large laboratory list and compulsory certification, so the answer is never empty.
CEMENT = "IS 269:2015"


@pytest.fixture(scope="module")
def finder():
    return LabFinder()


# ---------------------------------------------------------------- the arithmetic

def test_haversine_matches_known_distances():
    """Two well-known separations, to catch a radius or a radians mistake.

    Delhi to Mumbai is about 1,150 km in a straight line and Pune to Mumbai about 120 km. A formula
    that confused degrees for radians, or used the wrong radius, would miss both badly.
    """
    delhi, mumbai, pune = (28.6139, 77.2090), (19.0760, 72.8777), (18.5204, 73.8567)
    assert 1120 < haversine_km(*delhi, *mumbai) < 1180
    assert 110 < haversine_km(*pune, *mumbai) < 130
    assert haversine_km(*pune, *pune) == pytest.approx(0)


def test_distance_is_rounded_to_its_own_precision():
    """A town-centre distance is reported to the kilometre near by and to ten kilometres far off."""
    assert round_distance(12.4) == 12
    assert round_distance(98.6) == 99
    assert round_distance(263.2) == 260
    assert round_distance(1147.0) == 1150


def test_place_key_ignores_case_spacing_and_punctuation():
    """BIS writes the same town several ways, so the join key must not care which."""
    assert place_key("CHENNAI", "Tamil Nadu") == place_key("Chennai", "tamil  nadu")
    assert place_key("New Delhi", "Delhi") == "new delhi delhi"


def test_unusable_contact_values_are_dropped():
    """A few BIS rows hold "-" or a number cut off mid-way; a dead link is worse than nothing."""
    assert usable_phone("-") is None
    assert usable_phone("+91 955") is None
    assert usable_phone("+91 9555443495") == "+91 9555443495"
    assert usable_email("") is None
    assert usable_email("srol@bis.gov.in") == "srol@bis.gov.in"


# ---------------------------------------------------------------- locating the user

def test_a_town_resolves_to_its_coordinates(finder):
    origin = finder.resolve_origin(place="Pune")
    assert origin is not None and origin.precision == "town"
    assert origin.label == "Pune, Maharashtra"
    assert 18.3 < origin.lat < 18.7 and 73.6 < origin.lon < 74.1


def test_a_state_resolves_without_coordinates(finder):
    """A state is enough to order the list but not to measure anything, and it says so."""
    origin = finder.resolve_origin(place="Kerala")
    assert origin is not None and origin.precision == "state"
    assert origin.lat is None


def test_a_device_coordinate_is_labelled_by_the_nearest_known_town(finder):
    origin = finder.resolve_origin(lat=21.1458, lon=79.0882)  # Nagpur
    assert origin is not None and origin.precision == "device"
    assert "Nagpur" in origin.label


def test_an_unknown_place_resolves_to_nothing_rather_than_something_near(finder):
    """Guessing a location would produce distances that look authoritative and are wrong."""
    assert finder.resolve_origin(place="Wakanda") is None
    assert finder.resolve_origin(place="") is None
    assert finder.resolve_origin(lat=95.0, lon=0.0) is None


# ---------------------------------------------------------------- the answer

def test_laboratories_carry_the_detail_a_manufacturer_needs(finder):
    answer = finder.find([CEMENT], finder.resolve_origin(place="Pune"))
    assert answer.total > 20
    lab = answer.labs[0]
    assert lab.name and lab.city and lab.state
    assert lab.address, "the BIS directory holds an address for the large laboratories"
    assert lab.phone, "and a telephone number"
    assert lab.directions_url.startswith("https://www.google.com/maps/dir/?api=1")
    assert CEMENT in lab.tests


def test_the_list_is_ordered_nearest_first(finder):
    answer = finder.find([CEMENT], finder.resolve_origin(place="Nagpur"))
    measured = [lab.distance_km for lab in answer.labs if lab.distance_km is not None]
    assert measured == sorted(measured)
    assert measured[0] < 400, "somewhere in central India should be within a few hundred kilometres"


def test_a_laboratory_in_the_users_own_town_is_marked_rather_than_measured(finder):
    """Reporting "3 km" between two town centres would imply a precision we do not have."""
    answer = finder.find([CEMENT], finder.resolve_origin(lat=13.0827, lon=80.2707))  # Chennai
    here = [lab for lab in answer.labs if lab.same_city]
    assert here, "BIS has a Southern Regional Laboratory in Chennai"
    assert all(lab.distance_km is None for lab in here)
    assert answer.labs[0].same_city, "and it comes first"


def test_without_a_location_the_answer_is_still_useful(finder):
    """No location must degrade the ordering, never the content or the directions link."""
    answer = finder.find([CEMENT], None)
    assert answer.total > 20
    assert answer.origin is None
    assert all(lab.distance_km is None for lab in answer.labs)
    assert all(lab.directions_url for lab in answer.labs)
    assert "type your town" in answer.note


def test_a_superseded_citation_still_finds_laboratories(finder):
    """Recognition is recorded against the edition in force, so the number must be resolved first."""
    superseded = finder.find(["IS 8112:1989"], None)
    current = finder.find([CEMENT], None)
    assert superseded.total == current.total


def test_opening_times_are_never_invented(finder):
    """BIS publishes none. The gap is stated rather than filled with plausible office hours."""
    answer = finder.find([CEMENT], finder.resolve_origin(place="Pune"))
    assert all(lab.hours is None for lab in answer.labs)
    assert "does not publish opening times" in answer.hours_note


def test_directions_work_without_knowing_where_the_user_is(finder):
    """With no origin the link carries only a destination, and Google starts from the device."""
    lab = finder.find([CEMENT], None).labs[0]
    assert "origin=" not in lab.directions_url
    assert "destination=" in lab.directions_url

    located = finder.find([CEMENT], finder.resolve_origin(place="Pune")).labs[0]
    assert "origin=18.52137%2C73.85451" in located.directions_url


def test_several_standards_say_which_one_each_laboratory_covers(finder):
    answer = finder.find([CEMENT, "IS 1786:2008"], None, limit=50)
    assert answer.total > finder.find([CEMENT], None).total
    assert any(len(lab.tests) == 2 for lab in answer.labs), "some laboratories are recognised for both"
    assert all(lab.tests for lab in answer.labs)


def test_nothing_recognised_is_reported_as_nothing_recognised(finder):
    """An absent laboratory list is not evidence that no laboratory can test the standard."""
    answer = finder.find(["IS 99999:2099"], None)
    assert answer.total == 0 and answer.labs == []
    assert "does not list" in answer.note


# ---------------------------------------------------------------- the coordinate table

def test_the_coordinate_table_is_committed_and_covers_the_directory():
    """The online path must not need a geocoding service; the demo may have no network at all."""
    book = PlaceBook()
    assert len(book.places) > 150
    assert "OpenStreetMap" in book.attribution
    for place in book.places.values():
        assert 6 < place["lat"] < 38 and 68 < place["lon"] < 98, f"{place} is outside India"


def test_an_ambiguous_city_name_does_not_resolve_on_its_own(finder):
    """Two states hold a town of the same name, and picking either silently would be a guess."""
    book = PlaceBook()
    from collections import Counter
    counts = Counter(place_key(p["city"]) for p in book.places.values())
    ambiguous = [name for name, n in counts.items() if n > 1]
    for name in ambiguous:
        assert name not in book.by_city
