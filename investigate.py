import json, random, re, sys, time
from collections import Counter
from pathlib import Path
sys.path.insert(0, r"D:\Standards360\ingest")
import collect as c

recs = {}
for line in open(r"D:\Standards360\data\bis\standards.jsonl", encoding="utf-8"):
    r = json.loads(line); recs[r["record_id"]] = r

print("=== GAZETTE")
missing = [r for r in recs.values() if r.get("n_gazette") and not r.get("gazette")]
short = [r for r in recs.values() if r.get("n_gazette") and r.get("gazette") and len(r["gazette"]) != r["n_gazette"]]
print("n_gazette distribution among missing:", Counter(min(r["n_gazette"], 5) for r in missing).most_common())
print("short examples (count shown, list len):", [(r["n_gazette"], len(r["gazette"])) for r in short[:8]])
random.seed(3)
for r in random.sample(missing, 3) + random.sample(short, 2):
    rid = r["record_id"]
    raw = c.get(c.KYS + f"Is_gazattedetails/getgazattedetailsAjax?pk_is_id={rid}&is_id={rid}", ajax=True)
    rows = c.json_rows(raw)
    print(f"  id {rid} page says {r['n_gazette']} | stored {len(r.get('gazette') or [])} | live now {len(rows)} | raw head {str(raw)[:160]!r}")
    time.sleep(0.5)

print("\n=== XREF SYMMETRY")
refby = {(x["record_id"], r["record_id"]) for r in recs.values() for x in r.get("referenced_by", [])}
asym = [(r["record_id"], x["record_id"]) for r in recs.values() for x in r.get("references", [])
        if x["record_id"] in recs and (r["record_id"], x["record_id"]) not in refby]
print("A cites B but B's page omits A:", len(asym))
cited_counts = Counter(b for a, b in asym)
print("most affected targets:", [(recs[b]["is_number"], n, len(recs[b].get("referenced_by", []))) for b, n in cited_counts.most_common(5)])
lens = Counter(len(r.get("referenced_by", [])) for r in recs.values())
print("largest referenced_by list lengths:", sorted(lens)[-5:])
for a, b in random.sample(asym, 3):
    print(f"  {recs[a]['is_number']} cites {recs[b]['is_number']}; {recs[b]['is_number']} referenced_by has {len(recs[b].get('referenced_by', []))} entries")

print("\n=== DUPLICATE NUMBERS")
groups = {}
for r in recs.values():
    groups.setdefault(re.sub(r"\s+", "", r["is_number"]).upper(), []).append(r)
dups = [g for g in groups.values() if len(g) > 1]
for g in dups[:6]:
    print("  ", [(r["record_id"], r["is_number"], r["title"][:55], r.get("language")) for r in g])
print("duplicate groups where titles differ:", sum(1 for g in dups if len({r['title'][:40] for r in g}) > 1))

print("\n=== ODD NUMBERS")
for r in recs.values():
    n = r["is_number"]
    if n.startswith(("SI ", "Is ", "10558", "16324", "ISIHB")) or n.endswith(":0"):
        print("  ", r["record_id"], repr(n), "|", r["title"][:60])
        break
print("  SI examples:", [r["is_number"] for r in recs.values() if r["is_number"].startswith("SI ")][:4])
print("  Is examples:", [r["is_number"] for r in recs.values() if r["is_number"].startswith("Is ")][:4])
