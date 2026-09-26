"""BIS one-page summaries as a text source for A4.

Every BIS "Know Your Standards" detail page carries a link to a one-page official summary of the
standard, and A1 already captured 1,204 of those links for current standards. The summary is the
only text source in this project that is **current by construction**: BIS writes it against the
edition in force, so it can never carry the trust problem that made us refuse older archive.org
editions (see CLAUDE.md, "Trust over coverage").

It is also the text that matters most for retrieval. A summary says what the standard covers in
procurement language — "three grades of cement namely OPC 33, OPC 43 and OPC 53" — which is exactly
what a tender description looks like, and it carries none of the test-procedure clauses that dilute
a full document.

What comes out is clause-shaped, so A4 indexes it with no special case: one record per standard,
clause "SUMMARY", role "summary". C1 labels a hit on it as a summary rather than a clause, because
there is no numbered clause to cite.

    python ingest/fetch_summaries.py --sectors CED MTD          download and extract
    python ingest/fetch_summaries.py --sectors CED MTD --limit 20    a small trial first
    python ingest/fetch_summaries.py --only "IS 269:2015" "IS 455:2015"

Writes:
    data/raw/bis_summary/<record_id>.pdf   the downloaded page, kept so a re-run costs nothing
    data/a2/summaries.json                 clause-shaped records for A4
    data/a2/summary_manifest.json          what was fetched, skipped and quarantined, and why
"""

import argparse
import json
import random
import sqlite3
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
DB = DATA / "catalogue.db"
PDF_DIR = DATA / "raw" / "bis_summary"
OUT = DATA / "a2" / "summaries.json"
MANIFEST = DATA / "a2" / "summary_manifest.json"

DELAY = 0.7           # polite: the detail-page crawl used four workers at 4.5 s a page
TIMEOUT = 90
MIN_CHARS = 200       # a page with less than this carried no usable description
MIN_LETTER_RATIO = 0.5  # below this the PDF has no character map and the "text" is mojibake
USER_AGENT = "Standards360/0.1 (SIH PS26108 student research)"


def rows_to_fetch(sectors, only, limit):
    """Current standards in the chosen departments that have a summary link."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    sql = ["SELECT record_id, is_number, title, department, summary_pdf FROM standards",
           "WHERE withdrawn = 0 AND summary_pdf IS NOT NULL AND summary_pdf <> ''"]
    params = []
    if only:
        sql.append("AND is_number IN (%s)" % ",".join("?" * len(only)))
        params += list(only)
    elif sectors:
        sql.append("AND (%s)" % " OR ".join("department LIKE ?" for _ in sectors))
        params += [f"{s}%" for s in sectors]
    sql.append("ORDER BY record_id")
    if limit:
        sql.append("LIMIT %d" % limit)
    rows = con.execute(" ".join(sql), params).fetchall()
    con.close()
    return rows


def download(url, target, session):
    """Fetch once and keep the file. A re-run then costs no request at all."""
    if target.exists() and target.stat().st_size > 0:
        return target.read_bytes(), "cached"
    try:
        r = session.get(url, timeout=TIMEOUT)
    except requests.RequestException as e:
        return None, f"request failed: {type(e).__name__}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    if not r.content[:5].startswith(b"%PDF"):
        return None, "not a PDF"
    target.write_bytes(r.content)
    return r.content, "downloaded"


def extract(content):
    """Page text, with the quality guard that quarantined the BIS-store copy of IS 269.

    A PDF without a character map extracts as punctuation and boxes. Measuring the share of letters
    catches that in one line, and is the same test A2 applies.
    """
    import pymupdf

    doc = pymupdf.open(stream=content, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    collapsed = " ".join(text.split())
    if len(collapsed) < MIN_CHARS:
        return None, f"only {len(collapsed)} characters of text"
    letters = sum(c.isalpha() for c in collapsed)
    ratio = letters / len(collapsed)
    if ratio < MIN_LETTER_RATIO:
        return None, f"letters are {ratio:.0%} of the text; the PDF has no usable character map"
    return collapsed, None


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sectors", nargs="*", default=["CED", "MTD"],
                   help="department prefixes; the frozen sectors by default")
    p.add_argument("--only", nargs="*", default=None, help="specific IS numbers instead of sectors")
    p.add_argument("--limit", type=int, default=0, help="stop after this many, for a trial run")
    p.add_argument("--delay", type=float, default=DELAY, help="seconds between requests")
    args = p.parse_args()

    rows = rows_to_fetch(args.sectors, args.only, args.limit)
    if not rows:
        raise SystemExit("No current standards with a summary link matched. Check --sectors.")
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    print(f"{len(rows)} standards with a summary link. Fetching at {args.delay}s intervals.",
          flush=True)

    records, quarantine, counts = [], [], {"downloaded": 0, "cached": 0, "failed": 0, "unusable": 0}
    started = time.time()
    for i, row in enumerate(rows, 1):
        target = PDF_DIR / f"{row['record_id']}.pdf"
        was_cached = target.exists()
        content, how = download(row["summary_pdf"], target, session)
        if content is None:
            counts["failed"] += 1
            quarantine.append({"is_number": row["is_number"], "record_id": row["record_id"],
                               "reason": how})
        else:
            counts[how] += 1
            text, problem = extract(content)
            if text is None:
                counts["unusable"] += 1
                quarantine.append({"is_number": row["is_number"], "record_id": row["record_id"],
                                   "reason": problem})
            else:
                records.append({
                    "is": row["is_number"],
                    "clause": "SUMMARY",
                    "title": "BIS summary of the standard",
                    "text": text,
                    "clause_id": f"{row['is_number']}#SUMMARY",
                    "record_id": row["record_id"],
                    "role": "summary",
                    "page_start": 1,
                    "page_end": 1,
                    "has_table": False,
                    "flags": [],
                    "source": "bis_summary_pdf",
                    "source_url": row["summary_pdf"],
                })
        if i % 25 == 0 or i == len(rows):
            rate = i / max(1e-6, time.time() - started)
            print(f"  {i}/{len(rows)}  kept {len(records)}  quarantined {len(quarantine)}  "
                  f"({(len(rows) - i) / max(rate, 1e-6) / 60:.0f} min left)", flush=True)
        if not was_cached and content is not None:
            time.sleep(args.delay + random.random() * 0.3)

    OUT.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    manifest = {
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sectors": args.sectors if not args.only else None,
        "candidates": len(rows),
        "kept": len(records),
        "counts": counts,
        "quarantined": quarantine,
        "seconds": round(time.time() - started, 1),
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{len(records)} summaries kept, written to {OUT}")
    for reason, n in sorted(counts.items()):
        print(f"  {reason:<12} {n}")
    if quarantine:
        print(f"  quarantined {len(quarantine)}; reasons are in {MANIFEST}")


if __name__ == "__main__":
    main()
