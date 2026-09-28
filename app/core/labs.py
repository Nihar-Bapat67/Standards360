"""Module C4.5: nearest testing laboratories.

The manual's C4.5 says "join the BIS recognised-laboratory list on the standards being recommended,
and return the count plus the nearest few". This module is that step, answering a manufacturer's
question directly: my product has to be tested against these standards, so where do I take it, how
far away is that, and how do I contact them.

    from app.core.labs import LabFinder
    finder = LabFinder()
    finder.find(["IS 269:2015"], finder.resolve_origin(place="Pune"))

What each answer is built from, and how far each part can be trusted:

* The laboratory, its address, phone number and email address come from the BIS recognised-laboratory
  directory collected by `ingest/fetch_labs.py`. They are BIS's own values, reproduced unchanged.
* The distance is a straight line between two town centres, computed from the coordinate table in
  `config/city_locations.json`. It is not a road distance and it is not measured to the laboratory's
  door. It is reported to the nearest kilometre below 100 km and the nearest ten above, so the figure
  does not imply a precision it does not have, and it is labelled as a straight line everywhere it
  is shown.
* The directions link hands the real routing to Google Maps, which does know the roads. The link
  works even when this module has no idea where the user is, because Google Maps then starts from
  the user's own device location.
* Opening times are not published by BIS anywhere in this data, so every laboratory's `hours` field
  is None and `hours_note` says so. Inventing plausible office hours for a government laboratory
  would be exactly the kind of gap-filling this project refuses to do.

Knowing where the user is has three levels of precision, and the answer always says which one it
used. A device coordinate gives a real distance. A town name gives a town-centre distance. A state
name gives no distance at all, only the laboratories in that state first.
"""

import json
import math
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.catalogue import Catalogue  # noqa: E402
from app.core.version_resolver import VersionResolver  # noqa: E402
from contracts.analysis import LabAnswer, LabSuggestion, Origin  # noqa: E402

PLACES = ROOT / "config" / "city_locations.json"
MAPS = "https://www.google.com/maps/dir/?api=1"

# Below this, two town centres are close enough that calling it a distance would be misleading:
# the laboratory is simply in the user's own town.
SAME_TOWN_KM = 12.0

HOURS_NOTE = ("BIS does not publish opening times for recognised laboratories, so none are shown "
              "here. Telephone the laboratory before travelling; the directions link also shows any "
              "opening times Google holds for it.")


def place_key(city: Optional[str], state: Optional[str] = None) -> str:
    """A town reduced to a lookup key, matching `ingest/geocode_cities.py` and the loader."""
    return re.sub(r"[^a-z0-9]+", " ", f"{city or ''} {state or ''}".lower()).strip()


def usable_phone(value: Optional[str]) -> Optional[str]:
    """A telephone number only when it is one that can actually be dialled.

    A handful of BIS rows hold "-" or a number truncated mid-way, such as "+91 955". Offering those
    as a tel: link produces a dead call, which is worse than showing nothing, so anything with fewer
    than seven digits is treated as not stated.
    """
    digits = re.sub(r"\D", "", value or "")
    return value.strip() if len(digits) >= 7 else None


def usable_email(value: Optional[str]) -> Optional[str]:
    """An email address only when it looks like one; two BIS rows hold an empty string."""
    text = (value or "").strip()
    return text if "@" in text and "." in text.split("@")[-1] else None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres, on a sphere of the Earth's mean radius."""
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi, d_lambda = phi2 - phi1, math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def round_distance(km: float) -> float:
    """Report a straight-line distance without implying more precision than it has."""
    if km < 100:
        return round(km)
    return float(round(km, -1))


class PlaceBook:
    """The committed coordinate table, with the several ways a user might name a place.

    Loaded once per process. It holds only towns that hold a recognised laboratory, which is enough
    for both sides of the distance: the laboratory's town is always in it by construction, and a user
    who names a town we do not hold is told so rather than being given a distance from somewhere
    else.
    """

    _instance = None

    def __init__(self, path: Path = PLACES):
        self.places: Dict[str, dict] = {}
        self.attribution = ""
        if Path(path).exists():
            saved = json.loads(Path(path).read_text(encoding="utf-8"))
            self.places = saved.get("places", {})
            self.attribution = saved.get("attribution", "")

        # A city name on its own, but only when it is unambiguous. "Hyderabad" names a town in both
        # Telangana and Sindh, and within India BIS lists cities of the same name in two states, so
        # an ambiguous name must not silently resolve to whichever was loaded first.
        counts: Dict[str, int] = {}
        for place in self.places.values():
            counts[place_key(place["city"])] = counts.get(place_key(place["city"]), 0) + 1
        self.by_city = {place_key(p["city"]): k for k, p in self.places.items()
                        if counts[place_key(p["city"])] == 1}
        self.states = {place_key(p["state"]): p["state"] for p in self.places.values()}

    @classmethod
    def shared(cls) -> "PlaceBook":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def point(self, key: Optional[str]) -> Optional[dict]:
        return self.places.get(key) if key else None

    def nearest_town(self, lat: float, lon: float) -> Optional[dict]:
        """The known town closest to a coordinate, used only to label a device location."""
        best, best_km = None, None
        for place in self.places.values():
            km = haversine_km(lat, lon, place["lat"], place["lon"])
            if best_km is None or km < best_km:
                best, best_km = place, km
        return {**best, "km": best_km} if best else None


class LabFinder:
    def __init__(self, catalogue: Optional[Catalogue] = None,
                 resolver: Optional[VersionResolver] = None,
                 places: Optional[PlaceBook] = None):
        self.cat = catalogue or Catalogue.shared()
        self.resolver = resolver or VersionResolver(self.cat)
        self.places = places or PlaceBook.shared()

    # ---------------------------------------------------------------- locating the user

    def resolve_origin(self, lat: Optional[float] = None, lon: Optional[float] = None,
                       place: Optional[str] = None) -> Optional[Origin]:
        """Read the user's location from a device coordinate or from what they typed.

        A device coordinate wins, because it is the only exact one. Typed text is tried as a
        "city, state" pair, then as a city name on its own, then as a state name.
        """
        if lat is not None and lon is not None:
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return None
            near = self.places.nearest_town(lat, lon)
            label = "your location"
            if near and near["km"] <= 60:
                label = f"near {near['city']}, {near['state']}"
            return Origin(label=label, lat=lat, lon=lon, precision="device")

        text = (place or "").strip()
        if not text:
            return None

        key = place_key(text)
        point = self.places.point(key) or self.places.point(self.places.by_city.get(key))
        if point:
            return Origin(label=f"{point['city']}, {point['state']}",
                          lat=point["lat"], lon=point["lon"], precision="town")

        # "Pune, Maharashtra" typed with the state spelled differently, or a district attached:
        # fall back to the first word that names a town we hold.
        for word in re.split(r"[,/]| - ", text):
            candidate = self.places.by_city.get(place_key(word))
            point = self.places.point(candidate)
            if point:
                return Origin(label=f"{point['city']}, {point['state']}",
                              lat=point["lat"], lon=point["lon"], precision="town")

        for state_key, state in self.places.states.items():
            if state_key and (state_key in key or key in state_key):
                return Origin(label=state, precision="state")
        return None

    # ---------------------------------------------------------------- the answer

    def find(self, is_numbers: Sequence[str], origin: Optional[Origin] = None,
             limit: int = 8) -> LabAnswer:
        """The laboratories recognised for these standards, nearest first."""
        wanted = [n for n in dict.fromkeys(is_numbers) if n]
        collected: Dict[str, dict] = {}
        for number in wanted:
            for lab in self._labs_for(number):
                entry = collected.setdefault(lab["name"], {**lab, "tests": []})
                if number not in entry["tests"]:
                    entry["tests"].append(number)

        suggestions = self.rank(collected.values(), origin)

        return LabAnswer(
            standards=wanted,
            total=len(suggestions),
            origin=origin,
            note=self._note(origin, suggestions),
            labs=suggestions[:limit],
            hours_note=HOURS_NOTE,
            attribution=self.places.attribution if origin and origin.lat is not None else "",
        )

    def rank(self, labs, origin: Optional[Origin] = None) -> List[LabSuggestion]:
        """Catalogue laboratory rows turned into suggestions, nearest first.

        C4 uses this directly for the certification panel's short laboratory list, so that the panel
        and the full laboratory page agree on both the detail and the ordering.
        """
        suggestions = [self._suggest(lab, origin) for lab in labs]
        suggestions.sort(key=self._order)
        return suggestions

    # ---------------------------------------------------------------- internals

    def _labs_for(self, is_number: str) -> List[dict]:
        """Laboratories for one standard, resolved to its current edition first.

        Recognition is recorded against the edition in force, so a tender citing a superseded number
        must be resolved before the join or it finds nothing.
        """
        resolved = self.resolver.resolve(is_number)
        record_id = resolved.current_record_id or resolved.record_id
        return self.cat.labs(record_id) if record_id else []

    def _suggest(self, lab: dict, origin: Optional[Origin]) -> LabSuggestion:
        state = (lab.get("state") or "").strip()
        same_state = bool(origin and place_key(state) == place_key(origin.label.split(", ")[-1]))
        distance = same_city = None

        point = self.places.point(lab.get("city_key"))
        if origin and origin.lat is not None and point:
            km = haversine_km(origin.lat, origin.lon, point["lat"], point["lon"])
            same_city = km <= SAME_TOWN_KM
            distance = None if same_city else round_distance(km)
            same_state = same_state or km <= 150

        return LabSuggestion(
            name=lab["name"],
            city=(lab.get("city") or "").strip(),
            state=state,
            address=lab.get("address"),
            phone=usable_phone(lab.get("phone")),
            email=usable_email(lab.get("email")),
            distance_km=distance,
            same_city=bool(same_city),
            same_state=same_state,
            directions_url=self._directions(lab, origin),
            hours=None,  # BIS publishes none; see HOURS_NOTE
            tests=lab.get("tests", []),
        )

    @staticmethod
    def _directions(lab: dict, origin: Optional[Origin]) -> str:
        """A Google Maps directions link to this laboratory.

        The destination is the laboratory's name followed by the address BIS holds, because Google's
        own geocoder resolves a named place more reliably than an industrial-estate address alone.
        When the user's location is unknown the origin is left out entirely, and Google Maps then
        routes from wherever the user's device is — so the link is never broken, only less specific.
        """
        parts = [lab["name"], (lab.get("address") or "").replace("\n", ", "),
                 lab.get("city") or "", lab.get("state") or "", "India"]
        destination = ", ".join(re.sub(r"\s+", " ", p).strip(" ,") for p in parts if p and p.strip())
        url = f"{MAPS}&destination={quote_plus(destination)}&travelmode=driving"
        if origin and origin.lat is not None:
            url += f"&origin={origin.lat}%2C{origin.lon}"
        elif origin:
            url += f"&origin={quote_plus(origin.label + ', India')}"
        return url

    @staticmethod
    def _order(lab: LabSuggestion):
        """Nearest first, with everything of unknown distance after everything measured."""
        return (0 if lab.same_city else 1,
                lab.distance_km if lab.distance_km is not None else (0 if lab.same_city else 1e9),
                0 if lab.same_state else 1,
                lab.name)

    def _note(self, origin: Optional[Origin], labs: List[LabSuggestion]) -> str:
        if not labs:
            return ("BIS does not list a recognised laboratory for these standards. That does not "
                    "mean no laboratory can test them; ask the nearest BIS branch office.")
        if origin is None:
            return ("Share your location, or type your town, and these laboratories will be ordered "
                    "by how far away they are. The directions link works either way.")
        if origin.precision == "state":
            return (f"{origin.label} was read as a state, so laboratories there are listed first "
                    f"without a distance. Type a town, or share your location, for distances.")
        measured = sum(1 for lab in labs if lab.distance_km is not None or lab.same_city)
        how = "your device location" if origin.precision == "device" else f"the centre of {origin.label}"
        if not measured:
            return (f"Distances could not be worked out from {how}, because no coordinate is held for "
                    f"these laboratories' towns.")
        return (f"Distances are straight lines from {how} to the centre of each laboratory's town, "
                f"not road distances. Use the directions link for the real route.")
