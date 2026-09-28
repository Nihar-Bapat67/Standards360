"""A1 extension: the BIS recognised-laboratory directory.

The main collector (`ingest/collect.py`) records which laboratories can test each standard, but it
keeps only the lab's name, city and state. The same BIS endpoint also returns the street address,
a contact number, an email address and a link to the lab's scope of recognition, and C4.5 needs all
of those to answer "where do I get this tested, and how far away is it".

Re-crawling is unnecessary. 1,913 standards carry a laboratory list, but between them they name only
502 distinct laboratories, and the detail is a property of the laboratory rather than of the
standard. A greedy set cover over the lists we already hold picks 78 standards whose lists together
mention every one of the 502 labs, so the whole directory is collected in 78 requests.

    python ingest/fetch_labs.py                  collect the directory into data/bis/lab_directory.jsonl
    python ingest/fetch_labs.py --check          report what the saved directory covers, fetch nothing

`ingest/collect.py load` reads the file this writes into the `lab_directory` table.
"""
import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ingest.collect import BIS, KYS, STANDARDS, clean, get, json_rows  # noqa: E402

DIRECTORY = BIS / "lab_directory.jsonl"

# The fields BIS returns from Is_labs/getlabs, mapped to the names we store.
FIELDS = {
    "vc_lab_name": "name",
    "vc_lab_address": "address",
    "vc_lab_city": "city",
    "vc_lab_state": "state",
    "vc_contact_number": "phone",
    "vc_lab_email": "email",
}


def lab_lists():
    """Every standard's laboratory list, as {record_id: {lab name, ...}}, from the collected file."""
    if not STANDARDS.exists():
        raise SystemExit(f"{STANDARDS} is missing. Run `python ingest/collect.py crawl` first.")
    lists = {}
    with STANDARDS.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            names = {lab["name"] for lab in rec.get("labs") or [] if lab.get("name")}
            if names:
                lists[rec["record_id"]] = names
    return lists


def cover(lists):
    """The fewest standards whose laboratory lists between them name every known laboratory.

    Greedy: repeatedly take the standard that adds the most labs not yet covered. This is the
    classic set-cover heuristic, which cannot do better than a log factor worse than optimal — and
    the point here is only that 78 requests beats 1,913, not that 78 is minimal.
    """
    remaining = set().union(*lists.values())
    picks = []
    while remaining:
        best, gain = None, 0
        for record_id, names in lists.items():
            added = len(names & remaining)
            if added > gain:
                best, gain = record_id, added
        if best is None:  # nothing left can add anything; bad data rather than a normal exit
            break
        picks.append(best)
        remaining -= lists[best]
    return picks


def fetch(record_id):
    rows = json_rows(get(KYS + f"Is_labs/getlabs?pk_is_id={record_id}", ajax=True))
    labs = []
    for row in rows:
        lab = {ours: clean(row.get(theirs) or "") for theirs, ours in FIELDS.items()}
        if not lab["name"]:
            continue
        # The address arrives with the printed line breaks of a postal label. Keep the lines, since
        # the interface shows the address as BIS wrote it, but drop the carriage returns.
        lab["address"] = "\n".join(part.strip() for part in
                                   (row.get("vc_lab_address") or "").splitlines() if part.strip())
        labs.append(lab)
    return labs


def collect(workers=4):
    lists = lab_lists()
    picks = cover(lists)
    wanted = set().union(*lists.values())
    print(f"{len(wanted)} distinct laboratories are named by {len(lists)} standards; "
          f"fetching {len(picks)} laboratory lists to cover them all")

    found = {}
    conflicts = defaultdict(set)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for n, labs in enumerate(pool.map(fetch, picks), 1):
            for lab in labs:
                previous = found.get(lab["name"])
                if previous and previous != lab:
                    # BIS holds one row per lab, so a difference means one of the two lists is stale.
                    # Record it and keep the first; the count is reported so it is never silent.
                    conflicts[lab["name"]].add(json.dumps(lab, sort_keys=True, ensure_ascii=False))
                    continue
                found[lab["name"]] = lab
            if n % 10 == 0 or n == len(picks):
                print(f"  {n}/{len(picks)} lists fetched, {len(found)} laboratories known")

    DIRECTORY.parent.mkdir(parents=True, exist_ok=True)
    with DIRECTORY.open("w", encoding="utf-8") as fh:
        for name in sorted(found):
            fh.write(json.dumps(found[name], ensure_ascii=False) + "\n")

    missing = wanted - set(found)
    report(found, missing, conflicts)


def report(found, missing, conflicts):
    have = lambda field: sum(1 for lab in found.values() if lab.get(field))  # noqa: E731
    print(f"\nwrote {len(found)} laboratories to {DIRECTORY}")
    print(f"  with a street address {have('address')}   phone {have('phone')}   email {have('email')}")
    if conflicts:
        print(f"  {len(conflicts)} laboratories were described differently by two standards; "
              f"the first description was kept")
    if missing:
        print(f"  {len(missing)} named laboratories were not returned by any list fetched: "
              f"{', '.join(sorted(missing)[:5])}")
    else:
        print("  every laboratory named by any standard is in the directory")


def check():
    if not DIRECTORY.exists():
        raise SystemExit(f"{DIRECTORY} does not exist yet. Run `python ingest/fetch_labs.py`.")
    found = {}
    with DIRECTORY.open(encoding="utf-8") as fh:
        for line in fh:
            lab = json.loads(line)
            found[lab["name"]] = lab
    wanted = set().union(*lab_lists().values())
    report(found, wanted - set(found), {})


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="report on the saved directory, fetch nothing")
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()
    check() if args.check else collect(args.workers)


if __name__ == "__main__":
    main()
