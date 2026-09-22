import json, random, sys, time
sys.path.insert(0, r"D:\Standards360\ingest")
import collect as c

recs = {}
for line in open(r"D:\Standards360\data\bis\standards.jsonl", encoding="utf-8"):
    r = json.loads(line); recs[r["record_id"]] = r
random.seed(11)
keys = ["is_number", "title", "aspect", "certification", "superseding_is", "department", "n_labs", "n_amendments"]
same = diff = 0
for rid in random.sample(sorted(recs), 12):
    live = c.parse_detail(c.get(c.KYS + "Indian_standards/isdetails/" + c.b64(rid)) or "", rid)
    d = [k for k in keys if (live or {}).get(k) != recs[rid].get(k)]
    same += not d; diff += bool(d)
    print(f"{rid:>6} {recs[rid]['is_number']:<28} {'MATCH' if not d else 'DIFF ' + str([(k, recs[rid].get(k), live.get(k)) for k in d])}")
    time.sleep(0.5)
print(f"{same}/12 identical to the live site")
