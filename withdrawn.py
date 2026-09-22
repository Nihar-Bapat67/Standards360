import gzip, json, re, random
from collections import Counter
from pathlib import Path

raw = Path(r"D:\Standards360\data\raw\bis_html")
recs = {}
for line in open(r"D:\Standards360\data\bis\standards.jsonl", encoding="utf-8"):
    r = json.loads(line); recs[r["record_id"]] = r

hits = Counter(); examples = {}
random.seed(5)
ids = random.sample(sorted(recs), 4000)
for rid in ids:
    h = gzip.decompress((raw / f"{rid}.html.gz").read_bytes()).decode("utf-8", "replace")
    for m in re.finditer(r"(?i)(withdrawn|superseded|obsolete|under revision|reaffirmed)[^<]{0,60}", h):
        key = m.group(1).lower()
        hits[key] += 1
        examples.setdefault(key, (rid, recs[rid]["is_number"], re.sub(r"\s+", " ", h[max(0, m.start()-150):m.end()+60])))
print("mentions in 4000 random pages:", hits)
for k, (rid, num, ctx) in examples.items():
    print(f"\n[{k}] {rid} {num}\n   ...{re.sub(r'<[^>]+>', ' ', ctx)[:300]}")

titles = Counter()
for r in recs.values():
    t = (r.get("title") or "").lower()
    if "withdrawn" in t: titles["title says withdrawn"] += 1
    if "reaffirmed" in (r["is_number"] + t).lower(): titles["number/title says reaffirmed"] += 1
print("\n", titles)
