import gzip, json, random, re, sqlite3, sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"D:\Standards360")
sys.path.insert(0, str(ROOT / "ingest"))
import collect as c

D = ROOT / "data"
recs = {}
dupes = 0
for line in (D / "bis" / "standards.jsonl").open(encoding="utf-8"):
    r = json.loads(line)
    if r["record_id"] in recs:
        dupes += 1
    recs[r["record_id"]] = r
empty = {int(x) for x in (D / "bis" / "empty_ids.txt").read_text().split() if x.isdigit()}
out = {}

# 1 coverage
def cov(lo, hi):
    ids = range(lo, hi + 1)
    got = sum(1 for i in ids if i in recs); emp = sum(1 for i in ids if i in empty)
    return {"ids": len(ids), "valid": got, "blank": emp, "never_resolved": len(ids) - got - emp}
out["coverage_main"] = cov(*c.MAIN_RANGE)
out["coverage_recent"] = cov(*c.RECENT_RANGE)
out["outside_ranges_collected"] = sum(1 for i in recs if not (c.MAIN_RANGE[0] <= i <= c.MAIN_RANGE[1] or c.RECENT_RANGE[0] <= i <= c.RECENT_RANGE[1]))
out["total_valid"] = len(recs); out["duplicate_lines"] = dupes

# 2 IS number format and uniqueness
pat = re.compile(r"^(IS|IS/IEC|IS/ISO|IS/IEC/ISO|IS/ISO/IEC|SP|IS/IEEE|IS/CISPR|IS/IEC/IEEE)[\s/]")
bad_fmt = [r["is_number"] for r in recs.values() if not pat.match(r["is_number"] or "")]
out["is_number_nonstandard_prefix"] = len(bad_fmt)
out["is_number_nonstandard_examples"] = Counter(x.split()[0] if x else "" for x in bad_fmt).most_common(8)
year_re = re.compile(r":\s*(\d{4})")
no_year = [r["is_number"] for r in recs.values() if not year_re.search(r["is_number"] or "")]
out["is_number_without_year"] = len(no_year)
out["is_number_without_year_examples"] = no_year[:5]
num_counts = Counter(re.sub(r"\s+", "", r["is_number"]).upper() for r in recs.values())
out["same_is_number_on_multiple_records"] = sum(1 for n, k in num_counts.items() if k > 1)
out["same_is_number_examples"] = [n for n, k in num_counts.most_common(5) if k > 1]

# 3 field completeness
fields = ["title", "aspect", "department", "committee", "group", "sub_group", "sub_sub_group",
          "certification", "superseding_is", "equivalence", "revisions", "language", "reaffirmation_year"]
out["field_filled_pct"] = {f: round(100 * sum(1 for r in recs.values() if (r.get(f) or "").strip() not in ("", "None", "N/A")) / len(recs), 1) for f in fields}
out["certification_values"] = Counter(r.get("certification") or "(blank)" for r in recs.values()).most_common()
out["aspect_values"] = Counter(r.get("aspect") or "(blank)" for r in recs.values()).most_common(12)

# 4 enrichment vs counts shown on page
def check(count_key, list_key):
    shown = [r for r in recs.values() if r.get(count_key)]
    missing = [r for r in shown if not r.get(list_key)]
    mismatch = [r for r in shown if r.get(list_key) and len(r[list_key]) != r[count_key]]
    return {"standards_with_count>0": len(shown), "list_missing": len(missing), "length_differs_from_count": len(mismatch)}
out["enrich_labs"] = check("n_labs", "labs")
out["enrich_product_manuals"] = check("n_product_manuals", "product_manuals")
out["enrich_gazette"] = check("n_gazette", "gazette")
out["enrich_amendments"] = check("n_amendments", "amendments")

# 5 cross-reference integrity
refs = {(r["record_id"], x["record_id"]) for r in recs.values() for x in r.get("references", [])}
refby = {(x["record_id"], r["record_id"]) for r in recs.values() for x in r.get("referenced_by", [])}
both_known = {(a, b) for a, b in refs | refby if a in recs and b in recs}
out["xref_links_total"] = len(refs | refby)
out["xref_links_both_ends_collected"] = len(both_known)
out["xref_dangling_targets"] = len({b for a, b in refs if b not in recs} | {a for a, b in refby if a not in recs})
sym_pairs = {(a, b) for a, b in refs if a in recs and b in recs}
out["xref_symmetry_A_cites_B_and_B_lists_A"] = f"{sum(1 for p in sym_pairs if p in refby)}/{len(sym_pairs)}"
self_refs = sum(1 for a, b in refs if a == b)
out["xref_self_references"] = self_refs
number_mismatch = 0
checked = 0
for r in recs.values():
    for x in r.get("references", []):
        if x["record_id"] in recs:
            checked += 1
            a = re.sub(r"\W", "", x["is_number"]).upper()
            b = re.sub(r"\W", "", recs[x["record_id"]]["is_number"]).upper()
            if not (a[:8] == b[:8]):
                number_mismatch += 1
out["xref_label_vs_target_number_mismatch"] = f"{number_mismatch}/{checked}"

# 6 parser re-check against raw HTML (random 300)
random.seed(42)
sample = random.sample(sorted(recs), 300)
reparse_diff = Counter(); raw_missing = 0; title_absent = 0
for rid in sample:
    p = D / "raw" / "bis_html" / f"{rid}.html.gz"
    if not p.exists():
        raw_missing += 1; continue
    html = gzip.decompress(p.read_bytes()).decode("utf-8", "replace")
    again = c.parse_detail(html, rid)
    for k in ("is_number", "title", "aspect", "certification", "superseding_is", "n_labs", "n_amendments", "group"):
        if (again or {}).get(k) != recs[rid].get(k):
            reparse_diff[k] += 1
    flat = c.flatten_html(html)
    if recs[rid]["title"] and recs[rid]["title"][:40] not in flat:
        title_absent += 1
    for x in recs[rid].get("references", []):
        if c.b64(x["record_id"]) not in html:
            reparse_diff["reference_link_absent_in_raw"] += 1
out["reparse_sample"] = 300
out["reparse_raw_missing"] = raw_missing
out["reparse_field_differences"] = dict(reparse_diff)
out["title_text_absent_from_raw"] = title_absent

# 7 gold set consistency
cats = [json.loads(l) for l in (D / "bis" / "categories.jsonl").open(encoding="utf-8")]
norm = lambda s: re.sub(r"[^0-9A-Z()]", "", (s or "").upper().replace("PART", "P"))
agree = sum(1 for k in cats if k["record_id"] in recs and norm(k["is_number"])[:6] == norm(recs[k["record_id"]]["is_number"])[:6])
out["category_pairs_number_agrees_with_detail_page"] = f"{agree}/{len(cats)}"
out["category_pairs_disagree_examples"] = [(k["is_number"], recs[k["record_id"]]["is_number"]) for k in cats
    if k["record_id"] in recs and norm(k["is_number"])[:6] != norm(recs[k["record_id"]]["is_number"])[:6]][:6]

# 8 database matches files
con = sqlite3.connect(D / "catalogue.db")
out["db_standards"] = con.execute("SELECT COUNT(*) FROM standards").fetchone()[0]
out["db_tables"] = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("xrefs", "labs", "product_manuals", "gazette", "amendments", "categories")}
json.dump(out, open(Path(__file__).parent / "audit.json", "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str, ensure_ascii=False))
