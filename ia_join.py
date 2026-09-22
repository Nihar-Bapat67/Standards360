import json, re, sqlite3
from collections import Counter, defaultdict
items = json.load(open("ia_items.json"))["response"]["docs"]
ia = defaultdict(set)          # (number, part) -> years on archive.org
odd = 0
for d in items:
    m = re.fullmatch(r"gov\.in\.is\.(\d+)(?:\.(\w+?))?\.(\d{4})", d["identifier"])
    if not m: odd += 1; continue
    ia[(m.group(1), (m.group(2) or "").lstrip("0"))].add(int(m.group(3)))
con = sqlite3.connect("file:D:/Standards360/data/catalogue.db?mode=ro", uri=True)
rows = con.execute("SELECT is_number, department, withdrawn, aspect FROM standards").fetchall()
tot = Counter(); same = Counter(); older = Counter(); none_ = Counter()
for num, dept, wd, aspect in rows:
    if wd: continue
    m = re.match(r"IS\s*(\d+)\s*(?:\(\s*Part\s*(\w+)\s*\))?.*?(\d{4})\s*$", num or "", re.I)
    if not m: tot["unparsed"] += 1; continue
    key, year = (m.group(1), (m.group(2) or "").lstrip("0")), int(m.group(3))
    dep = (dept or "?").split()[0]
    for g in ("ALL", dep):
        tot[g] += 1
        ys = ia.get(key, set())
        if year in ys: same[g] += 1
        elif ys: older[g] += 1
        else: none_[g] += 1
print("archive items not matching id pattern:", odd, "  current standards:", tot["ALL"], " unparsed numbers:", tot["unparsed"])
print(f"{'dept':<8}{'current':>8}{'same ed.':>10}{'other ed.':>11}{'absent':>8}")
for g, n in sorted(tot.items(), key=lambda x: -x[1])[:14]:
    if g == "unparsed": continue
    print(f"{g:<8}{n:>8}{same[g]:>10}{older[g]:>11}{none_[g]:>8}")
print(Counter(d for (d,) in con.execute("SELECT department FROM standards WHERE withdrawn=0")).most_common(6))
print("--- gold-set (category) standards by category")
cat = Counter(); hit = Counter()
for c, num in con.execute("SELECT c.category, s.is_number FROM categories c JOIN standards s ON s.record_id=c.record_id GROUP BY c.category, s.record_id"):
    m = re.match(r"IS\s*(\d+)\s*(?:\(\s*Part\s*(\w+)\s*\))?.*?(\d{4})\s*$", num or "", re.I)
    cat[c] += 1
    if m and int(m.group(3)) in ia.get((m.group(1), (m.group(2) or "").lstrip("0")), set()): hit[c] += 1
for c, n in cat.most_common(): print(f"  {hit[c]:>4}/{n:<4} {c}")
print("  total", sum(hit.values()), "/", sum(cat.values()))
