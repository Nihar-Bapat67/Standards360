"""Evaluation harness for the retrieval engine (manual §10).

Runs every record of the frozen gold set through the current index and reports the numbers the
manual asks for: Hit@1, Hit@3, Hit@5 and MRR@5, sliced by sector and by difficulty.

It also reports the **ceiling**: a gold standard whose text is not in the index cannot be retrieved
at all, so the score is bounded by corpus coverage rather than by the retrieval engine. Both numbers
are printed, raw and ceiling-adjusted, because reporting only the first would flatter the engine and
only the second would hide a real gap.

    python eval/run_eval.py                       evaluate the current index
    python eval/run_eval.py --top 10 --show-misses
    python eval/run_eval.py --out eval/results.json
"""

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.retrieval import RetrievalEngine  # noqa: E402
from ingest.build_index import load_index  # noqa: E402

GOLD = ROOT / "eval" / "gold_set.json"
META = ROOT / "eval" / "gold_set_meta.json"
DB = ROOT / "data" / "catalogue.db"


def key(is_number):
    """Compare IS numbers without depending on spacing or punctuation."""
    return re.sub(r"[\s:()\-]|PART", "", (is_number or "").upper())


def sector_of(numbers):
    """Department code per gold standard, read from the catalogue rather than assumed."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    by_key = {}
    for num, dept, withdrawn in con.execute("SELECT is_number, department, withdrawn FROM standards"):
        k = key(num)
        if k not in by_key or (by_key[k][1] and not withdrawn):
            by_key[k] = ((dept or "?")[:3], withdrawn)
    con.close()
    return {n: by_key.get(key(n), ("?", 0))[0] for n in numbers}


def difficulty_of(gold):
    if not META.exists():
        return {r["id"]: "unlabelled" for r in gold}
    labels = json.loads(META.read_text(encoding="utf-8"))["difficulty"]
    out = {}
    for level, ids in labels.items():
        for i in ids:
            out[i] = level
    return {r["id"]: out.get(r["id"], "unlabelled") for r in gold}


def evaluate(top_k, show_misses):
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    _, _, id_map, meta = load_index()
    engine = RetrievalEngine()          # C1 itself, reranker included, warmed at construction
    indexed = {key(r["is_number"]) for r in id_map} | {key(r["catalogue_is_number"]) for r in id_map}
    sectors = sector_of({r["correct_is"] for r in gold})
    difficulty = difficulty_of(gold)

    rows = []
    started = time.time()
    for i, record in enumerate(gold, 1):
        target = key(record["correct_is"])
        hits = engine.search(record["product_description"], top_k=top_k).standards
        ranked = [key(hit.is_number) for hit in hits]
        rank = ranked.index(target) + 1 if target in ranked else None
        rows.append({
            "id": record["id"],
            "query": record["product_description"],
            "expected": record["correct_is"],
            "sector": sectors.get(record["correct_is"], "?"),
            "difficulty": difficulty.get(record["id"], "unlabelled"),
            "in_index": target in indexed,
            "rank": rank,
            "returned": [
                {"is_number": h.is_number, "score": h.score,
                 "clause": h.evidence.clause if h.evidence else None,
                 "role": h.evidence.role if h.evidence else None}
                for h in hits
            ],
        })
        print(f"  {i}/{len(gold)} evaluated", end="\r", flush=True)
    print(" " * 30, end="\r")

    def metrics(subset):
        n = len(subset)
        if not n:
            return {}
        return {
            "n": n,
            "hit@1": round(sum(1 for r in subset if r["rank"] == 1) / n, 3),
            "hit@3": round(sum(1 for r in subset if r["rank"] and r["rank"] <= 3) / n, 3),
            "hit@5": round(sum(1 for r in subset if r["rank"] and r["rank"] <= 5) / n, 3),
            "mrr@5": round(sum(1 / r["rank"] for r in subset if r["rank"] and r["rank"] <= 5) / n, 3),
        }

    retrievable = [r for r in rows if r["in_index"]]
    report = {
        "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "index": {k: meta[k] for k in ("model", "rows_indexed", "standards_indexed", "built_at")},
        "gold_records": len(rows),
        "targets_in_index": len(retrievable),
        "targets_missing_from_index": len(rows) - len(retrievable),
        "overall_raw": metrics(rows),
        "overall_retrievable_only": metrics(retrievable),
        "by_sector": {s: metrics([r for r in rows if r["sector"] == s]) for s in sorted({r["sector"] for r in rows})},
        "by_difficulty": {d: metrics([r for r in rows if r["difficulty"] == d])
                          for d in ("easy", "medium", "hard", "unlabelled")
                          if any(r["difficulty"] == d for r in rows)},
        "seconds": round(time.time() - started, 1),
        "records": rows,
    }

    print(f"Index: {meta['model']}, {meta['rows_indexed']} clauses from {meta['standards_indexed']} standards")
    print(f"Gold set: {len(rows)} records, of which {len(retrievable)} have their standard in the index.\n")
    head = f"{'slice':<22}{'n':>4}{'Hit@1':>8}{'Hit@3':>8}{'Hit@5':>8}{'MRR@5':>8}"
    print(head)
    print("-" * len(head))

    def line(name, m):
        if m:
            print(f"{name:<22}{m['n']:>4}{m['hit@1']:>8.3f}{m['hit@3']:>8.3f}{m['hit@5']:>8.3f}{m['mrr@5']:>8.3f}")

    line("all records", report["overall_raw"])
    line("in index only", report["overall_retrievable_only"])
    for s, m in report["by_sector"].items():
        line(f"  sector {s}", m)
    for d, m in report["by_difficulty"].items():
        line(f"  {d}", m)

    target = 0.85
    achieved = report["overall_raw"].get("hit@3", 0)
    print(f"\nManual §10 target is Hit@3 above {target:.0%}: currently {achieved:.1%} "
          f"({'met' if achieved > target else 'not met'}).")
    if report["targets_missing_from_index"]:
        print(f"{report['targets_missing_from_index']} gold standards have no text in the index and "
              f"can never be found; their current editions need downloading.")

    if show_misses:
        print("\nMisses:")
        for r in rows:
            if r["rank"] is None:
                got = ", ".join(x["is_number"] for x in r["returned"][:3]) or "nothing"
                flag = "" if r["in_index"] else "  [not in index]"
                print(f"  {r['id']:>3} {r['expected']:<24} {r['difficulty']:<7}{flag}")
                print(f"      query: {r['query'][:92]}")
                print(f"      got:   {got}")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--top", type=int, default=5, help="results per query to consider")
    p.add_argument("--show-misses", action="store_true", help="print every record the engine missed")
    p.add_argument("--out", default=str(ROOT / "eval" / "results.json"), help="where to write the full report")
    args = p.parse_args()

    report = evaluate(args.top, args.show_misses)
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull per-record report written to {args.out}")


if __name__ == "__main__":
    main()
