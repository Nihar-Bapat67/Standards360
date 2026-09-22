import json, re, sqlite3
from collections import Counter, defaultdict
ia = defaultdict(set)
for d in json.load(open("ia_items.json"))["response"]["docs"]:
    m = re.fullmatch(r"gov\.in\.is\.(\d+)(?:\.(\w+?))?\.(\d{4})", d["identifier"])
    if m: ia[(m.group(1), (m.group(2) or "").lstrip("0"))].add(int(m.group(3)))
con = sqlite3.connect("file:D:/Standards360/data/catalogue.db?mode=ro", uri=True)
def has_text(num):
    m = re.match(r"IS\s*(\d+)\s*(?:\(\s*Part\s*(\w+)\s*\))?.*?(\d{4})\s*$", num or "", re.I)
    return bool(m) and int(m.group(3)) in ia.get((m.group(1), (m.group(2) or "").lstrip("0")), set())
for dep in ("CED", "MTD", "ETD"):
    print(f"\n== {dep}: QCO standards by sub group (count, with current text or summary)")
    c = Counter(); ok = Counter()
    for num, sg, summ in con.execute("select is_number, sub_group, summary_pdf from standards where withdrawn=0 and qco_status<>'' and department like ?", (dep+"%",)):
        c[sg] += 1; ok[sg] += has_text(num) or bool(summ)
    for sg, n in c.most_common(6): print(f"   {n:>3} ({ok[sg]:>3} usable)  {sg}")
print("\n== key procurement standards")
for fam in ["IS 269","IS 1489","IS 455","IS 8112","IS 12269","IS 456","IS 383","IS 1077","IS 2185","IS 1786","IS 2062","IS 1239","IS 1161","IS 432","IS 4984","IS 694","IS 1554","IS 302","IS 732","IS 16102"]:
    for num, t, wd, sup, qco, summ, labs, dep in con.execute(
        "select is_number,title,withdrawn,superseded_by,qco_status,summary_pdf,n_labs,department from standards where replace(is_number,' ','') like ? order by withdrawn, record_id limit 2",
        (fam.replace(' ','') + ':%',)):
        st = "WITHDRAWN->" + sup if wd else "current"
        print(f"   {num:<18} {st:<22} text={'Y' if has_text(num) else '-'} summ={'Y' if summ else '-'} qco={'Y' if qco else '-'} labs={labs:<3} {dep[:3]} {t[:45]}")
