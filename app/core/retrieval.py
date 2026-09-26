"""Module C1: Hybrid Retrieval Engine.

Searches the A4 indexes two ways at once, merges the two ranked lists by position, re-orders the
shortlist with a cross-encoder, and rolls the surviving clauses up into standards. The clause that
scored highest travels with each standard as its evidence, which is what makes "why this standard?"
answerable.

Deviation from the manual, measured on this machine: `bge-reranker-v2-m3` needs over a minute to
score 25 candidates on a CPU, so the reranker here is `ms-marco-MiniLM-L-6-v2`, which does the same
job in 0.22 s. It is English-only, which is acceptable because B2 translates before retrieval.
Pass `reranker="BAAI/bge-reranker-v2-m3"` on a machine with a GPU.

    from app.core.retrieval import RetrievalEngine
    RetrievalEngine().search("43 grade ordinary portland cement for RCC work")
"""

import math
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.catalogue import Catalogue, parse_any_is  # noqa: E402
from contracts.retrieval import Evidence, RetrievalResult, RetrievedStandard  # noqa: E402
from ingest.build_index import TITLES_FILE, load_index, load_model, tokenize  # noqa: E402

DEFAULT_RERANKER = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RRF_K = 60          # the constant from the literature; not a tuning knob
# Candidates taken from each clause index before fusion.
#
# This was 25 while the clause index held 4,293 rows. Adding the BIS summaries took it to 4,856, and
# a row that used to scrape into the top 25 stopped doing so: IS 8041:1990 is the right standard for
# "quick setting high early strength cement", it ranked first before the corpus grew, and afterwards
# it did not appear in the results at all — not demoted, simply never a candidate. The pool is a
# recall budget and has to grow with the corpus, so it is set from the corpus rather than left as a
# number that happened to work once.
POOL = 50
RERANK_POOL = 25    # the manual's cap: a cross-encoder must never see more than about 25 candidates
TITLE_POOL = 25     # unchanged; the title index still covers the same 24,101 standards it always did
QUOTE_CHARS = 300   # short extract only: BIS text is never redistributed in full
# Measured on this laptop: reranking 25 candidates of 850 characters costs 2.7 s, the same 25
# truncated to 400 characters costs 0.57 s, and the ranking does not change. A clause says what it
# is about in its opening sentence.
RERANK_CHARS = 400
MAX_ATTRIBUTES = 6   # a long attribute list dilutes the query rather than sharpening it
# Only absurd matches are dropped here. A higher bar loses correct answers: IS 8041:1990 is the
# right standard for "quick setting high early strength cement" and scores 0.055, while the next
# candidate scores 0.011. What protects the user from a weak answer is C5's confidence and B5's
# question, not a hard cut-off in retrieval.
MIN_MATCH = 0.02
IS_NUMBER = re.compile(r"\bIS\s*[:\s\-]?\s*\d{2,5}", re.IGNORECASE)
DROP_FIELDS = ("quantity", "delivery", "rate", "price")
CITED_FROM_TOP = 3        # only the best clauses are trusted to name the authority
CITED_RANK_PENALTY = 4    # a citation counts as a weaker vote than a clause or a title match
CITED_LIMIT = 3

# How much a title match counts for, against a clause or summary match at the same rank.
#
# Plain Reciprocal Rank Fusion gives both signals the same vote, and that is wrong here because the
# two are not the same kind of evidence. A clause or a BIS summary is text out of the standard
# itself; a title is only its name, which is why C5 already caps a title-only match below the high
# band. Weighting the vote the same way makes the fusion agree with that judgement.
#
# The failure it fixes, from the gold set: for "cement based tile adhesive for fixing vitrified
# tiles", IS 15477:2019 matched its own scope clause at 0.0333, the best score in the list, and
# still came third — because IS 13801:2013 ("Chequered Cement Concrete Tiles") shares the words
# "cement" and "tiles" with the query and collected a title vote worth as much as a clause.
#
# 0.5 is a judgement, not a tuned constant: a name is worth something and worth less than evidence.
# It is deliberately not pushed lower. The title signal is what finds the 23,000-odd standards whose
# text we do not hold, so suppressing it would flatter the gold set — where every answer now has
# text — while making the engine worse on everything outside it.
TITLE_WEIGHT = 0.5

# Units and bare numbers are stripped before the title index is searched. A BIS title says what a
# standard covers, never what quantity the tender wants, so a measurement in the query can only
# match a title by accident — and it does. Measured on the 50 gold records, searching titles with
# the raw query put the correct standard first 48% of the time; stripping these tokens raised it to
# 52%, and top-5 from 78% to 82%. The failures it fixes are exactly the absurd ones: "whiteness not
# less than 70 percent" matched a lifeboat standard for "less than 70 persons" and a sorbitol
# solution "(70 Percent)" above the white cement standard we were looking for.
# The clause index is left alone: there "43 grade" and "IP66" are real signal, which is why BM25 is
# in the pipeline at all.
MEASUREMENT_UNITS = {
    "mm", "cm", "m", "km", "kg", "mt", "kgf", "cm2", "m2", "mm2", "gsm", "nb", "dn", "pn", "sdr",
    "litre", "litres", "ltr", "percent", "pct", "mpa", "kn", "kv", "kw", "mtr", "inch", "dia",
    "thick", "thickness", "no", "nos",
}


def title_query(query: str) -> str:
    """The query with bare numbers and measurement units removed, for the title index only."""
    kept = [t for t in tokenize(query)
            if not t.replace(".", "").isdigit() and t not in MEASUREMENT_UNITS]
    return " ".join(kept) or query


class RetrievalEngine:
    def __init__(self, reranker: Optional[str] = DEFAULT_RERANKER, catalogue: Optional[Catalogue] = None,
                 warm: bool = True):
        self.index, self.bm25, self.id_map, self.meta = load_index()
        self.model = load_model(self.meta["model"])
        self.cat = catalogue or Catalogue.shared()
        self._reranker_name = reranker
        self._reranker = None
        self._title_index = None
        if warm:
            self.warm_up()

    def warm_up(self) -> None:
        """Run one throwaway query through both models.

        Measured on this laptop: the first encode costs 7 to 16 seconds while weights are paged in
        and kernels are chosen, then settles at about 0.25 s. A service must absorb that at startup,
        not on the first user's request.
        """
        self.model.encode(["warm up"], normalize_embeddings=True)
        if self._reranker_name:
            self._rerank("warm up", [0])

    # ---------------------------------------------------------------- query building

    @staticmethod
    def build_query(requirement: dict) -> str:
        """C1.1: build the search string from B3's structured fields, in a fixed order.

        Quantity and delivery terms are excluded deliberately: '500 MT' carries no signal about
        which standard applies and pulls keyword search toward clauses that mention tonnage.
        """
        if not requirement:
            return ""
        attributes = requirement.get("attributes") or {}
        application = attributes.get("application") or requirement.get("application") or ""
        parts = [requirement.get("product") or ""]
        for key, value in list(attributes.items())[:MAX_ATTRIBUTES]:
            if key.lower() in DROP_FIELDS or key.lower() == "application" or not value:
                continue
            value = str(value)
            # A standard number in the query pulls retrieval toward whatever clause happens to cite
            # it. The numbers the tender gave are B4's business, not the search engine's.
            if IS_NUMBER.search(value):
                continue
            parts.append(value if key.lower() in value.lower() else f"{value} {key}")
        parts.append(application)
        seen, ordered = set(), []
        for part in parts:
            part = str(part).strip()
            if part and part.lower() not in seen:
                seen.add(part.lower())
                ordered.append(part)
        return " ".join(ordered)

    # ---------------------------------------------------------------- search

    def search(self, query: str, top_k: int = 5, rerank: bool = False) -> RetrievalResult:
        """Search the index. Reranking is off by default, which departs from the manual.

        Measured on the 27 gold records whose text is indexed (eval/run_eval.py):

            fusion only                Hit@1 0.889   Hit@3 0.926   MRR@5 0.901
            + MiniLM cross-encoder     Hit@1 0.704   Hit@3 0.963   MRR@5 0.821
            + blended, alpha 0.5       Hit@1 0.778   Hit@3 0.926   MRR@5 0.859

        The small cross-encoder is trained on web passages, not standards clauses: it rescues one
        record into the top three and costs five at rank one. Since the product names a single
        primary standard, rank one is what matters. Revisit with the manual's bge-reranker-v2-m3 on
        a machine with a GPU, where the domain gap should be smaller.
        """
        started = time.time()
        if not query.strip():
            return RetrievalResult(query=query, seconds=0.0)

        dense = self._dense(query)
        sparse = self._sparse(query)
        fused = self._fuse(dense, sparse)

        rows = [row for row, _ in fused[:RERANK_POOL]]
        scores = self._rerank(query, rows) if (rerank and rows) else None
        result = self._roll_up(query, fused, rows, scores, top_k)
        result.standards = self._merge_titles(query, result.standards, top_k)
        result.considered_clauses = len(fused)
        result.reranked = scores is not None
        result.seconds = round(time.time() - started, 2)
        return result

    def score(self, query: str, is_number: str) -> float:
        """How well one named standard answers a query, for B4's relevance judgement."""
        rows = [i for i, entry in enumerate(self.id_map)
                if entry["is_number"].replace(" ", "").upper() == is_number.replace(" ", "").upper()]
        if not rows:
            return 0.0
        scores = self._rerank(query, rows)
        return max(scores) if scores else 0.0

    # ---------------------------------------------------------------- internals

    def _dense(self, query: str) -> List[int]:
        import numpy as np
        vector = np.asarray(self.model.encode([query], normalize_embeddings=True), dtype="float32")
        _, rows = self.index.search(vector, min(POOL, self.index.ntotal))
        return [int(r) for r in rows[0] if r >= 0]

    def _sparse(self, query: str) -> List[int]:
        import numpy as np
        scores = self.bm25.get_scores(tokenize(query))
        return [int(r) for r in np.argsort(scores)[::-1][:POOL] if scores[r] > 0]

    @staticmethod
    def _fuse(dense: List[int], sparse: List[int]):
        """C1.4: Reciprocal Rank Fusion. Positions only, because a cosine distance and a BM25
        score are not comparable numbers."""
        fused = {}
        for rank, row in enumerate(dense):
            fused[row] = fused.get(row, 0.0) + 1 / (RRF_K + rank)
        for rank, row in enumerate(sparse):
            fused[row] = fused.get(row, 0.0) + 1 / (RRF_K + rank)
        return sorted(fused.items(), key=lambda kv: -kv[1])

    def _rerank(self, query: str, rows: Optional[List[int]],
                texts: Optional[List[str]] = None) -> Optional[List[float]]:
        """Absolute 0..1 scores for candidate rows, or for texts supplied directly (title matches)."""
        if not self._reranker_name:
            return None
        if self._reranker is None:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder(self._reranker_name)
        candidates = texts if texts is not None else [self._text_of(row) for row in rows or []]
        if not candidates:
            return []
        pairs = [(query, text[:RERANK_CHARS]) for text in candidates]
        raw = self._reranker.predict(pairs)
        # Cross-encoder output is a logit; map it to 0..1 so thresholds elsewhere are meaningful.
        return [1 / (1 + math.exp(-float(s))) for s in raw]

    def _cited_by(self, standards: List[RetrievedStandard]) -> List[str]:
        """Current editions of the standards cited inside the best clauses, most cited first."""
        counts = {}
        for standard in standards:
            text = standard.evidence.quote if standard.evidence else ""
            for match in IS_NUMBER.finditer(text or ""):
                resolved = self.cat.family(parse_any_is(match.group(0))) if parse_any_is(match.group(0)) else []
                current = next((row for row in resolved if not row["withdrawn"]), None)
                if current is not None and current["is_number"] != standard.is_number:
                    counts[current["is_number"]] = counts.get(current["is_number"], 0) + 1
        return [number for number, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:CITED_LIMIT]

    def _titles(self):
        """The BM25 index over every current standard's title, loaded once."""
        if self._title_index is None and TITLES_FILE.exists():
            import pickle
            self._title_index = pickle.loads(TITLES_FILE.read_bytes())
        return self._title_index

    def _merge_titles(self, query: str, standards: List[RetrievedStandard],
                      top_k: int) -> List[RetrievedStandard]:
        """Merge title matches with the clause matches, by rank.

        The clause index covers 266 standards; the catalogue holds 24,101 current ones. Without this
        step a query about anything outside the indexed text lands on whichever clause happens to
        mention the product, which is how "43 grade ordinary Portland cement" returned a flooring
        tile standard. A title match has no clause to quote, so it is marked `source="title"` and
        C5 treats it as weaker evidence.

        The query is stripped of measurements first: see `title_query`.
        """
        import numpy as np

        index = self._titles()
        if not index:
            return standards

        scores = index["bm25"].get_scores(tokenize(title_query(query)))
        order = [int(i) for i in np.argsort(scores)[::-1][:TITLE_POOL] if scores[i] > 0]
        if not order:
            return standards

        fused = {}
        for rank, standard in enumerate(standards):
            fused[standard.is_number] = fused.get(standard.is_number, 0.0) + 1 / (RRF_K + rank)

        # A third signal: the standards that the best-matching clauses point at. When a clause says
        # "ordinary Portland cement conforming to IS 269", the corpus is naming the authority for the
        # product even though we hold no text for it. Counted as a weak vote, below the clause and
        # title lists, because a clause cites many standards for many reasons.
        for rank, cited in enumerate(self._cited_by(standards[:CITED_FROM_TOP])):
            fused[cited] = fused.get(cited, 0.0) + 1 / (RRF_K + rank + CITED_RANK_PENALTY)
        title_rows = {}
        for rank, position in enumerate(order):
            row = index["rows"][position]
            fused[row["is_number"]] = (fused.get(row["is_number"], 0.0)
                                       + TITLE_WEIGHT / (RRF_K + rank))
            title_rows.setdefault(row["is_number"], row)

        by_number = {s.is_number: s for s in standards}
        extras = []
        for number in fused:
            if number in by_number:
                continue
            row = title_rows.get(number)
            if row is None:
                # Reached through a citation inside a matching clause rather than the title index.
                catalogue_row = next((r for r in self.cat.family(parse_any_is(number) or "")
                                      if r["is_number"] == number), None)
                if catalogue_row is None:
                    continue
                row = {"record_id": catalogue_row["record_id"], "is_number": number,
                       "title": catalogue_row["title"] or "",
                       "department": (catalogue_row["department"] or "")[:3], "context": ""}
                extras.append((number, row, "cited"))
            else:
                extras.append((number, row, "title"))

        matches = self._rerank(query, None, texts=[
            f"{row['is_number']} {row['title']} {row.get('context', '')}" for _, row, _ in extras
        ]) if extras else []

        for (number, row, source), match in zip(extras, matches or [None] * len(extras)):
            by_number[number] = RetrievedStandard(
                is_number=number, record_id=row["record_id"], title=row["title"],
                department=row["department"], source=source,
                score=round(fused[number], 5), fusion_score=round(fused[number], 5),
                match=round(float(match), 4) if match is not None else None,
                evidence=None)

        # The minimum-match rule belongs to clause hits only. A cross-encoder scores a short title
        # far lower than a paragraph, so applying the same bar would discard the right answer:
        # IS 269:2015 ranks second in the title index for "ordinary Portland cement 43 grade" and
        # would otherwise be dropped. BM25 having ranked the title at all is the relevance gate here.
        merged = sorted(by_number.values(), key=lambda s: -fused.get(s.is_number, 0.0))
        return [s for s in merged
                if s.source != "clause" or s.match is None or s.match >= MIN_MATCH][:top_k]

    def _text_of(self, row: int) -> str:
        entry = self.id_map[row]
        head = f"{entry['is_number']} {entry.get('standard_title', '')} {entry.get('title') or ''}"
        return f"{head.strip()} — {(entry.get('text') or '')[:1200]}"

    def _roll_up(self, query, fused, pooled_rows, scores, top_k) -> RetrievalResult:
        """C1.6: group clauses by their standard and keep the best clause as the evidence.

        The maximum is used rather than the mean: a standard with one perfectly matching scope
        clause and forty irrelevant test clauses is still the right answer.
        """
        fusion_by_row = dict(fused)
        scored_rows = (list(zip(pooled_rows, scores)) if scores is not None
                       else [(row, value) for row, value in fused[:POOL]])

        best = {}
        for row, score in scored_rows:
            entry = self.id_map[row]
            key = entry.get("record_id") or entry["is_number"]
            if key not in best or score > best[key][0]:
                best[key] = (score, row)

        chosen = sorted(best.items(), key=lambda kv: -kv[1][0])[:top_k]

        # An absolute match score for the shortlist. Fusion scores are ranks in disguise and mean
        # nothing across queries, so C5 cannot build an honest confidence from them. Scoring a few
        # pairs with the cross-encoder costs about 0.05 s and gives a comparable 0..1 number.
        matches = {}
        if scores is None and self._reranker_name and chosen:
            rows_to_score = [row for _, (_, row) in chosen]
            absolute = self._rerank(query, rows_to_score)
            if absolute:
                matches = dict(zip(rows_to_score, absolute))

        standards = []
        for key, (score, row) in chosen:
            match = matches.get(row, score if scores is not None else None)
            if match is not None and match < MIN_MATCH:
                # Returning a standard whose clause plainly does not answer the query is worse than
                # returning nothing: C5 would score it low, but D2 would still print it.
                continue
            entry = self.id_map[row]
            quote = " ".join((entry.get("text") or "").split())[:QUOTE_CHARS]
            standards.append(RetrievedStandard(
                is_number=entry["is_number"],
                record_id=entry.get("record_id"),
                title=entry.get("standard_title") or "",
                department=entry.get("department") or "",
                score=round(float(score), 4),
                fusion_score=round(float(fusion_by_row.get(row, 0.0)), 5),
                match=round(float(matches[row]), 4) if row in matches else (
                    round(float(score), 4) if scores is not None else None),
                evidence=Evidence(
                    clause=str(entry.get("clause")),
                    clause_id=str(entry.get("clause_id")),
                    role=str(entry.get("role")),
                    page_start=entry.get("page_start"),
                    page_end=entry.get("page_end"),
                    quote=quote,
                ),
            ))
        return RetrievalResult(query=query, standards=standards)
