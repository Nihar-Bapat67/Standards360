import json, re
raw = open("is269_2013.pdf.txt", encoding="utf-8").read()
t = re.sub(r"IS\s*269\s*:\s*2013", " ", raw)            # running page headers
t = re.sub(r"©\s*BIS\s*\d{4}", " ", t)
t = re.sub(r"\b1S\s+(?=\d)", "IS ", t)                   # OCR: 1S -> IS
t = re.sub(r"\s+", " ", t)
start = t.find("FOREWORD")
t = t[start:]
# candidate headings: "4 MANUFACTURE", "ANNEX A", sub-clauses "4.1"
pat = re.compile(r"(?<![\w.])(?:(ANNEX\s+[A-Z])\b|(\d{1,2}(?=\s+[A-Z][A-Z’'-]{2,}\b)|\d{1,2}(?:\.\d{1,2}){1,3}(?=\s+[A-Z(])))")
cands = []
for m in pat.finditer(t):
    cands.append((m.start(), m.end(), m.group(1) or m.group(2)))
def nextok(prev, cur):
    if prev is None: return cur == "1"
    if cur.startswith("ANNEX"): return True
    if prev.startswith("ANNEX"): return False                # inside annexes: keep A-1 etc. out of scope for demo
    p, c = [int(x) for x in prev.split(".")], [int(x) for x in cur.split(".")]
    if len(c) == len(p) + 1 and c[:-1] == p and c[-1] == 1: return True   # 4 -> 4.1
    for k in range(min(len(p), len(c)), 0, -1):               # 4.1 -> 4.2, 4.2.3 -> 5
        if len(c) == k and c[:k-1] == p[:k-1] and c[k-1] == p[k-1] + 1: return True
    return False
heads, prev = [], None
for s, e, num in cands:
    if nextok(prev, num):
        heads.append((s, e, num)); prev = num
KIND = {"SCOPE": "scope", "REFERENCES": "references", "TERMINOLOGY": "terminology", "DEFINITIONS": "terminology"}
out = [{"clause": "0", "title": "Foreword", "kind": "foreword", "text": t[len("FOREWORD"):heads[0][0]].strip()}]
for i, (s, e, num) in enumerate(heads):
    body = t[e:heads[i+1][0] if i+1 < len(heads) else len(t)].strip()
    m = re.match(r"([A-Z][A-Z ,/&()’'-]{2,60}?)(?=\s+[A-Z][a-z]|\s+\d|\s*$)", body)
    title = m.group(1).strip().title() if m and "." not in num and not num.startswith("ANNEX") else ""
    if title: body = body[m.end():].strip()
    if num.startswith("ANNEX"):
        m2 = re.match(r"\(\s*\w+\s*\)\s*(.{0,80}?[A-Z]{4,}[A-Z ]*)", body); title = "Annex " + num[-1]
    top = num.split(".")[0]
    kind = ("annex" if num.startswith("ANNEX") else KIND.get(title.upper(), None))
    out.append({"clause": num, "parent": None if "." not in num else num.rsplit(".", 1)[0],
                "title": title, "kind": kind, "text": body})
# inherit kind from parent top-level clause
tops = {c["clause"]: c for c in out if "." not in c["clause"]}
for c in out:
    if not c["kind"]:
        tt = tops.get(c["clause"].split(".")[0], {}).get("title", "").upper()
        c["kind"] = ("test" if "TEST" in tt else KIND.get(tt, "requirement"))
with open("demo_clauses.jsonl", "w", encoding="utf-8") as f:
    for c in out:
        f.write(json.dumps({"record_id": 111, "is_number": "IS 269:2015", "text_edition": 2013,
                            "edition_match": False, "source": "archive.org:gov.in.is.269.2013", **c},
                           ensure_ascii=False) + "\n")
for c in out:
    print(f"{c['clause']:<9} {c['kind']:<12} {c['title'][:34]:<35} {len(c['text']):>5} chars")
print(len(out), "clauses")
