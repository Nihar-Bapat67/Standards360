import gzip, json, re
from collections import Counter
from pathlib import Path

root = Path(r"D:\Standards360\data")
ids = [json.loads(l)["record_id"] for l in open(root / "bis" / "standards.jsonl", encoding="utf-8")]
q = Counter(); sup = Counter(); ex = {}
for rid in ids:
    h = gzip.decompress((root / "raw" / "bis_html" / f"{rid}.html.gz").read_bytes()).decode("utf-8", "replace")
    m = re.search(r'class="qco_file_details">(.*?)</a>', h, re.S)
    if m:
        t = re.sub(r"\d{2}-\d{2}-\d{4}", "<date>", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip())
        q[t] += 1
        ex.setdefault(t, rid)
    if "Superseded by IS" in h: sup["has Superseded by IS"] += 1
    if "Superseding IS" in h: sup["has Superseding IS"] += 1
print(len(ids), "pages scanned", dict(sup))
for t, n in q.most_common():
    print(n, repr(t), "e.g.", ex[t])
