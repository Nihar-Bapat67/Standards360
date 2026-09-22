import json, re, sqlite3
cl = [json.loads(l) for l in open("demo_clauses.jsonl", encoding="utf-8")]
tok = lambda s: set(re.findall(r"[a-z0-9]+", s.lower())) - {"the","of","and","to","in","for","be","shall","a","is","as","on","by","or","with","how","what","should","when"}
con = sqlite3.connect("file:D:/Standards360/data/catalogue.db?mode=ro", uri=True)
meta = " ".join(str(x) for x in con.execute("select * from standards where record_id=111").fetchone())
for q in ["how should cement bags be stored", "compressive strength at 28 days",
          "what must be marked on each bag", "when can the purchaser reject a consignment",
          "chloride content limit", "fineness setting time soundness"]:
    qt = tok(q)
    best = sorted(cl, key=lambda c: -len(qt & tok(c["title"] + " " + c["text"])))[:2]
    in_cat = sorted(qt & tok(meta))
    print(f"Q: {q}\n   catalogue row words matched: {in_cat or 'none'}")
    for c in best:
        print(f"   clause {c['clause']:<7} {c['kind']:<11} overlap {len(qt & tok(c['title']+' '+c['text']))}")
# references: who cites what, and where
cited_db = sorted(n for (n,) in con.execute("select s.is_number from xrefs x join standards s on s.record_id=x.cited_record where x.citing_record=111"))
print("\ncatalogue xrefs for IS 269:2015 ->", len(cited_db), "standards")
where = {}
for c in cl:
    if c["kind"] == "foreword": continue
    for m in re.finditer(r"IS\s?(\d{2,5})(?:\s*\(\s*Part\s*(\d+)\s*\))?", c["text"]):
        key = f"IS {m.group(1)}" + (f" (Part {m.group(2)})" if m.group(2) else "")
        where.setdefault(key, set()).add(c["clause"])
for k in sorted(where, key=lambda s: int(re.search(r"\d+", s).group())):
    print(f"   {k:<22} cited in clauses {sorted(where[k])}")
