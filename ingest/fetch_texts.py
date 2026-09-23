"""Text acquisition for A2: current-edition standard PDFs for the frozen sectors.

The BIS detail pages carry no document text, so A2's input comes from the public
archive.org collection of Indian Standards (items named `gov.in.is.<number>[.<part>].<year>`).

Only the **current edition** is downloaded: an item whose year equals the year of the current
standard in `data/catalogue.db`. Older editions are skipped by design — see the trust-over-coverage
decision in CLAUDE.md. Standards with no current-edition item are listed in the manifest as
`missing`, and their current editions have to be downloaded by hand from the BIS store.

    python ingest/fetch_texts.py --list                 how many standards each sector could get
    python ingest/fetch_texts.py --sectors CED MTD      download them (resumable)
    python ingest/fetch_texts.py --sectors CED --limit 50 --priority
"""

import argparse
import json
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB = DATA / "catalogue.db"
PDF_DIR = DATA / "raw" / "bis_pdf"
MANIFEST = DATA / "text_manifest.json"
IA_ITEMS = DATA / "ia_items.json"

SEARCH = "https://archive.org/advancedsearch.php"
METADATA = "https://archive.org/metadata/"
DOWNLOAD = "https://archive.org/download/"
IDENT = re.compile(r"gov\.in\.is\.(\d+)(?:\.(\w+?))?\.(\d{4})$")
IS_NUM = re.compile(r"IS\s*(\d+)\s*(?:\(\s*Part\s*(\w+)\s*\))?.*?(\d{4})\s*$", re.I)


def archive_items(refresh=False):
    """The archive.org identifiers, keyed by (number, part) -> set of years. Cached on disk."""
    if IA_ITEMS.exists() and not refresh:
        docs = json.loads(IA_ITEMS.read_text(encoding="utf-8"))
    else:
        r = requests.get(SEARCH, params={"q": "identifier:gov.in.is*", "fl[]": "identifier",
                                         "rows": 30000, "output": "json"}, timeout=180)
        r.raise_for_status()
        docs = [d["identifier"] for d in r.json()["response"]["docs"]]
        IA_ITEMS.parent.mkdir(parents=True, exist_ok=True)
        IA_ITEMS.write_text(json.dumps(docs), encoding="utf-8")
    items = {}
    for ident in docs:
        m = IDENT.fullmatch(ident)
        if m:
            items.setdefault((m.group(1), (m.group(2) or "").lstrip("0")), {})[int(m.group(3))] = ident
    return items


def catalogue_rows(sectors):
    """Current standards of the given departments, most useful first."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = []
    for dep in sectors:
        rows += con.execute(
            "SELECT s.record_id, s.is_number, s.title, s.department, s.qco_status, s.n_labs, "
            "  (SELECT COUNT(*) FROM categories c WHERE c.record_id = s.record_id) AS in_gold, "
            "  (SELECT COUNT(*) FROM xrefs x WHERE x.cited_record = s.record_id) AS cited_by "
            "FROM standards s WHERE s.withdrawn = 0 AND s.department LIKE ?", (dep + "%",)).fetchall()
    con.close()
    # Priority: gold-set members first, then QCO products, then the most-cited standards.
    rows.sort(key=lambda r: (-bool(r[6]), -bool(r[4]), -(r[7] or 0), -(r[5] or 0)))
    return rows


def plan(sectors, limit=None, priority=False):
    """Match catalogue standards to a current-edition archive item."""
    items = archive_items()
    wanted, missing = [], []
    for rid, num, title, dep, qco, labs, in_gold, cited_by in catalogue_rows(sectors):
        m = IS_NUM.match(num or "")
        if not m:
            missing.append({"record_id": rid, "is_number": num, "reason": "unparsed_number"})
            continue
        year = int(m.group(3))
        ident = items.get((m.group(1), (m.group(2) or "").lstrip("0")), {}).get(year)
        if not ident:
            missing.append({"record_id": rid, "is_number": num, "reason": "no_current_edition_text"})
            continue
        wanted.append({"record_id": rid, "is_number": num, "title": title, "department": dep[:3],
                       "year": year, "identifier": ident, "in_gold": bool(in_gold),
                       "qco": bool(qco), "cited_by": cited_by})
    if priority:
        wanted = [w for w in wanted if w["in_gold"] or w["qco"] or w["cited_by"] >= 5]
    return (wanted[:limit] if limit else wanted), missing


def fetch_one(entry, session):
    """Download the item's PDF. Returns the entry with a status."""
    target = PDF_DIR / f"{entry['identifier'].replace('gov.in.', '')}.pdf"
    entry["file"] = str(target.relative_to(DATA))
    if target.exists() and target.stat().st_size > 20000:
        entry["status"] = "cached"
        return entry
    try:
        meta = session.get(METADATA + entry["identifier"], timeout=60).json()
        pdfs = [f["name"] for f in meta.get("files", []) if f["name"].lower().endswith(".pdf")]
        if not pdfs:
            entry["status"] = "no_pdf_in_item"
            return entry
        # The file name inside an item varies ('is.269.2013.pdf', 'IS1161:2014.pdf'), and a colon
        # is not a legal Windows filename, so always save under the identifier's own name.
        r = session.get(DOWNLOAD + entry["identifier"] + "/" + requests.utils.quote(pdfs[0]), timeout=180)
        r.raise_for_status()
        if not r.content.startswith(b"%PDF"):
            entry["status"] = "not_a_pdf"
            return entry
        target.write_bytes(r.content)
        entry["status"] = "downloaded"
        entry["bytes"] = len(r.content)
    except Exception as e:
        entry["status"] = f"error: {type(e).__name__}"
    time.sleep(0.2)
    return entry


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sectors", nargs="+", default=["CED", "MTD"], help="department codes to fetch")
    p.add_argument("--limit", type=int, default=None, help="stop after this many standards")
    p.add_argument("--priority", action="store_true",
                   help="only gold-set members, QCO products, and standards cited 5+ times")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--list", action="store_true", help="report coverage and write nothing")
    args = p.parse_args()

    if not DB.exists():
        raise SystemExit(f"{DB} not found. Run `python ingest/collect.py load` first.")

    wanted, missing = plan(args.sectors, args.limit, args.priority)
    print(f"{len(wanted)} standards have a current-edition text; "
          f"{len(missing)} do not and need a manual download from the BIS store.")
    if args.list:
        for dep in args.sectors:
            have = sum(1 for w in wanted if w["department"] == dep)
            gone = sum(1 for m in missing if m.get("reason") == "no_current_edition_text")
            print(f"  {dep}: {have} available")
        print(f"  gold-set members: {sum(1 for w in wanted if w['in_gold'])}, "
              f"QCO products: {sum(1 for w in wanted if w['qco'])}")
        return

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "Standards360/1.0 (SIH PS 26108; research use)"
    done = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, entry in enumerate(pool.map(lambda e: fetch_one(e, session), wanted), 1):
            done.append(entry)
            if i % 25 == 0 or i == len(wanted):
                print(f"  {i}/{len(wanted)} processed", flush=True)

    MANIFEST.write_text(json.dumps({"fetched": done, "missing": missing}, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    counts = {}
    for e in done:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    for k, v in sorted(counts.items()):
        print(f"  {k:<20} {v}")
    print(f"PDFs in {PDF_DIR}; manifest written to {MANIFEST}")


if __name__ == "__main__":
    main()
