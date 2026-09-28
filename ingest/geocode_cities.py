"""Coordinates for the towns that hold a BIS recognised laboratory.

C4.5 answers "how far away is this laboratory", which needs a coordinate for the laboratory and a
coordinate for the user. Both come from this one table, because a user's typed town is looked up the
same way a laboratory's town is.

Why towns and not the laboratories themselves. Only 90 of the 502 laboratory addresses carry a
pincode, and the rest are industrial-estate descriptions that a geocoder resolves to the wrong side
of a city or not at all. A town centre, by contrast, is a well-defined point that can be checked by
hand. So every distance this project reports is a straight line between two town centres, which is
honest about its own precision and is the right granularity for deciding which laboratory to
approach. The exact door-to-door route is the Google Maps link's job, not ours.

The result is written to `config/city_locations.json`, which is committed. The online path therefore
needs no network and no geocoding service, which matters because the demo has to survive a venue
without wifi.

    python ingest/geocode_cities.py              geocode any town not already in the table
    python ingest/geocode_cities.py --recheck    geocode every town again, replacing the table
    python ingest/geocode_cities.py --check      report coverage, geocode nothing

Geocoding is Nominatim (OpenStreetMap). Their usage policy allows at most one request per second
from an identified application, and this script obeys both conditions. The coordinates are
OpenStreetMap data, © OpenStreetMap contributors, ODbL 1.0.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ingest.collect import BIS  # noqa: E402

DIRECTORY = BIS / "lab_directory.jsonl"
TABLE = ROOT / "config" / "city_locations.json"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
AGENT = "Standards360/0.1 (SIH PS 26108 prototype; BIS laboratory directory)"
PAUSE = 1.1  # Nominatim allows one request per second; stay just outside it.

# Towns whose name BIS spells in a way no geocoder recognises. The correction is used only to look
# up a coordinate; the interface always shows the laboratory's city exactly as BIS wrote it, because
# the BIS record is the authority on its own data and we are not in the business of quietly editing
# it. Each entry below was checked against the state it is listed in.
ALIASES = {
    "aditypur jharkhand": "Adityapur",                     # the industrial town near Jamshedpur
    "derabassi punjab": "Dera Bassi",                       # written as two words in OpenStreetMap
    "devangunthi karnataka": "Devanagundi",                 # near Hoskote, Bengaluru Rural
    "guruhram haryana": "Gurugram",                         # a transposition of Gurugram
    "ishnapur telangana": "Isnapur",                        # near Patancheru, Sangareddy district
    "sipara p o lohia nagar patna bihar": "Patna",          # the city field holds a postal address
}

ATTRIBUTION = "Coordinates from OpenStreetMap via Nominatim. Data (c) OpenStreetMap contributors, ODbL 1.0."


def key(city: str, state: str) -> str:
    """The lookup key for a town. Case and punctuation vary between BIS rows; the key must not."""
    return re.sub(r"[^a-z0-9]+", " ", f"{city} {state}".lower()).strip()


def towns():
    """Every (city, state) pair named in the laboratory directory, with a display spelling.

    BIS writes the same city as "CHENNAI", "Chennai" and "chennai". The display spelling chosen is
    the title-cased one, because that is what the interface shows.
    """
    if not DIRECTORY.exists():
        raise SystemExit(f"{DIRECTORY} is missing. Run `python ingest/fetch_labs.py` first.")
    found = {}
    with DIRECTORY.open(encoding="utf-8") as fh:
        for line in fh:
            lab = json.loads(line)
            city, state = (lab.get("city") or "").strip(), (lab.get("state") or "").strip()
            if not city or not state:
                continue
            found.setdefault(key(city, state), {"city": city.title(), "state": state.title()})
    return found


def load_table():
    if not TABLE.exists():
        return {}
    saved = json.loads(TABLE.read_text(encoding="utf-8"))
    return saved.get("places", {})


def geocode(city: str, state: str):
    """One town's coordinates, or None when Nominatim does not recognise it.

    Two attempts: the structured query first, which is the accurate one, then a free-text query for
    towns Nominatim holds under a different administrative level than "city".
    """
    attempts = (
        {"city": city, "state": state, "country": "India"},
        {"q": f"{city}, {state}, India"},
    )
    for params in attempts:
        try:
            response = requests.get(NOMINATIM, params={**params, "format": "jsonv2", "limit": 1},
                                    headers={"User-Agent": AGENT}, timeout=25)
            response.raise_for_status()
            rows = response.json()
        except (requests.RequestException, ValueError):
            rows = []
        time.sleep(PAUSE)
        if rows:
            row = rows[0]
            return {"lat": round(float(row["lat"]), 5), "lon": round(float(row["lon"]), 5),
                    "matched": row.get("display_name", "")}
    return None


def write(places):
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    TABLE.write_text(json.dumps({"attribution": ATTRIBUTION, "places": places},
                                indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                     encoding="utf-8")


def run(recheck=False):
    wanted, places = towns(), {} if recheck else load_table()
    todo = [(k, v) for k, v in wanted.items() if k not in places]
    print(f"{len(wanted)} towns hold a laboratory; {len(places)} already located, {len(todo)} to geocode")
    if todo:
        print(f"at one request per second this takes about {len(todo) * PAUSE / 60:.0f} minutes")

    failed = []
    for n, (k, town) in enumerate(sorted(todo), 1):
        point = geocode(ALIASES.get(k, town["city"]), town["state"])
        if point:
            places[k] = {**town, **point}
        else:
            failed.append(f"{town['city']}, {town['state']}")
        if n % 25 == 0 or n == len(todo):
            print(f"  {n}/{len(todo)} geocoded, {len(failed)} not recognised")

    write(places)
    print(f"\nwrote {len(places)} towns to {TABLE.relative_to(ROOT)}")
    if failed:
        print(f"  {len(failed)} towns were not recognised and carry no coordinate. Laboratories in "
              f"them are still listed, without a distance: {', '.join(failed[:6])}")


def check():
    wanted, places = towns(), load_table()
    missing = sorted(set(wanted) - set(places))
    print(f"{len(places)} towns located of {len(wanted)} named in the laboratory directory")
    if missing:
        print(f"  no coordinate for {len(missing)}: "
              f"{', '.join(wanted[k]['city'] for k in missing[:10])}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--recheck", action="store_true", help="geocode every town again")
    p.add_argument("--check", action="store_true", help="report coverage and geocode nothing")
    args = p.parse_args()
    check() if args.check else run(args.recheck)


if __name__ == "__main__":
    main()
