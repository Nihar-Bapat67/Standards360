"""Module A4: Index Builder.

Turns A2's clauses into the two search indexes C1 queries at request time, plus the row map that
converts a search hit back into a real catalogue entry.

Outputs (all files, no server, so the demo runs offline):
    data/index/faiss.index   dense vectors, one row per indexed clause, cosine similarity
    data/index/bm25.pkl      keyword index over the same rows, in the same order
    data/index/id_map.json   row -> record_id, IS number, clause, role, pages, text
    data/index/meta.json     model, dimensions, filters applied, counts, build time

Only clauses that may be relied on are indexed, per the trust-over-coverage decision in CLAUDE.md:
a clause parsed from a withdrawn standard, or from an edition that is not the current one, is
skipped, and the count of what was skipped is reported.

    python ingest/build_index.py --clauses data/a2/clauses.json
    python ingest/build_index.py --model BAAI/bge-m3            the manual's model (large download)
    python ingest/build_index.py --query "steel tubes for structural purposes"   smoke test
"""

import argparse
import json
import pickle
import re
import sqlite3
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB = DATA / "catalogue.db"
INDEX_DIR = DATA / "index"
FAISS_FILE = INDEX_DIR / "faiss.index"
BM25_FILE = INDEX_DIR / "bm25.pkl"
ID_MAP_FILE = INDEX_DIR / "id_map.json"
META_FILE = INDEX_DIR / "meta.json"
TITLES_FILE = INDEX_DIR / "titles.pkl"

# The manual's model. A smaller multilingual model can be passed with --model on a laptop.
DEFAULT_MODEL = "BAAI/bge-m3"
SKIP_FLAGS = ("standard_withdrawn", "text_version_differs_from_current")
TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")


def tokenize(text):
    """Lowercase word tokens, keeping IS numbers and ratings like 'is1786', '43', 'ip66' intact."""
    return TOKEN.findall(text.lower())


def build_title_index():
    """A keyword index over the title of every current standard.

    The clause index only covers standards whose text we hold, which is a minority of the catalogue,
    and a query about anything else lands on whichever clause happens to mention the product. BIS's
    own titles are short, precise and cover all 24,101 current standards, so they give the engine
    something correct to find when the text is missing. A title match carries no clause evidence and
    is labelled as such downstream.

    Titles alone are indexed with BM25 rather than embedded: embedding 24,101 titles would take a
    day on this laptop, while BM25 builds in seconds and matches product names well.
    """
    import pickle

    from rank_bm25 import BM25Okapi

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = []
    for record_id, is_number, title, department, group, sub_group in con.execute(
            "SELECT record_id, is_number, title, department, group_name, sub_group "
            "FROM standards WHERE withdrawn = 0 AND title <> ''"):
        rows.append({"record_id": record_id, "is_number": is_number, "title": title,
                     "department": (department or "")[:3],
                     # The group names carry vocabulary the title omits ("Cement and its Testing"),
                     # which helps a plain-language query find the right family.
                     "context": " ".join(x for x in (group, sub_group) if x)})
    con.close()
    if not rows:
        raise SystemExit("No current standards in the catalogue; run `python ingest/collect.py load`.")

    corpus = [tokenize(f"{r['is_number']} {r['title']} {r['context']}") for r in rows]
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    TITLES_FILE.write_bytes(pickle.dumps({"bm25": BM25Okapi(corpus), "rows": rows}))
    print(f"Title index: {len(rows)} current standards -> {TITLES_FILE} "
          f"({TITLES_FILE.stat().st_size / 1e6:.1f} MB)")
    return len(rows)


def standard_titles():
    """record_id -> (is_number, title, department) from the A1 catalogue."""
    if not DB.exists():
        return {}
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = {r[0]: (r[1], r[2], r[3]) for r in
            con.execute("SELECT record_id, is_number, title, department FROM standards WHERE withdrawn = 0")}
    con.close()
    return rows


def select_clauses(clauses, titles, min_chars, include_foreword):
    """Apply the trust rules and drop clauses that carry no searchable content."""
    rows, skipped = [], Counter()
    for c in clauses:
        flags = set(c.get("flags") or [])
        if flags & set(SKIP_FLAGS):
            skipped["not the current edition"] += 1
            continue
        if c.get("role") == "foreword" and not include_foreword:
            skipped["foreword (history, not requirements)"] += 1
            continue
        text = (c.get("text") or "").strip()
        if len(text) < min_chars:
            skipped[f"shorter than {min_chars} characters"] += 1
            continue
        rid = c.get("record_id")
        if rid is None or rid not in titles:
            skipped["no current catalogue record"] += 1
            continue
        rows.append((c, titles[rid]))
    return rows, skipped


def searchable_text(clause, title):
    """What gets embedded: the standard's identity, then the clause heading, then its text.

    The standard's title is included because a scope clause often describes the product without
    naming it ('This standard covers the requirements for hot finished seamless...').
    """
    parts = [f"{clause.get('is', '')} {title}", clause.get("title") or "", clause.get("text") or ""]
    return " — ".join(p.strip() for p in parts if p and p.strip())[:2000]


def build(args):
    import faiss
    import numpy as np
    from rank_bm25 import BM25Okapi
    from sentence_transformers import SentenceTransformer

    clauses_path = Path(args.clauses)
    if not clauses_path.exists():
        raise SystemExit(f"{clauses_path} not found. Run `python ingest/parse_clauses.py` (A2) first.")
    clauses = json.loads(clauses_path.read_text(encoding="utf-8"))
    titles = standard_titles()
    selected, skipped = select_clauses(clauses, titles, args.min_chars, args.include_foreword)
    if not selected:
        raise SystemExit("Nothing to index after filtering. Check the A2 output and its flags.")

    print(f"{len(clauses)} clauses in, {len(selected)} indexed.")
    for reason, n in skipped.most_common():
        print(f"  skipped {n:>6}  {reason}")

    # Appending keeps the existing vectors and embeds only what is new. Embedding is the whole cost
    # of this module, about 0.29 clauses a second on a CPU, so adding 300 clauses to an index of
    # 4,130 takes under twenty minutes instead of four hours.
    existing_map, existing_index = [], None
    if args.append and FAISS_FILE.exists() and ID_MAP_FILE.exists():
        existing_map = json.loads(ID_MAP_FILE.read_text(encoding="utf-8"))
        existing_index = faiss.read_index(str(FAISS_FILE))
        known = {row.get("clause_id") for row in existing_map}
        fresh = [(c, t) for c, t in selected if c.get("clause_id") not in known]
        print(f"Append mode: {len(existing_map)} clauses already indexed, {len(fresh)} new to embed.")
        if not fresh:
            print("Nothing new to add; the index already covers every clause.")
            return json.loads(META_FILE.read_text(encoding="utf-8"))
        # The ordering contract: existing rows keep their positions, new rows are appended after.
        by_clause = {c.get("clause_id"): (c, t) for c, t in selected}
        selected = [by_clause.get(row.get("clause_id"), (row, (row.get("catalogue_is_number"),
                                                              row.get("standard_title"), "")))
                    for row in existing_map] + fresh
        texts_all = [searchable_text(c, t[1]) for c, t in selected]
        texts = [searchable_text(c, t[1]) for c, t in fresh]
    else:
        texts = texts_all = [searchable_text(c, t[1]) for c, t in selected]

    print(f"Loading embedding model {args.model} to embed {len(texts)} clauses ...", flush=True)
    started = time.time()
    model = SentenceTransformer(args.model)

    # Encode in chunks and report progress to stdout. bge-m3 on a CPU takes hours for a few
    # thousand clauses, and a progress bar inside a background job cannot be read.
    chunk = max(args.batch_size * 8, 64)
    parts = []
    encode_started = time.time()
    for start in range(0, len(texts), chunk):
        parts.append(model.encode(texts[start:start + chunk], batch_size=args.batch_size,
                                  convert_to_numpy=True, normalize_embeddings=True,
                                  show_progress_bar=False))
        done = min(start + chunk, len(texts))
        rate = done / max(1e-6, time.time() - encode_started)
        print(f"  encoded {done}/{len(texts)} clauses  ({rate:.1f}/s, "
              f"about {(len(texts) - done) / max(rate, 1e-6) / 60:.0f} min left)", flush=True)
    vectors = np.asarray(np.vstack(parts), dtype="float32")
    dim = vectors.shape[1]

    # Inner product on normalised vectors is cosine similarity. Flat index: exact, and fast enough
    # well past this corpus size; swap for IVF only when the corpus stops fitting in memory.
    if existing_index is not None:
        index = existing_index
        index.add(vectors)
    else:
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)

    # BM25 is cheap to rebuild and must cover every row in the same order as the vectors.
    bm25 = BM25Okapi([tokenize(t) for t in texts_all])

    id_map = []
    for row, (c, (is_number, title, dept)) in enumerate(selected):
        id_map.append({
            "row": row,
            "record_id": c.get("record_id"),
            "is_number": c.get("is") or is_number,
            "catalogue_is_number": is_number,
            "standard_title": title,
            "department": (dept or "")[:3],
            "clause": c.get("clause"),
            "clause_id": c.get("clause_id"),
            "role": c.get("role"),
            "page_start": c.get("page_start"),
            "page_end": c.get("page_end"),
            "has_table": c.get("has_table", False),
            "text": c.get("text"),
        })

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(FAISS_FILE))
    BM25_FILE.write_bytes(pickle.dumps({"bm25": bm25, "tokenizer": "build_index.tokenize"}))
    ID_MAP_FILE.write_text(json.dumps(id_map, ensure_ascii=False), encoding="utf-8")
    meta = {
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": args.model,
        "dimensions": dim,
        "clauses_in": len(clauses),
        "rows_indexed": len(id_map),
        "standards_indexed": len({r["record_id"] for r in id_map}),
        "departments": dict(Counter(r["department"] for r in id_map)),
        "roles": dict(Counter(r["role"] for r in id_map)),
        "skipped": dict(skipped),
        "filters": {"min_chars": args.min_chars, "include_foreword": args.include_foreword,
                    "skip_flags": list(SKIP_FLAGS)},
        "source": str(clauses_path),
        "build_seconds": round(time.time() - started, 1),
    }
    META_FILE.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nIndexed {len(id_map)} clauses from {meta['standards_indexed']} standards "
          f"in {meta['build_seconds']}s ({dim} dimensions).")
    for name, path in (("faiss.index", FAISS_FILE), ("bm25.pkl", BM25_FILE),
                       ("id_map.json", ID_MAP_FILE), ("meta.json", META_FILE)):
        print(f"  {name:<14} {path.stat().st_size / 1e6:.1f} MB  {path}")
    return meta


_LOADED = {}


def load_index():
    """Load the index once per process. Loading the model costs about a minute, so an evaluation
    run over fifty queries must not repeat it."""
    import faiss
    if "index" not in _LOADED:
        if not FAISS_FILE.exists():
            raise SystemExit("No index yet. Run `python ingest/build_index.py` first.")
        meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        _LOADED["index"] = faiss.read_index(str(FAISS_FILE))
        _LOADED["bm25"] = pickle.loads(BM25_FILE.read_bytes())["bm25"]
        _LOADED["id_map"] = json.loads(ID_MAP_FILE.read_text(encoding="utf-8"))
        _LOADED["meta"] = meta
    return _LOADED["index"], _LOADED["bm25"], _LOADED["id_map"], _LOADED["meta"]


def load_model(name):
    from sentence_transformers import SentenceTransformer
    if _LOADED.get("model_name") != name:
        _LOADED["model"] = SentenceTransformer(name)
        _LOADED["model_name"] = name
    return _LOADED["model"]


def search(query, top_k=5, pool=25):
    """Smoke test of both indexes, merged with Reciprocal Rank Fusion.

    This is deliberately minimal: C1 owns the real retrieval, including the cross-encoder rerank
    and the roll-up from clauses to standards. This exists so A4's output can be verified on its own.
    """
    import numpy as np

    index, bm25, id_map, meta = load_index()
    model = load_model(meta["model"])
    qv = np.asarray(model.encode([query], normalize_embeddings=True), dtype="float32")
    _, dense_rows = index.search(qv, min(pool, index.ntotal))
    dense_rows = list(dense_rows[0])
    sparse_rows = list(np.argsort(bm25.get_scores(tokenize(query)))[::-1][:pool])

    fused = {}
    for rank, row in enumerate(dense_rows):
        fused[int(row)] = fused.get(int(row), 0) + 1 / (60 + rank)
    for rank, row in enumerate(sparse_rows):
        fused[int(row)] = fused.get(int(row), 0) + 1 / (60 + rank)

    # Roll clauses up to standards, keeping each standard's best clause as its evidence.
    by_standard = {}
    for row, score in sorted(fused.items(), key=lambda kv: -kv[1]):
        entry = id_map[row]
        best = by_standard.get(entry["record_id"])
        if best is None or score > best[0]:
            by_standard[entry["record_id"]] = (score, entry)
    return sorted(by_standard.values(), key=lambda x: -x[0])[:top_k]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--clauses", default=str(DATA / "a2" / "clauses.json"), help="A2 output to index")
    p.add_argument("--model", default=DEFAULT_MODEL, help="sentence-transformers model name")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--min-chars", type=int, default=40, help="skip clauses shorter than this")
    p.add_argument("--include-foreword", action="store_true",
                   help="index foreword clauses as well (they describe revision history, not requirements)")
    p.add_argument("--titles-only", action="store_true",
                   help="rebuild only the title index over every current standard (seconds, no embedding)")
    p.add_argument("--append", action="store_true",
                   help="keep the existing vectors and embed only clauses that are not yet indexed")
    p.add_argument("--query", help="search the existing index instead of building it")
    p.add_argument("--top", type=int, default=5, help="results to show with --query")
    args = p.parse_args()

    if args.titles_only:
        build_title_index()
        return

    if args.query:
        for i, (score, e) in enumerate(search(args.query, args.top), 1):
            print(f"{i}. {e['is_number']:<24} {score:.4f}  clause {e['clause']} ({e['role']}), "
                  f"page {e['page_start']}")
            print(f"   {e['standard_title'][:88]}")
            print(f"   {' '.join((e['text'] or '').split())[:150]}")
        return
    build(args)


if __name__ == "__main__":
    main()
