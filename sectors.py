import json, re, sqlite3
from collections import Counter, defaultdict
ia = defaultdict(set)
for d in json.load(open("ia_items.json"))["response"]["docs"]:
    m = re.fullmatch(r"gov\.in\.is\.(\d+)(?:\.(\w+?))?\.(\d{4})", d["identifier"])
    if m: ia[(m.group(1), (m.group(2) or "").lstrip("0"))].add(int(m.group(3)))
con = sqlite3.connect("file:D:/Standards360/data/catalogue.db?mode=ro", uri=True)
dup = {n for (n,) in con.execute("select is_number from standards where withdrawn=0 group by is_number having count(*)>1")}
nref = Counter(r for (r,) in con.execute("select citing_record from xrefs"))
aspect_of = dict(con.execute("select record_id, aspect from standards"))
test_refs = Counter()
for a, b in con.execute("select citing_record, cited_record from xrefs"):
    if (aspect_of.get(b) or "").lower().startswith("methods of test"): test_refs[a] += 1
repl_into = Counter()   # withdrawn standards that name a replacement, by dept of the withdrawn one
S = {}
for rid, num, dept, wd, cert, qco, summ, labs, sup in con.execute(
        "select record_id,is_number,department,withdrawn,certification,qco_status,summary_pdf,n_labs,superseded_by from standards"):
    d = (dept or "?").split()[0]
    if wd:
        if sup: repl_into[d] += 1
        continue
    m = re.match(r"IS\s*(\d+)\s*(?:\(\s*Part\s*(\w+)\s*\))?.*?(\d{4})\s*$", num or "", re.I)
    text = bool(m) and int(m.group(3)) in ia.get((m.group(1), (m.group(2) or "").lstrip("0")), set())
    S[rid] = dict(d=d, text=text, summ=bool(summ), qco=bool(qco), mand="mandatory" in (cert or "").lower(),
                  labs=(labs or 0) > 0, refs=nref[rid], trefs=test_refs[rid], uniq=num not in dup)
def row(ids):
    v = [S[i] for i in ids if i in S]; n = len(v) or 1
    ok = [x for x in v if x["uniq"] and (x["text"] or x["summ"])]
    qc = [x for x in v if x["qco"]]
    return dict(n=len(v), text=sum(x["text"] for x in v)/n, summ=sum(x["summ"] for x in v)/n,
                ok=len(ok)/n, qco=len(qc), qco_ok=sum(1 for x in qc if x["uniq"] and (x["text"] or x["summ"]) and x["labs"]),
                refs=sum(x["refs"] for x in v)/n, trefs=sum(x["trefs"]>0 for x in v)/n)
by = defaultdict(list)
for rid, x in S.items(): by[x["d"]].append(rid)
print("DEPARTMENT   current  text%  summ%  usable%  QCO  QCO-complete  avg-refs  has-test-ref%  withdrawn->named-replacement")
for d, ids in sorted(by.items(), key=lambda kv: -len(kv[1])):
    r = row(ids)
    if r["n"] < 300: continue
    print(f"{d:<10}{r['n']:>9}{r['text']:>7.0%}{r['summ']:>7.0%}{r['ok']:>9.0%}{r['qco']:>5}{r['qco_ok']:>13}{r['refs']:>10.1f}{r['trefs']:>14.0%}{repl_into[d]:>12}")
print("\nGOLD CATEGORY (BIS category pages)   stds  usable%  QCO  QCO-complete  has-test-ref%  departments")
cat = defaultdict(set)
for c, rid in con.execute("select category, record_id from categories"): cat[c].add(rid)
for c, ids in sorted(cat.items(), key=lambda kv: -row(kv[1])["ok"]):
    r = row(ids); ds = Counter(S[i]["d"] for i in ids if i in S).most_common(2)
    print(f"{c[:36]:<37}{r['n']:>5}{r['ok']:>8.0%}{r['qco']:>5}{r['qco_ok']:>13}{r['trefs']:>14.0%}  {ds}")
