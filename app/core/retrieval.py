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

from app.catalogue import Catalogue  # noqa: E402
from contracts.retrieval import Evidence, RetrievalResult, RetrievedStandard  # noqa: E402
from ingest.build_index import load_index, load_model, tokenize  # noqa: E402

DEFAULT_RERANKER = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RRF_K = 60          # the constant from the literature; not a tuning knob
POOL = 25           # candidates per index, and the most the reranker ever sees
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


class RetrievalEngine:
    def __init__(self, reranker: Optional[str] = DEFAULT_RERANKER, catalogue: Optional[Catalogue] = None,
                 warm: bool = True):
        self.index, self.bm25, self.id_map, self.meta = load_index()
        self.model = load_model(self.meta["model"])
        self.cat = catalogue or Catalogue.shared()
        self._reranker_name = reranker
        self._reranker = None
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

        rows = [row for row, _ in fused[:POOL]]
        scores = self._rerank(query, rows) if (rerank and rows) else None
        result = self._roll_up(query, fused, rows, scores, top_k)
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

    def _rerank(self, query: str, rows: List[int]) -> Optional[List[float]]:
        if not self._reranker_name:
            return None
        if self._reranker is None:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder(self._reranker_name)
        pairs = [(query, self._text_of(row)[:RERANK_CHARS]) for row in rows]
        raw = self._reranker.predict(pairs)
        # Cross-encoder output is a logit; map it to 0..1 so thresholds elsewhere are meaningful.
        return [1 / (1 + math.exp(-float(s))) for s in raw]

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
