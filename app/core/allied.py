"""Module C2: Allied Standards Expander.

Takes what C1 found and walks the relationship map outward, two hops, then groups the result by the
role each standard plays. This is a graph traversal, not a search, which is exactly why a vector
index alone can never produce it.

Two sources of edges, merged:

* the catalogue's own cross-references from A1, 165,657 of them, typed from the cited standard's
  Aspect field ("Methods of tests" becomes a test method, and so on);
* A3's clause-level edges, which carry the sentence that asserts the relationship and a relation
  type read from the wording. Where both exist, A3 wins on type and supplies the evidence.

Every allied standard is passed through C3, so what the user sees is the edition in force, with a
note when the source standard cited a withdrawn one.

    from app.core.allied import AlliedExpander
    AlliedExpander().expand(["IS 1161:2014"])
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.catalogue import Catalogue, parse_any_is  # noqa: E402
from app.core.version_resolver import VersionResolver  # noqa: E402
from common.is_normalizer import norm_is_lookup_key  # noqa: E402
from contracts.retrieval import AlliedResult, AlliedStandard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
A3_EDGES = ROOT / "data" / "a3" / "edges.json"

# C2.4: not all edges deserve equal prominence.
RELATION_WEIGHT = {
    "normative_reference": 1.00,
    "test_method": 0.95,
    "safety": 0.85,
    "terminology": 0.80,
    "installation": 0.70,
    "related_product": 0.60,
    "same_family_part": 0.55,
}
DECAY = 0.5          # C2.3: a test method's own terminology standard is relevant, but less so
MAX_HOPS = 2         # C2.3: hop three pulls in a hundred standards with no real connection
SEED_FLOOR = 0.80    # C2.1: expanding from a weak match multiplies the error

# The cited standard's own Aspect field decides the edge type when A3 has nothing to say.
ASPECT_RELATION = {
    "methods of tests": "test_method",
    "terminology": "terminology",
    "safety standard": "safety",
    "code of practice": "installation",
    "product specification": "related_product",
    "dimensions": "related_product",
    "glossary of terms": "terminology",
}


class AlliedExpander:
    def __init__(self, catalogue: Optional[Catalogue] = None, resolver: Optional[VersionResolver] = None,
                 edges_path: Path = A3_EDGES):
        self.cat = catalogue or Catalogue.shared()
        self.resolver = resolver or VersionResolver(self.cat)
        self.a3 = self._load_a3(edges_path)

    # ---------------------------------------------------------------- public

    def expand(self, seeds: List[str], scores: Optional[Dict[str, float]] = None,
               depth: int = MAX_HOPS, floor: float = SEED_FLOOR) -> AlliedResult:
        """Walk outward from the seeds and return allied standards grouped by relation."""
        chosen = [s for s in seeds if not scores or scores.get(s, 1.0) >= floor]
        if not chosen:
            return AlliedResult(seeds=[], groups={}, total=0)

        best: Dict[str, AlliedStandard] = {}
        visited = {norm_is_lookup_key(s) for s in chosen}
        frontier = [(s, 1.0, s) for s in chosen]

        for hop in range(1, depth + 1):
            next_frontier = []
            for source, inherited, path in frontier:
                for edge in self._edges_from(source):
                    key = norm_is_lookup_key(edge["current"])
                    if key in visited and hop > 1:
                        continue
                    weight = round(inherited * RELATION_WEIGHT.get(edge["relation"], 0.5)
                                   * (DECAY ** (hop - 1)), 3)
                    route = f"{path} -> {edge['current']}"
                    existing = best.get(key)
                    if existing is None:
                        best[key] = AlliedStandard(
                            is_number=edge["current"], cited_as=edge["cited_as"],
                            record_id=edge["record_id"], title=edge["title"],
                            relation=edge["relation"], weight=weight, hops=hop,
                            paths=[route], evidence=edge["evidence"], superseded=edge["superseded"])
                    else:
                        # C2.5: keep the strongest weight, remember every route it was reached by.
                        if route not in existing.paths:
                            existing.paths.append(route)
                        if weight > existing.weight:
                            existing.weight = weight
                            existing.relation = edge["relation"] or existing.relation
                            existing.evidence = edge["evidence"] or existing.evidence
                    next_frontier.append((edge["current"], weight, route))
                    visited.add(key)
            frontier = next_frontier

        groups: Dict[str, List[AlliedStandard]] = defaultdict(list)
        for allied in sorted(best.values(), key=lambda a: (-a.weight, a.is_number)):
            groups[allied.relation].append(allied)
        ordered = {relation: groups[relation]
                   for relation in sorted(groups, key=lambda r: -RELATION_WEIGHT.get(r, 0.5))}
        return AlliedResult(seeds=chosen, groups=ordered, total=len(best))

    # ---------------------------------------------------------------- internals

    @staticmethod
    def _load_a3(path: Path) -> Dict[str, List[dict]]:
        """A3 edges, keyed by source standard. Absent file simply means no clause-level evidence."""
        if not path.exists():
            return {}
        by_source: Dict[str, List[dict]] = defaultdict(list)
        for edge in json.loads(path.read_text(encoding="utf-8")):
            by_source[norm_is_lookup_key(edge["from_is"])].append(edge)
        return by_source

    def _edges_from(self, source: str) -> List[dict]:
        """Every standard reachable from this one, with a relation type and, where known, evidence."""
        resolved = self.resolver.resolve(source)
        record_id = resolved.current_record_id or resolved.record_id
        if record_id is None:
            return []

        a3_by_target = {}
        for edge in self.a3.get(norm_is_lookup_key(resolved.current or source), []):
            a3_by_target[norm_is_lookup_key(edge["to_is"])] = edge

        out = []
        for row in self.cat.cited_by_record(record_id):
            cited_as = row["is_number"]
            target = self.resolver.resolve(cited_as)
            current = target.current or cited_as
            a3 = a3_by_target.pop(norm_is_lookup_key(cited_as), None) \
                or a3_by_target.pop(norm_is_lookup_key(current), None)
            # The title must describe the edition we are recommending, not the withdrawn one that
            # was cited: showing "IS 228 (Part 1):2025 — ... (Withdrawn)" reads as a contradiction.
            current_row = self.cat.record(target.current_record_id) if target.current_record_id else None
            out.append({
                "cited_as": cited_as,
                "current": current,
                "record_id": target.current_record_id or row["record_id"],
                "title": (current_row["title"] if current_row is not None else row["title"]) or "",
                "relation": (a3 or {}).get("relation") or self._relation_from_aspect(row["aspect"]),
                "evidence": (a3 or {}).get("evidence_text"),
                "superseded": bool(row["withdrawn"]),
            })

        # Anything A3 found in the text that the BIS page does not list. For IS 1786:2008 the page
        # lists one reference while the standard's own text cites eight.
        for edge in a3_by_target.values():
            target = self.resolver.resolve(edge["to_is"])
            if not target.exists:
                continue
            row = self.cat.record(target.current_record_id or target.record_id)
            out.append({
                "cited_as": edge["to_is"],
                "current": target.current or edge["to_is"],
                "record_id": target.current_record_id or target.record_id,
                "title": row["title"] if row is not None else "",
                "relation": edge["relation"],
                "evidence": edge.get("evidence_text"),
                "superseded": bool(row["withdrawn"]) if row is not None else False,
            })
        return out

    @staticmethod
    def _relation_from_aspect(aspect: Optional[str]) -> str:
        return ASPECT_RELATION.get((aspect or "").strip().lower(), "normative_reference")
