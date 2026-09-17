
"""A1 Standards Data Collector.

Collects the Indian Standards catalogue from the public BIS "Know Your Standards"
detail pages (services.bis.gov.in), plus the curated product categories.

    python ingest/collect.py categories          product -> standard pairs (28 pages)
    python ingest/collect.py crawl --priority    category standards + the standards they cite
    python ingest/collect.py crawl --recent      the 2026-era record block (about 1,700 pages)
    python ingest/collect.py crawl --all         every record ID (runs for hours, resumable)
    python ingest/collect.py crawl --closure     any cross-referenced record not yet collected
    python ingest/collect.py crawl --ids 111 100 specific record IDs, for testing
    python ingest/collect.py load                build data/catalogue.db from the collected files
    python ingest/collect.py stats               progress summary
    python ingest/collect.py show "IS 269:2015"  one standard and the standards it cites
"""
import argparse
import base64
import gzip
import html as htmllib
import json
import os
import random
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw" / "bis_html"
BIS = DATA / "bis"
STANDARDS = BIS / "standards.jsonl"
EMPTY = BIS / "empty_ids.txt"
CATEGORIES = BIS / "categories.jsonl"
DB = DATA / "catalogue.db"

SITE = "https://www.services.bis.gov.in/php/BIS_2.0/bisconnect/"
KYS = SITE + "knowyourstandards/"
# Record IDs observed in September 2026: a dense block up to about 34,170, then a gap,
# then a block of recent (2026-era) standards from about 65,530 to 67,220.
MAIN_RANGE = (1, 34300)
RECENT_RANGE = (65500, 67400)
TOTAL_IDS = (MAIN_RANGE[1] - MAIN_RANGE[0] + 1) + (RECENT_RANGE[1] - RECENT_RANGE[0] + 1)

BASIC = {
    "IS Number": "is_number",
    "IS Title": "title",
    "Superseding IS": "superseding_is",
    "Degree of Equivalence": "equivalence",
    "Number of Revisions": "revisions",
    "Number of Amendments": "amendments_text",
    "Aspect": "aspect",
    "Language": "language",
    "Reaffirmation Year": "reaffirmation_year",
    "Technical Department": "department",
    "Technical Committee": "committee",
}
CLASSIFICATION = {"Group": "group", "Sub Group": "sub_group",
                  "Sub Sub Group": "sub_sub_group", "Certification": "certification"}
COUNTS = {"Amendment": "n_amendments", "Gazette Document": "n_gazette", "License": "n_licences",
          "Product Manual & SIT": "n_product_manuals", "Laboratory": "n_labs",
          "Corrigendum": "n_corrigenda"}
XREF_HEADINGS = [("references", "Indian Standards Referred In"),
                 ("international", "International Standards Referred In"),
                 ("referenced_by", "is Referred in following Indian Standards")]
XREF_LINK = re.compile(r'<a[^>]+href="[^"]*/isdetails/([A-Za-z0-9+/=]+)"[^>]*>(.*?)</a>', re.S)

_local = threading.local()
_write_lock = threading.Lock()
_state = {"consecutive_failures": 0, "stop": False}


def user_agent():
    contact = os.environ.get("BIS_CONTACT", "").strip()
    return "Standards360/0.1 (SIH PS26108 student research" + (f"; {contact})" if contact else ")")


def session():
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = user_agent()
        _local.session = s
    return s


def get(url, ajax=False, tries=5):
    headers = {"X-Requested-With": "XMLHttpRequest"} if ajax else {}
    for attempt in range(tries):
        if _state["stop"]:
            return None
        try:
            r = session().get(url, headers=headers, timeout=90)
            if r.status_code == 200:
                _state["consecutive_failures"] = 0
                return r.text
            if r.status_code in (403, 429):
                # The server is asking us to back off. Wait long, and give up quickly if it persists.
                time.sleep(120)
        except requests.RequestException:
            pass
        time.sleep(min(60, 2 ** attempt + random.random()))
    _state["consecutive_failures"] += 1
    if _state["consecutive_failures"] >= 25:
        _state["stop"] = True
        print("\nSTOPPING: 25 requests in a row failed. The site may be down or refusing us. "
              "Wait an hour and re-run the same command; it resumes where it stopped.")
    return None


def b64(n):
    return base64.b64encode(str(n).encode()).decode()


def unb64(token):
    try:
        return int(base64.b64decode(token).decode())
    except (ValueError, UnicodeDecodeError):
        return None


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def flatten_html(fragment):
    return clean(re.sub(r"<[^>]+>", " ", fragment.replace("&nbsp;", " ")))


# ---------------------------------------------------------------- parsing

def parse_detail(html, record_id):
    soup = BeautifulSoup(html, "html.parser")
    rec = {"record_id": record_id}

    for row in soup.select("div.form-group.row"):
        label, value = row.select_one("label.qs"), row.select_one("label.rly")
        if not (label and value):
            continue
        key = BASIC.get(clean(label.get_text(" ")).split("/")[0].strip())
        if not key:
            continue
        parts = [clean(p) for p in value.get_text("\n").split("\n") if clean(p)]
        rec[key] = parts[0] if parts else ""
        if key == "is_number" and len(parts) > 1:
            rec["also_numbered"] = parts[1:]

    if not rec.get("is_number"):
        return None

    for tr in soup.find_all("tr"):
        cells = [clean(td.get_text(" ")) for td in tr.find_all(["td", "th"], recursive=False)]
        if len(cells) >= 2 and cells[0] in CLASSIFICATION:
            rec[CLASSIFICATION[cells[0]]] = "" if cells[-1] == ":" else cells[-1]

    start = html.find("Other Details")
    counts_text = flatten_html(html[start:start + 15000]) if start >= 0 else ""
    for label, key in COUNTS.items():
        m = re.search(re.escape(label) + r"\s*:\s*(\d+)", counts_text)
        rec[key] = int(m.group(1)) if m else 0

    marks = sorted((pos.start(), kind) for kind, phrase in XREF_HEADINGS
                   for pos in re.finditer(re.escape(phrase), html))
    rec["references"], rec["referenced_by"] = [], []
    if marks:
        seen = set()
        for m in XREF_LINK.finditer(html, marks[0][0]):
            kind = [k for p, k in marks if p < m.start()][-1]
            target = unb64(m.group(1))
            if kind == "international" or target is None or (kind, target) in seen:
                continue
            seen.add((kind, target))
            rec[kind].append({"record_id": target, "is_number": flatten_html(m.group(2))})
        intl = [p for p, k in marks if k == "international"]
        if intl:
            after = [p for p, _ in marks if p > intl[0]]
            chunk = flatten_html(html[intl[0]:after[0] if after else intl[0] + 4000])
            for noise in ["Standard contains no Cross Referenced International Standard.",
                          "International Standards Referred In", rec["is_number"],
                          *rec.get("also_numbered", [])]:
                chunk = chunk.replace(noise, " ")
            rec["international_refs_text"] = clean(chunk)[:2000]
    return rec


def json_rows(text):
    try:
        data = json.loads(text) if text else None
    except ValueError:
        return []
    return data.get("aaData") or [] if isinstance(data, dict) else []


def enrich(rec):
    rid = rec["record_id"]
    if rec.get("n_labs"):
        rows = json_rows(get(KYS + f"Is_labs/getlabs?pk_is_id={rid}", ajax=True))
        rec["labs"] = [{"name": r.get("vc_lab_name"), "city": r.get("vc_lab_city"),
                        "state": r.get("vc_lab_state")} for r in rows]
    if rec.get("n_product_manuals"):
        rows = json_rows(get(KYS + f"Indian_standards/getproduct_manuals_stiAjax?bis_id={rid}", ajax=True))
        rec["product_manuals"] = [{"type": r.get("file_type"), "doc": r.get("doc_name")} for r in rows]
    if rec.get("n_gazette"):
        rows = json_rows(get(KYS + f"Is_gazattedetails/getgazattedetailsAjax?pk_is_id={rid}&is_id={rid}", ajax=True))
        rec["gazette"] = [{"notice": r.get("AmendmentNumber"), "so_no": r.get("So_No")} for r in rows]
    if rec.get("n_amendments"):
        url = (KYS + f"Indian_standards/getamendments?pk_is_id={rid}"
               f"&con_date=&numb_amendments={rec['n_amendments']}")
        rows = json_rows(get(url, ajax=True))
        rec["amendments"] = [{k: clean(htmllib.unescape(str(v))) for k, v in r.items()
                              if k not in ("Action", "id")} for r in rows]
    return rec


# ---------------------------------------------------------------- crawling

def done_ids():
    done = set()
    if STANDARDS.exists():
        with STANDARDS.open(encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["record_id"])
                except (ValueError, KeyError):
                    pass
    if EMPTY.exists():
        done.update(int(x) for x in EMPTY.read_text().split() if x.strip().isdigit())
    return done


def fetch_one(rid):
    if _state["stop"]:
        return None
    raw_path = RAW / f"{rid}.html.gz"
    if raw_path.exists():
        html = gzip.decompress(raw_path.read_bytes()).decode("utf-8", "replace")
    else:
        html = get(KYS + "Indian_standards/isdetails/" + b64(rid))
        if html is None:
            return None
        raw_path.write_bytes(gzip.compress(html.encode("utf-8")))
    rec = parse_detail(html, rid)
    with _write_lock:
        if rec is None:
            with EMPTY.open("a") as f:
                f.write(f"{rid}\n")
            return None
    rec = enrich(rec)
    with _write_lock:
        with STANDARDS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    time.sleep(0.3)
    return rec


def run(ids, workers, label):
    todo = [i for i in dict.fromkeys(ids) if i not in done_ids()]
    print(f"{label}: {len(todo)} records to fetch with {workers} workers")
    t0, n, found, cited = time.time(), 0, 0, set()
    with ThreadPoolExecutor(workers) as pool:
        for rec in pool.map(fetch_one, todo):
            n += 1
            if rec:
                found += 1
                cited.update(r["record_id"] for r in rec.get("references", []))
            if n % 25 == 0 or n == len(todo):
                rate = n / max(time.time() - t0, 1)
                eta = (len(todo) - n) / rate / 60 if rate else 0
                print(f"  {n}/{len(todo)}  valid {found}  {rate:.2f}/s  about {eta:.0f} min left", flush=True)
            if _state["stop"]:
                break
    return cited


def seed_ids_from_categories():
    if not CATEGORIES.exists():
        raise SystemExit("Run `python ingest/collect.py categories` first.")
    with CATEGORIES.open(encoding="utf-8") as f:
        return [json.loads(line)["record_id"] for line in f if '"record_id": ' in line]


def referenced_ids(only_from=None, directions=("references", "referenced_by")):
    ids = set()
    if not STANDARDS.exists():
        return ids
    with STANDARDS.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if only_from is None or rec["record_id"] in only_from:
                for d in directions:
                    ids.update(r["record_id"] for r in rec.get(d, []))
    return ids


def cmd_crawl(args):
    RAW.mkdir(parents=True, exist_ok=True)
    BIS.mkdir(parents=True, exist_ok=True)
    if args.ids:
        run(args.ids, args.workers, "ids")
        if args.follow:
            cited = referenced_ids(set(args.ids), ("references",))
            run(sorted(cited), args.workers, "standards cited by those ids")
    elif args.priority:
        seeds = seed_ids_from_categories()
        run(seeds, args.workers, "category standards")
        cited = referenced_ids(set(seeds), ("references",))
        run(sorted(cited), args.workers, "standards cited by category standards")
    elif args.recent:
        run(range(RECENT_RANGE[0], RECENT_RANGE[1] + 1), args.workers, "recent block")
    elif args.all:
        run(range(RECENT_RANGE[0], RECENT_RANGE[1] + 1), args.workers, "recent block")
        run(range(MAIN_RANGE[0], MAIN_RANGE[1] + 1), args.workers, "main block")
        run(sorted(referenced_ids()), args.workers, "closure: cross-referenced records not yet collected")
    elif args.closure:
        run(sorted(referenced_ids()), args.workers, "closure: cross-referenced records not yet collected")
    else:
        raise SystemExit("Choose one of --priority, --recent, --all, --closure or --ids.")


def cmd_categories(_args):
    BIS.mkdir(parents=True, exist_ok=True)
    index = BeautifulSoup(get(SITE + "get_is_list_by_category/") or "", "html.parser")
    cats = {}
    for a in index.find_all("a", href=re.compile(r"get_is_list_by_category_id/\d+")):
        cid = int(re.search(r"get_is_list_by_category_id/(\d+)", a["href"]).group(1))
        name = clean(a.get_text(" "))
        if name and cid not in cats:
            cats[cid] = name
    rows = []
    for cid, name in sorted(cats.items()):
        page = BeautifulSoup(get(SITE + f"get_is_list_by_category_id/{cid}") or "", "html.parser")
        for tr in page.find_all("tr"):
            cells = [clean(td.get_text(" ")) for td in tr.find_all("td")]
            link = tr.find("a", href=re.compile(r"isdetails(_mnd)?/"))
            if len(cells) < 4 or not link:
                continue
            m = re.search(r"isdetails_mnd/(\d+)", link["href"])
            rid = int(m.group(1)) if m else unb64(link["href"].rstrip("/").split("/")[-1])
            rows.append({"category_id": cid, "category": name, "record_id": rid,
                         "is_number": cells[1], "product": cells[2], "features": cells[3]})
        print(f"  category {cid:>2}  {len(rows):>4} pairs so far  {name}")
        time.sleep(1)
    with CATEGORIES.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Saved {len(rows)} product-to-standard pairs from {len(cats)} categories to {CATEGORIES}")


# ---------------------------------------------------------------- loading

SCHEMA = """
DROP TABLE IF EXISTS standards; DROP TABLE IF EXISTS xrefs; DROP TABLE IF EXISTS labs;
DROP TABLE IF EXISTS product_manuals; DROP TABLE IF EXISTS gazette;
DROP TABLE IF EXISTS amendments; DROP TABLE IF EXISTS categories;
CREATE TABLE standards (
  record_id INTEGER PRIMARY KEY, is_number TEXT, title TEXT, superseding_is TEXT,
  equivalence TEXT, revisions TEXT, amendments_text TEXT, aspect TEXT, language TEXT,
  reaffirmation_year TEXT, department TEXT, committee TEXT, group_name TEXT, sub_group TEXT,
  sub_sub_group TEXT, certification TEXT, n_amendments INTEGER, n_gazette INTEGER,
  n_licences INTEGER, n_product_manuals INTEGER, n_labs INTEGER, n_corrigenda INTEGER,
  also_numbered TEXT, international_refs_text TEXT);
CREATE TABLE xrefs (citing_record INTEGER, cited_record INTEGER, PRIMARY KEY (citing_record, cited_record));
CREATE TABLE labs (record_id INTEGER, name TEXT, city TEXT, state TEXT);
CREATE TABLE product_manuals (record_id INTEGER, type TEXT, doc TEXT);
CREATE TABLE gazette (record_id INTEGER, notice TEXT, so_no TEXT);
CREATE TABLE amendments (record_id INTEGER, detail TEXT);
CREATE TABLE categories (category_id INTEGER, category TEXT, record_id INTEGER,
  is_number TEXT, product TEXT, features TEXT);
CREATE INDEX ix_standards_is ON standards(is_number);
CREATE INDEX ix_xrefs_cited ON xrefs(cited_record);
"""


def cmd_load(_args):
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    n = 0
    with STANDARDS.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            n += 1
            con.execute("INSERT OR REPLACE INTO standards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                r["record_id"], r.get("is_number"), r.get("title"), r.get("superseding_is"),
                r.get("equivalence"), r.get("revisions"), r.get("amendments_text"), r.get("aspect"),
                r.get("language"), r.get("reaffirmation_year"), r.get("department"), r.get("committee"),
                r.get("group"), r.get("sub_group"), r.get("sub_sub_group"), r.get("certification") or "",
                r.get("n_amendments"), r.get("n_gazette"), r.get("n_licences"),
                r.get("n_product_manuals"), r.get("n_labs"), r.get("n_corrigenda"),
                json.dumps(r.get("also_numbered", []), ensure_ascii=False), r.get("international_refs_text")))
            for x in r.get("references", []):
                con.execute("INSERT OR IGNORE INTO xrefs VALUES (?,?)", (r["record_id"], x["record_id"]))
            for x in r.get("referenced_by", []):
                con.execute("INSERT OR IGNORE INTO xrefs VALUES (?,?)", (x["record_id"], r["record_id"]))
            con.executemany("INSERT INTO labs VALUES (?,?,?,?)",
                            [(r["record_id"], x["name"], x["city"], x["state"]) for x in r.get("labs", [])])
            con.executemany("INSERT INTO product_manuals VALUES (?,?,?)",
                            [(r["record_id"], x["type"], x["doc"]) for x in r.get("product_manuals", [])])
            con.executemany("INSERT INTO gazette VALUES (?,?,?)",
                            [(r["record_id"], x["notice"], x["so_no"]) for x in r.get("gazette", [])])
            con.executemany("INSERT INTO amendments VALUES (?,?)",
                            [(r["record_id"], json.dumps(x, ensure_ascii=False)) for x in r.get("amendments", [])])
    if CATEGORIES.exists():
        with CATEGORIES.open(encoding="utf-8") as f:
            con.executemany("INSERT INTO categories VALUES (?,?,?,?,?,?)",
                            [tuple(json.loads(l)[k] for k in ("category_id", "category", "record_id",
                                                              "is_number", "product", "features")) for l in f])
    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("standards", "xrefs", "labs", "product_manuals", "gazette", "amendments", "categories")}
    con.close()
    print(f"Loaded {n} standards into {DB}")
    for t, c in counts.items():
        print(f"  {t:<16} {c}")


def cmd_show(args):
    con = sqlite3.connect(DB)
    wanted = args.is_number.replace(" ", "").upper()
    sql = ("SELECT record_id, is_number, title, aspect, certification, superseding_is, n_labs FROM standards "
           "WHERE upper(replace(is_number,' ','')) {} ? ORDER BY record_id LIMIT 1")
    row = (con.execute(sql.format("="), (wanted,)).fetchone()
           or con.execute(sql.format("LIKE"), (wanted + "%",)).fetchone())
    if not row:
        raise SystemExit(f"{args.is_number} is not in data/catalogue.db yet. Crawl it, then run `load`.")
    rid, num, title, aspect, cert, sup, n_labs = row
    print(f"{num}  {title}")
    print(f"  aspect: {aspect}   certification: {cert or 'not listed'}   superseding IS: {sup}   labs: {n_labs}")
    print("  cites:")
    for a, n, t in con.execute("SELECT s.aspect, s.is_number, s.title FROM xrefs x JOIN standards s "
                               "ON s.record_id = x.cited_record WHERE x.citing_record = ? "
                               "ORDER BY s.aspect, s.is_number", (rid,)):
        print(f"    {a or '':<24} {n:<26} {(t or '')[:60]}")
    missing = con.execute("SELECT COUNT(*) FROM xrefs x LEFT JOIN standards s ON s.record_id = x.cited_record "
                          "WHERE x.citing_record = ? AND s.record_id IS NULL", (rid,)).fetchone()[0]
    if missing:
        print(f"    plus {missing} cited standards not collected yet")


def cmd_stats(_args):
    valid = sum(1 for _ in STANDARDS.open(encoding="utf-8")) if STANDARDS.exists() else 0
    empty = len(EMPTY.read_text().split()) if EMPTY.exists() else 0
    raw = len(list(RAW.glob("*.html.gz"))) if RAW.exists() else 0
    print(f"valid standards {valid}   empty IDs {empty}   raw pages saved {raw}   "
          f"about {100 * (valid + empty) / TOTAL_IDS:.1f}% of both ID ranges")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("categories").set_defaults(fn=cmd_categories)
    c = sub.add_parser("crawl")
    c.add_argument("--priority", action="store_true")
    c.add_argument("--recent", action="store_true")
    c.add_argument("--all", action="store_true")
    c.add_argument("--closure", action="store_true")
    c.add_argument("--ids", type=int, nargs="+")
    c.add_argument("--follow", action="store_true", help="with --ids, also fetch the standards they cite")
    c.add_argument("--workers", type=int, default=4)
    c.set_defaults(fn=cmd_crawl)
    sub.add_parser("load").set_defaults(fn=cmd_load)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    s = sub.add_parser("show")
    s.add_argument("is_number")
    s.set_defaults(fn=cmd_show)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
